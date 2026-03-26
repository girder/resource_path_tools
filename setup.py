import os

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()


def prerelease_local_scheme(version):
    """
    Return local scheme version unless building on master in CircleCI.

    This function returns the local scheme version number
    (e.g. 0.0.0.dev<N>+g<HASH>) unless building on CircleCI for a
    pre-release in which case it ignores the hash and produces a
    PEP440 compliant pre-release version number (e.g. 0.0.0.dev<N>).
    """
    from setuptools_scm.version import get_local_node_and_date

    if os.getenv('CIRCLE_BRANCH') in ('master', ):
        return ''
    else:
        return get_local_node_and_date(version)


setup(
    name='girder-resource-path-tools',
    use_scm_version={'local_scheme': prerelease_local_scheme, 'fallback_version': '0.0.0'},
    setup_requires=['setuptools-scm'],
    author='Kitware, Inc.',
    author_email='kitware@kitware.com',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12'
        'Programming Language :: Python :: 3.13'
        'Programming Language :: Python :: 3.14'
    ],
    description='Add resource path utility endpoints.',
    # Note: this plugin works with both Girder 3 and Girder 5
    install_requires=[
        'girder>=3.0.2',
    ],
    license='Apache Software License 2.0',
    long_description=readme,
    long_description_content_type='text/x-rst',
    include_package_data=True,
    keywords='girder-plugin, resource_path_tools',
    packages=find_packages(exclude=['test', 'test.*']),
    url='https://github.com/girder/resource_path_tools',
    zip_safe=False,
    entry_points={
        'girder.plugin': [
            'resource_path_tools = resource_path_tools:GirderPlugin'
        ]
    }
)
