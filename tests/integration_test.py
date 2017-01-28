import collections
import subprocess
import sys
import time
import uuid

import ephemeral_port_reserve
import pytest
import requests


UrlAndPath = collections.namedtuple('UrlAndPath', ('url', 'path'))


@pytest.fixture(scope='session')
def running_server(tmpdir_factory):
    ip = '127.0.0.1'
    port = ephemeral_port_reserve.reserve(ip=ip)
    url = 'http://{}:{}'.format(ip, port)

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
    path = tmpdir.join('pypi')
    path.mkdir()

    # symlink some uuid under the running server path to our tmpdir
    name = str(uuid.uuid4())
    running_server.path.join(name).mksymlinkto(path)

    return UrlAndPath('{}/{}'.format(running_server.url, name), path)


def test_lol(tmpweb):
    print(tmpweb)
