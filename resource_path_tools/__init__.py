import cherrypy
import six
from six.moves import urllib

from pkg_resources import DistributionNotFound, get_distribution

import girder.api.docs
import girder.api.rest
import girder.api.v1.resource
import girder.plugin

from girder.api import access
from girder.api.describe import Description, autoDescribeRoute
from girder.api.rest import Resource, setContentDisposition, setRawResponse, setResponseHeader
from girder.constants import AccessType, SortDir, TokenScope
from girder.exceptions import RestException
from girder.models.collection import Collection
from girder.models.file import File
from girder.models.folder import Folder
from girder.models.item import Item
from girder.models.user import User
from girder.utility import path as path_util
from girder.utility import ziputil

try:
    __version__ = get_distribution(__name__).version
except DistributionNotFound:
    # package is not installed
    pass


_oldMatchRoute = None


def _matchRoute(self, method, path):
    try:
        return _oldMatchRoute(self, method, path)
    except RestException:
        # Handle routes with variable arguments
        for routelen in range(len(path), 0, -1):
            for route, handler in self._routes[method][routelen]:
                wildcards = {}
                if route[-1].startswith('+'):
                    wildcards[route[-1][1:]] = path[routelen - 1:]
                    for routeComponent, pathComponent in six.moves.zip(
                            route[:-1], path[:routelen - 1]):
                        if routeComponent[0] == ':':  # Wildcard token
                            wildcards[routeComponent[1:]] = pathComponent
                        elif routeComponent != pathComponent:  # Exact match token
                            break
                    else:
                        return route, handler, wildcards
        raise


def _toRoutePath(resource, route):
    """
    Convert a base resource type and list of route components into a
    Swagger-compatible route path.
    """
    # Convert wildcard tokens from :foo form to {foo} form
    convRoute = [
        '{%s}' % token[1:] if token[0] in {':', '+'} else token
        for token in route
    ]

    prefix = ['']
    # If resource is a string then use this as the prefix to the route.
    if isinstance(resource, str):
        prefix.append(resource)

    path = '/'.join(prefix + convRoute)
    return path


class PathToolsResource(girder.api.v1.resource.Resource):
    def __init__(self, apiRoot):
        super(girder.api.v1.resource.Resource, self).__init__()
        apiRoot.resource.route('GET', ('path', 'download', '+path'), self.pathDownload)
        apiRoot.resource.route('GET', ('path', 'redirect', '+path'), self.pathRedirect)
        apiRoot.resource.route('PUT', ('path', 'redirect', '+path'), self.pathRedirect)
        apiRoot.resource.route('POST', ('path', 'redirect', '+path'), self.pathRedirect)
        apiRoot.resource.route('DELETE', ('path', 'redirect', '+path'), self.pathRedirect)

    @access.public(scope=TokenScope.DATA_READ, cookie=True)
    @autoDescribeRoute(
        Description('Download a resource based on its path')
        .param('path',
               'The path of the resource.  The path must be an absolute Unix '
               'path starting with either "/user/[user name]", for a user\'s '
               'resources or "/collection/[collection name]", for resources '
               'under a collection.',
               paramType='path')
        .errorResponse('Path is invalid.')
        .errorResponse('Path refers to a resource that does not exist.')
        .errorResponse('Read access was denied for the resource.', 403)
    )
    def pathDownload(self, path):
        user = self.getCurrentUser()
        path = '/'.join(path)
        resource = path_util.lookUpPath(path, user)['document']
        if resource['_modelType'] == 'file':
            singleFile = resource
        else:
            model = self._getResourceModel(resource['_modelType'], 'fileList')
            singleFile = None
            for _path, file in model.fileList(doc=resource, user=user, subpath=True, data=False):
                if singleFile is None:
                    singleFile = file
                else:
                    singleFile = False
                    break
        if singleFile is not False and singleFile is not None:
            offset, endByte = 0, None
            rangeHeader = cherrypy.lib.httputil.get_ranges(
                cherrypy.request.headers.get('Range'), singleFile.get('size', 0))
            if rangeHeader and len(rangeHeader):
                offset, endByte = rangeHeader[0]
            singleFile = File().load(singleFile['_id'], user=user, level=AccessType.READ)
            return File().download(singleFile, offset, endByte=endByte)
        setResponseHeader('Content-Type', 'application/zip')
        setContentDisposition(resource.get('name', 'Resources') + '.zip')

        def stream():
            zip = ziputil.ZipGenerator()
            for (path, file) in model.fileList(
                    doc=resource, user=user, subpath=True):
                for data in zip.addFile(file, path):
                    yield data
            yield zip.footer()
        return stream

    @access.public(scope=TokenScope.DATA_READ, cookie=True)
    @autoDescribeRoute(
        Description('Redirect to a model endpoint based on a resource path')
        .notes('This is significantly less efficient that using '
               '/(model)/(id)/..., as the route must validated and tested to '
               'that the longest sensible path is used.')
        .param('path',
               'The path of the resource.  The path must be an absolute Unix '
               'path starting with either "/user/[user name]", for a user\'s '
               'resources or "/collection/[collection name]", for resources '
               'under a collection.',
               paramType='path')
        .errorResponse('Path is invalid.')
        .errorResponse('Path refers to a resource that does not exist.')
        .errorResponse('Read access was denied for the resource.', 403)
    )
    def pathRedirect(self, path):
        user = self.getCurrentUser()
        # Find the longest path that is a valid resource
        used = len(path)
        while used:
            try:
                resource = path_util.lookUpPath('/'.join(path[:used]), user)['document']
                break
            except path_util.ResourcePathNotFound:
                if used == 1:
                    raise
                used -= 1
        path = [resource['_modelType'], str(resource['_id'])] + list(path[used:])
        path_info = ('/'.join(cherrypy.request.path_info.split('/')[:2] + path))
        # This locates the redirected handler
        cherrypy.request.get_resource(path_info)
        result = cherrypy.request.handler()
        setRawResponse()
        return result


class ResourceFilesResource(Resource):
    def __init__(self):
        super(ResourceFilesResource, self).__init__()
        self.resourceName = 'files'
        self.route('GET', (), self.filesResponseRoot)
        self.route('GET', ('+path', ), self.filesResponse)

    def _forward(self):
        """
        Forward a request to the same path with a slash added.
        """
        result = '\n'.join([
            '<html>', '<head><title>301 Moved Permanently</title></head>',
            '<body>', '<center><h1>301 Moved Permanently</h1></center>',
            '</body>', '</html>'])
        setResponseHeader('Location', cherrypy.request.path_info + '/')
        setResponseHeader('Content-Type', 'text/html')
        setRawResponse()
        cherrypy.response.status = 301
        return result.encode('utf8')

    def _listDirectory(self, path, children):
        """
        List a directory as an html format response like ftp servers do.

        :param path: the string path used to get here.
        :param children: a list of mongo documents with the children to list.
        """
        path = path.rstrip('/')
        result = [
            '<head><title>Index of /%s</title></head>' % path,
            '<body',
            '<h1>Index of /%s</h1><hr><pre><a href="../">..</a>' % path
        ]
        listing = []
        for child in children:
            name = child.get('name', child.get('login'))
            if not name:
                continue
            date = child.get('modified', child.get('created'))
            datestr = date.strftime('%Y-%m-%d %H:%M:%S') if date else ''
            sizestr = str(child.get('size')) if child.get('size') is not None else ''
            listing.append((name, datestr, sizestr))
        maxlen = max(len(entry[0]) for entry in listing) if listing else 1
        for name, datestr, sizestr in listing:
            result.append('<a href="%s">%s</a>%s %s %10s' % (
                urllib.parse.quote(name), name, ' ' * (maxlen - len(name)), datestr, sizestr))
        result.extend(['</pre><hr></body>', '</html>'])
        result = '\n'.join(result)
        setResponseHeader('Content-Type', 'text/html')
        setRawResponse()
        return result.encode('utf8')

    @access.public(scope=TokenScope.DATA_READ, cookie=True)
    @autoDescribeRoute(
        Description('List subitems or download a resource based on its path')
    )
    def filesResponseRoot(self):
        if not cherrypy.request.path_info.endswith('/'):
            return self._forward()
        return self._listDirectory('', [{'name': 'collection'}, {'name': 'user'}])

    @access.public(scope=TokenScope.DATA_READ, cookie=True)
    @autoDescribeRoute(
        Description('List subitems or download a resource based on its path')
        .param('path',
               'The path of the resource.  The path must be an absolute Unix '
               'path starting with either "/user/[user name]", for a user\'s '
               'resources or "/collection/[collection name]", for resources '
               'under a collection.',
               paramType='path')
        .errorResponse('Path is invalid.')
        .errorResponse('Path refers to a resource that does not exist.')
        .errorResponse('Read access was denied for the resource.', 403)
    )
    def filesResponse(self, path):
        user = self.getCurrentUser()
        path = '/'.join(path)
        # Handle /collection and /user specially
        if path in ('user', 'collection'):
            if not cherrypy.request.path_info.endswith('/'):
                return self._forward()
            model = User() if path == 'user' else Collection()
            return self._listDirectory(path, model.list(
                user=user, sort=[('user' if path == 'user' else 'name', SortDir.ASCENDING)]))
        resource = path_util.lookUpPath(path, user)['document']
        singleFile = None
        if resource['_modelType'] == 'file':
            singleFile = resource
        elif resource['_modelType'] == 'item':
            singleFile = None
            for _path, file in Item().fileList(doc=resource, user=user, subpath=True, data=False):
                if singleFile is None:
                    singleFile = file
                else:
                    singleFile = False
                    break
        if singleFile is not False and singleFile is not None:
            offset, endByte = 0, None
            rangeHeader = cherrypy.lib.httputil.get_ranges(
                cherrypy.request.headers.get('Range'), singleFile.get('size', 0))
            if rangeHeader and len(rangeHeader):
                offset, endByte = rangeHeader[0]
            singleFile = File().load(singleFile['_id'], user=user, level=AccessType.READ)
            return File().download(singleFile, offset, endByte=endByte)
        if not cherrypy.request.path_info.endswith('/'):
            return self._forward()
        children = []
        if resource['_modelType'] != 'item':
            children.extend(Folder().childFolders(
                parentType=resource['_modelType'], parent=resource, user=user,
                sort=[('name', SortDir.ASCENDING)]))
        if resource['_modelType'] == 'folder':
            children.extend(Folder().childItems(resource, sort=[('name', SortDir.ASCENDING)]))
        if resource['_modelType'] == 'item':
            children.extend(Item().childFiles(resource, sort=[('name', SortDir.ASCENDING)]))
        return self._listDirectory(path, children)


class GirderPlugin(girder.plugin.GirderPlugin):
    DISPLAY_NAME = 'Resource Path Tools'

    def load(self, info):
        global _oldMatchRoute

        if _oldMatchRoute is None:
            girder.api.docs._toRoutePath = _toRoutePath
            _oldMatchRoute = girder.api.rest.Resource._matchRoute
            girder.api.rest.Resource._matchRoute = _matchRoute
        PathToolsResource(info['apiRoot'])
        info['serverRoot'].files = ResourceFilesResource()
