import json
import os
import pytest
import requests

from pytest_girder.assertions import assertStatus, assertStatusOk
import pytest_girder.utils

from girder.models.collection import Collection
from girder.models.folder import Folder
from girder.models.item import Item
from girder.models.upload import Upload
from girder.utility import path as path_utils


def createData(admin, user):
    collection = Collection().createCollection('Test Collection', admin)
    collPrivateFolder = Folder().createFolder(
        collection, 'Private', parentType='collection', public=False, creator=admin)
    adminPublicFolder = path_utils.lookUpPath(
        '/user/admin/Public', filter=False, force=True)['document']
    adminSubFolder = Folder().createFolder(
        adminPublicFolder, 'Folder 1', creator=admin)
    item1 = Item().createItem('Item 1', admin, adminPublicFolder)
    item2 = Item().createItem('Item 2', admin, adminPublicFolder)
    item3 = Item().createItem('It\\em/3', admin, adminSubFolder)
    item4 = Item().createItem('Item 4', admin, collPrivateFolder)
    item5 = Item().createItem('Item 5', admin, collPrivateFolder)
    # just use this file itself as a test file
    filepath = os.path.realpath(__file__)
    filelen = os.path.getsize(filepath)
    file1 = Upload().uploadFromFile(
        open(filepath, 'rb'), filelen,
        'File 1', parentType='item', parent=item1, user=admin)
    file2 = Upload().uploadFromFile(
        open(filepath, 'rb'), filelen,
        'File 2', parentType='item', parent=item1, user=admin)
    file3 = Upload().uploadFromFile(
        open(filepath, 'rb'), filelen,
        'File 3', parentType='item', parent=item2, user=admin)
    file4 = Upload().uploadFromFile(
        open(filepath, 'rb'), filelen,
        'File 4', parentType='item', parent=item3, user=admin)
    file5 = Upload().uploadFromFile(
        open(filepath, 'rb'), filelen,
        'File 5', parentType='item', parent=item4, user=admin)
    return {
        'collection': collection,
        'collPrivateFolder': collPrivateFolder,
        'adminPublicFolder': adminPublicFolder,
        'adminSubFolder': adminSubFolder,
        'items': [item1, item2, item3, item4, item5],
        'files': [file1, file2, file3, file4, file5],
        'filelen': filelen
    }


@pytest.mark.plugin('resource_path_tools')
def test_download(server, admin, user, fsAssetstore):
    data = createData(admin, user)
    filelen = data['filelen']
    resp = server.request(
        path='/resource/path/download/user/admin/Public/Item 1/File 1',
        user=user, isJson=False)
    assertStatusOk(resp)
    assert len(b''.join(resp.body)) == filelen
    # Item 1 has multiple files, so we get more data for it
    resp = server.request(
        path='/resource/path/download/user/admin/Public/Item 1',
        user=user, isJson=False)
    assertStatusOk(resp)
    assert len(b''.join(resp.body)) >= filelen * 2
    # Item 2 has one file, so we just get the file
    resp = server.request(
        path='/resource/path/download/user/admin/Public/Item 2',
        user=user, isJson=False)
    assertStatusOk(resp)
    assert len(b''.join(resp.body)) == filelen
    # The user shouldn't be able to get a private file
    resp = server.request(
        path='/resource/path/download/collection/Test Collection/Private/Item 4',
        user=user, isJson=False)
    assertStatus(resp, 400)
    # But the admin should be able to get it
    resp = server.request(
        path='/resource/path/download/collection/Test Collection/Private/Item 4',
        user=admin, isJson=False)
    assertStatusOk(resp)
    assert len(b''.join(resp.body)) == filelen


@pytest.mark.plugin('resource_path_tools')
def test_redirect(boundServer, admin, user, fsAssetstore):
    # We have to use a bound server to habdle redirects properly
    createData(admin, user)
    body = json.dumps({'key': 'value'})
    headers = pytest_girder.utils.buildHeaders(
        [('Content-Type', 'application/json'), ('Content-Length', str(len(body)))],
        None, admin, None, None, None)
    resp = requests.put(
        'http://127.0.0.1:%d/api/v1/resource/path/redirect/user/admin/Public/Item 1/metadata' % (
            boundServer.boundPort), headers={k: v for k, v in headers}, data=body)
    assert resp.status_code == 200
    headers = pytest_girder.utils.buildHeaders(
        [('Accept', 'application/json')], None, user, None, None, None)
    resp = requests.get(
        'http://127.0.0.1:%d/api/v1/resource/path/redirect/user/admin/Public/Item 1' % (
            boundServer.boundPort), headers={k: v for k, v in headers})
    assert resp.status_code == 200
    assert resp.json()['meta'] == {'key': 'value'}


@pytest.mark.plugin('resource_path_tools')
def test_browse(server, admin, user, fsAssetstore):
    data = createData(admin, user)
    resp = server.request('/files', prefix='', user=admin, isJson=False)
    assertStatus(resp, 301)
    resp = server.request('/files/', prefix='', user=admin, isJson=False)
    assertStatusOk(resp)
    assert b'href="user"' in b''.join(resp.body)
    resp = server.request('/files/user/', prefix='', user=admin, isJson=False)
    assertStatusOk(resp)
    assert b'href="admin"' in b''.join(resp.body)
    resp = server.request('/files/user/admin/', prefix='', user=admin, isJson=False)
    assertStatusOk(resp)
    assert b'href="Public"' in b''.join(resp.body)
    resp = server.request('/files/user/admin/Public/', prefix='', user=admin, isJson=False)
    assertStatusOk(resp)
    assert b'href="Item%202"' in b''.join(resp.body)
    resp = server.request('/files/user/admin/Public/Item 1/', prefix='', user=admin, isJson=False)
    assertStatusOk(resp)
    assert b'href="File%201"' in b''.join(resp.body)
    resp = server.request('/files/user/admin/Public/Item 2', prefix='', user=admin, isJson=False)
    assertStatusOk(resp)
    assert len(b''.join(resp.body)) == data['filelen']
    resp = server.request(
        '/files/user/admin/Public/Item 2/File 3', prefix='', user=admin, isJson=False)
    assertStatusOk(resp)
    assert len(b''.join(resp.body)) == data['filelen']
