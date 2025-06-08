from __future__ import annotations

import collections
import subprocess
import sys
import time
import uuid

import ephemeral_port_reserve
import pytest
import requests


PIP_TEST_VERSION = '25.1.1'


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
    subprocess.check_call(('virtualenv', '-p', sys.executable, path.strpath))

    pip = path.join('bin', 'pip').strpath
    subprocess.check_call((pip, 'install', '-i', 'https://pypi.org/simple', f'pip=={version}'))
    subprocess.check_call((pip, 'install', '-i', 'https://pypi.org/simple', 'setuptools'))

    version_output = subprocess.check_output((pip, '--version'))
    assert version_output.split()[1].decode('ascii') == version
    return pip


@pytest.fixture(scope='session')
def pip(tmpdir_factory):
    return install_pip(PIP_TEST_VERSION, tmpdir_factory.mktemp('pip'))
