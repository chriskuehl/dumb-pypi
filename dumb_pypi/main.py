"""A simple read-only PyPI static index server generator."""
import argparse
import collections
import operator
import os
import os.path
import re
import sys
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
        version = None

        if '-' in name:
            if name.count('-') == 1:
                name, version = name.split('-')
            else:
                parts = name.split('-')
                for i in range(len(parts) - 1, -1, -1):
                    part = parts[i]
                    if '.' in part and re.search('[0-9]', part):
                        name, version = '-'.join(parts[0:i]), '-'.join(parts[i:])

        assert len(name) > 0, (name, version)
        return name, version


class Package(collections.namedtuple('Package', (
    'filename',
    'name',
    'version',
    'url',
))):

    __slots__ = ()

    @property
    def sort_key(self):
        """Sort key for a filename.

        Based on pkg_resources._by_version_descending.
        """
        name = remove_extension(self.filename)
        return tuple(packaging.version.parse(part) for part in name.split('-'))

    @classmethod
    def from_name(cls, filename, base_url):
        if not re.match('[a-zA-Z0-9_\-\.]+$', filename) or '..' in filename:
            raise ValueError('Unsafe package name: {}'.format(filename))

        name, version = guess_name_version_from_filename(filename)
        return cls(
            filename=filename,
            name=packaging.utils.canonicalize_name(name),
            version=version,
            url=base_url.rstrip('/') + '/' + filename,
        )


def build_repo(package_names, output_path, packages_url):
    packages = collections.defaultdict(set)
    for filename in package_names:
        package = Package.from_name(filename, packages_url)
        packages[package.name].add(package)

    simple = os.path.join(output_path, 'simple')
    os.makedirs(simple, exist_ok=True)

    current_date = datetime.now().isoformat()

    # /simple/index.html
    with open(os.path.join(simple, 'index.html'), 'w') as f:
        f.write(jinja_env.get_template('simple.html').render(
            date=current_date,
            package_names=sorted(packages),
        ))

    for package_name, versions in packages.items():
        package_dir = os.path.join(simple, package_name)
        os.makedirs(package_dir, exist_ok=True)

        # /simple/{package}/index.html
        with open(os.path.join(package_dir, 'index.html'), 'w') as f:
            f.write(jinja_env.get_template('package.html').render(
                date=current_date,
                package_name=package_name,
                versions=sorted(versions, key=operator.attrgetter('sort_key')),
            ))


def package_list(path):
    f = sys.stdin if path == '-' else open(path)
    return frozenset(f.read().splitlines())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--package-list', help='path to a list of packages (one per line)',
        type=package_list, required=True,
    )
    parser.add_argument(
        '--output-dir', help='path to output to', required=True,
    )
    parser.add_argument(
        '--packages-url',
        help='url to packages (can be absolute or relative)', required=True,
    )
    args = parser.parse_args(argv)

    build_repo(args.package_list, args.output_dir, args.packages_url)


if __name__ == '__main__':
    exit(main())
