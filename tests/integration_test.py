import os.path
import subprocess
import tempfile

import pytest

from dumb_pypi import main
from testing import make_package


def install_packages(path, package_names):
    """Deploy fake packages with the given names into path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for package in package_names:
            make_package(os.path.join(tmpdir, package))
        main.main((tmpdir, path.strpath))


def pip_download(pip, index_url, path, *spec):
    subprocess.check_call(
        (pip, 'install', '-i', index_url, '--download', path) + spec,
    )


@pytest.mark.parametrize('package_names', (
    ('aspy.yaml-0.2.1.zip',),
    ('aspy.yaml-0.2.1.tar',),
    ('aspy.yaml-0.2.1.tar.gz',),
    ('aspy.yaml-0.2.1.tgz',),
    ('aspy.yaml-0.2.1-py2.py3-none-any.whl',)
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
        package_names,
        requirement,
):
    install_packages(tmpweb.path, package_names)
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
        'aspy.yaml-0.2.1-py2.py3-none-any.whl',
    ))
    pip_download(
        modern_pips,
        tmpweb.url + '/simple',
        tmpdir.strpath,
        requirement,
    )
