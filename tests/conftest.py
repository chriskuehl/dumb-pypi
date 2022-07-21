from __future__ import annotations

import collections
import subprocess
import sys
import time
import uuid

import ephemeral_port_reserve
import pytest
import requests


PIP_FULL_NORMALIZATION = ('9.0.1', '8.1.2')
PIP_PARTIAL_NORMALIZATION = ('8.0.0', '6.0')
PIP_NO_NORMALIZATION = ('1.5.5',)
ALL_PIPS = (
    PIP_FULL_NORMALIZATION +
    PIP_PARTIAL_NORMALIZATION +
    PIP_NO_NORMALIZATION
)


UrlAndPath = collections.namedtuple('UrlAndPath', ('url', 'path'))


@pytest.fixture(scope='session')
def running_server(tmpdir_factory):
    ip = '127.0.0.1'
    port = ephemeral_port_reserve.reserve(ip=ip)
    url = f'http://{ip}:{port}'

    path = tmpdir_factory.mktemp('http')
    proc = subprocess.Popen(
        (sys.executable, '-m', 'http.server', '-b', ip, str(port)),
        cwd=path.strpath,
    )
    try:
        for _ in range(100):
            try:
                requests.get(url)
            except requests.exceptions.ConnectionError:
                time.sleep(0.1)
            else:
                break
        else:
            raise AssertionError('http.server did not start fast enough.')
        yield UrlAndPath(url, path)
    finally:
        proc.terminate()
        proc.wait()


@pytest.fixture
def tmpweb(running_server, tmpdir):
    """Provide a URL and a path to write files into to publish them."""
    path = tmpdir.join('pypi')
    path.mkdir()

    # symlink some uuid under the running server path to our tmpdir
    name = str(uuid.uuid4())
    running_server.path.join(name).mksymlinkto(path)

    return UrlAndPath(f'{running_server.url}/{name}', path)


def install_pip(version, path):
    # Old versions of pip don't work with python3.6.
    subprocess.check_call(('virtualenv', '-p', 'python2.7', path.strpath))

    pip = path.join('bin', 'pip').strpath
    subprocess.check_call((pip, 'install', '-i', 'https://pypi.org/simple', f'pip=={version}'))

    version_output = subprocess.check_output((pip, '--version'))
    assert version_output.split()[1].decode('ascii') == version
    return pip


@pytest.fixture(scope='session')
def pip_versions(tmpdir_factory):
    return {
        version: install_pip(version, tmpdir_factory.mktemp(f'pip-{version}'))
        for version in ALL_PIPS
    }


@pytest.fixture(scope='session', params=ALL_PIPS)
def all_pips(request, pip_versions):
    version = request.param
    return pip_versions[version]


@pytest.fixture(scope='session', params=PIP_FULL_NORMALIZATION)
def modern_pips(request, pip_versions):
    version = request.param
    return pip_versions[version]
