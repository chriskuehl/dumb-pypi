from __future__ import annotations

import os
import subprocess

import pytest

from dumb_pypi import main
from testing import FakePackage
from testing import make_package


def install_packages(path, fake_packages):
    """Deploy fake packages with the given names into path."""
    pool = path.join('pool').mkdir()
    for package in fake_packages:
        make_package(package, pool.strpath)

    package_list = path.join('package-list.json')
    package_list.write('\n'.join(package.as_json() for package in fake_packages) + '\n')

    main.main((
        '--package-list-json', package_list.strpath,
        '--output-dir', path.strpath,
        '--packages-url', '../../pool/',
    ))


def pip_download(pip, index_url, path, *spec):
    subprocess.check_call(
        (pip, 'install', '-i', index_url, '--download', path) + spec,
    )


@pytest.mark.parametrize('packages', (
    (FakePackage('ocflib-2016.12.10.1.48-py2.py3-none-any.whl'),),
    (FakePackage('ocflib-2016.12.10.1.48.tar.gz'),),
    (FakePackage('ocflib-2016.12.10.1.48.zip'),),
))
@pytest.mark.parametrize('requirement', (
    'ocflib',
    'ocflib<2017',
    'ocflib==2016.12.10.1.48',
))
def test_simple_package(
        tmpdir,
        tmpweb,
        all_pips,
        packages,
        requirement,
):
    install_packages(tmpweb.path, packages)
    pip_download(
        all_pips,
        tmpweb.url + '/simple',
        tmpdir.strpath,
        requirement,
    )


@pytest.mark.parametrize('packages', (
    (FakePackage('aspy.yaml-0.2.1.zip'),),
    (FakePackage('aspy.yaml-0.2.1.tar'),),
    (FakePackage('aspy.yaml-0.2.1.tar.gz'),),
    (FakePackage('aspy.yaml-0.2.1.tgz'),),
    (FakePackage('aspy.yaml-0.2.1-py2.py3-none-any.whl'),)
))
@pytest.mark.parametrize('requirement', (
    'aspy.yaml',
    'aspy.yaml>0.2,<0.3',
    'aspy.yaml==0.2.1',
    'ASPY.YAML==0.2.1',
))
def test_normalized_packages_modern_pip(
        tmpdir,
        tmpweb,
        modern_pips,
        packages,
        requirement,
):
    """Only modern versions of pip fully normalize names before making requests
    to PyPI, so old versions of pip cannot pass this test.

    RATIONALE.md explains how we suggest adding support for old versions of pip.
    """
    install_packages(tmpweb.path, packages)
    pip_download(
        modern_pips,
        tmpweb.url + '/simple',
        tmpdir.strpath,
        requirement,
    )


@pytest.mark.parametrize('requirement', (
    'aspy-yaml',
    'aspy-yaml>0.2,<0.3',
    'ASPY-YAML==0.2.1',
))
def test_normalized_packages_modern_pip_wheels(
        tmpdir,
        tmpweb,
        modern_pips,
        requirement,
):
    """Wheels are special: unlike archives, the package names are fully
    normalized, so you can install with a wider varierty of names.
    """
    install_packages(tmpweb.path, (
        FakePackage('aspy.yaml-0.2.1-py2.py3-none-any.whl'),
    ))
    pip_download(
        modern_pips,
        tmpweb.url + '/simple',
        tmpdir.strpath,
        requirement,
    )


def test_pip_9_respects_requires_python(
        tmpdir,
        tmpweb,
        pip_versions,
):
    pip = pip_versions['9.0.1']
    install_packages(
        tmpweb.path,
        (
            # This is a fallback that shouldn't be used.
            FakePackage('foo-1.tar.gz'),
            # This one should match all verisons we care about.
            FakePackage('foo-2.tar.gz', requires_python='>=2'),
            # Nonsensical requires_python value that will never match.
            FakePackage('foo-3.tar.gz', requires_python='==1.2.3'),
        )
    )
    pip_download(
        pip,
        tmpweb.url + '/simple',
        tmpdir.strpath,
        'foo',
    )
    downloaded_package, = tmpdir.listdir(fil=os.path.isfile)
    assert downloaded_package.basename == 'foo-2.tar.gz'
