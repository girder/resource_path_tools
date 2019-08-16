======================
Resource Path Tools
======================

A Girder plugin to add some server-side tools that work with resource paths.

Features
--------

* Download by path.

  ``GET /resource/path/download/<resource path>`` will download the collection, user, folder, item, or file.  If there is a single file within a parent object, the file will be downloaded directly.  If there are multiple files, a zip file will be downloaded.

* Redirect by path.

  ``GET``, ``PUT``, ``POST``, ``DELETE`` ``/resource/path/redirect/<resource path>[/<path components>]`` will redirect to the appropriate model route for the last identifiable Girder model within the route.  
  
  Since only routes that the user has permission for can be accessed, this can have strange repercussions if the resource path has components that look like route paths.  For instance, ``PUT /resource/path/redirect/user/User/Public/ItemA/metadata`` will either modify an item's metadata OR alter a file named ``metadata`` within the item.

  Also, redirecting has a significant overhead compared to accessing a route by model and id, as the resource path must be validated and checked for permissions.

* Browse files via path.

  A ``GET /files`` endpoint is added at the server's root (not under the ``/api/v1`` route).  This responds much like an ftp server, providing HTML listings of available resources (based on the current user).  If the path is a single-file item or a file, then the appropriate file is returned.  For instance ``/files/user/User/Public/`` would list folders and items within the user's ``Public`` folder, while ``/files/user/User/Public/ItemA/File1`` will download the specified file.
