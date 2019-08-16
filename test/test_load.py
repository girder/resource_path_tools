import pytest

from girder.plugin import loadedPlugins


@pytest.mark.plugin('resource_path_tools')
def test_import(server):
    assert 'resource_path_tools' in loadedPlugins()
