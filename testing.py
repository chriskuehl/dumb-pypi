import os.path
import shutil
import subprocess
import sys
import tempfile
from typing import Tuple

from dumb_pypi import main


def make_package(path):
    """Make a fake package at path.

    Even with --download, pip insists on extracting the downloaded packages (in
    order to find dependencies), so we can't just make empty files.
    """
    name, version = main.guess_name_version_from_filename(os.path.basename(path))

    with tempfile.TemporaryDirectory() as td:
        setup_py = os.path.join(td, 'setup.py')
        with open(setup_py, 'w') as f:
            f.write(
                'from setuptools import setup\n'
                'setup(name="{}", version="{}")\n'.format(name, version),
            )

        args: Tuple[str, ...] = ('sdist', '--formats=zip')
        if path.endswith(('.tgz', '.tar.gz')):
            args = ('sdist', '--formats=gztar')
        elif path.endswith('.tar'):
            args = ('sdist', '--formats=tar')
        elif path.endswith('.whl'):
            args = ('bdist_wheel',)

        subprocess.check_call((sys.executable, setup_py) + args, cwd=td)
        created, = os.listdir(os.path.join(td, 'dist'))
        shutil.move(os.path.join(td, 'dist', created), path)
