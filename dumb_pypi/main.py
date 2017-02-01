"""A simple read-only PyPI static index server generator."""
import argparse
import collections
import operator
import os
import os.path
import shutil
from datetime import datetime

import jinja2
import packaging.utils
import packaging.version
from pip.wheel import Wheel


jinja_env = jinja2.Environment(
    loader=jinja2.PackageLoader('dumb_pypi', 'templates'),
    autoescape=True,
)


def remove_extension(name):
    if name.endswith(('gz', 'bz2')):
        name, _ = name.rsplit('.', 1)
    name, _ = name.rsplit('.', 1)
    return name


def guess_name_version_from_filename(name):
    if name.endswith('.whl'):
        wheel = Wheel(name)
        return wheel.name, wheel.version
    else:
        # These don't have a well-defined format like wheels do, so they are
        # sort of "best effort", with lots of tests to back them up.
        # The most important thing is to correctly parse the name.
        name = remove_extension(name)

        if '-' not in name:
            name, version = name, None
        elif name.count('-') == 1:
            name, version = name.split('-')
        else:
            parts = name.split('-')
            for i in range(len(parts) - 1, -1, -1):
                part = parts[i]
                if '.' in part:
                    name, version = '-'.join(parts[0:i]), '-'.join(parts[i:])

        return name, version


class Package(collections.namedtuple('Package', (
    'path',
    'name',
    'version',
))):

    __slots__ = ()

    @property
    def filename(self):
        return os.path.basename(self.path)

    @property
    def sort_key(self):
        """Sort key for a filename.

        Based on pkg_resources._by_version_descending.
        """
        name = remove_extension(self.filename)
        return tuple(packaging.version.parse(part) for part in name.split('-'))

    @classmethod
    def from_path(cls, path):
        name, version = guess_name_version_from_filename(os.path.basename(path))
        return cls(
            path=path,
            name=packaging.utils.canonicalize_name(name),
            version=version,
        )


def build_repo(packages_path, output_path):
    packages = collections.defaultdict(set)
    for filename in os.listdir(packages_path):
        full_path = os.path.join(packages_path, filename)
        package = Package.from_path(full_path)
        packages[package.name].add(package)

    simple = os.path.join(output_path, 'simple')
    os.makedirs(simple, exist_ok=True)

    pool = os.path.join(output_path, 'pool')
    os.makedirs(pool, exist_ok=True)

    # /simple/index.html
    with open(os.path.join(simple, 'index.html'), 'w') as f:
        f.write(jinja_env.get_template('simple.html').render(
            date=datetime.now().isoformat(),
            package_names=sorted(packages),
        ))

    for package_name, versions in packages.items():
        assert '/' not in package_name, package_name
        assert '..' not in package_name, package_name

        package_dir = os.path.join(simple, package_name)
        os.makedirs(package_dir, exist_ok=True)

        # /simple/{package}/index.html
        with open(os.path.join(package_dir, 'index.html'), 'w') as f:
            f.write(jinja_env.get_template('package.html').render(
                package_name=package_name,
                versions=sorted(versions, key=operator.attrgetter('sort_key')),
            ))

        # TODO: eventually, don't actually want to copy files
        for version in versions:
            assert '/' not in version.filename, version.filename
            assert '..' not in version.filename, version.filename

            # /pool/{filename}
            shutil.copy(version.path, os.path.join(pool, version.filename))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packages', help='path to packages')
    parser.add_argument('output_dir', help='path to output directory')
    args = parser.parse_args(argv)

    build_repo(args.packages, args.output_dir)


if __name__ == '__main__':
    exit(main())
