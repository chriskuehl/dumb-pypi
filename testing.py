import gzip
import io
import os.path
import tarfile
import zipfile

from dumb_pypi import main


def make_package(path):
    """Make a fake package at path.

    Even with --download, pip insists on extracting the downloaded packages (in
    order to find dependencies), so we can't just make empty files.
    """
    name, version = main.guess_name_version_from_filename(os.path.basename(path))
    setup_py = (
        'from setuptools import setup\n'
        'setup(name="{}", version="{}")\n'
    ).format(name, version).encode('utf8')

    is_gzip = path.endswith(('.tgz', '.tar.gz'))

    if is_gzip or path.endswith('.tar'):
        with tarfile.TarFile(path, 'w') as tf:
            ti = tarfile.TarInfo('{}/setup.py'.format(name))
            ti.size = len(setup_py)
            tf.addfile(ti, fileobj=io.BytesIO(setup_py))
    else:
        with zipfile.ZipFile(path, 'w') as zf:
            zf.writestr('{}/setup.py'.format(name), setup_py)

    if is_gzip:
        with open(path, 'rb+') as f:
            data = f.read()
            f.seek(0)
            f.write(gzip.compress(data))
            f.truncate()
