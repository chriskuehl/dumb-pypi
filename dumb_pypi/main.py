"""A simple read-only PyPI static index server generator."""
import argparse
import collections
import contextlib
import operator
import os
import os.path
import re
import sys
import tempfile
from datetime import datetime

import jinja2
import packaging.utils
import packaging.version
import pkg_resources
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


def guess_name_version_from_filename(filename):
    if filename.endswith('.whl'):
        wheel = Wheel(filename)
        return wheel.name, wheel.version
    else:
        # These don't have a well-defined format like wheels do, so they are
        # sort of "best effort", with lots of tests to back them up.
        # The most important thing is to correctly parse the name.
        name = remove_extension(filename)
        version = None

        if '-' in name:
            if name.count('-') == 1:
                name, version = name.split('-')
            else:
                parts = name.split('-')
                for i in range(len(parts) - 1, 0, -1):
                    part = parts[i]
                    if '.' in part and re.search('[0-9]', part):
                        name, version = '-'.join(parts[0:i]), '-'.join(parts[i:])

        # possible with poorly-named files
        if len(name) <= 0:
            raise ValueError('Invalid package name: {}'.format(filename))

        # impossible
        assert version is None or len(version) > 0, version

        return name, version


class Package(collections.namedtuple('Package', (
    'filename',
    'name',
    'version',
    'url',
))):

    __slots__ = ()

    def __lt__(self, other):
        assert isinstance(other, Package), type(other)
        return self.sort_key < other.sort_key

    @property
    def sort_key(self):
        """Sort key for a filename."""
        return (
            self.name,
            pkg_resources.parse_version(self.version or '0'),

            # This looks ridiculous, but it's so that like extensions sort
            # together when the name and version are the same (otherwise it
            # depends on how the filename is normalized, which means sometimes
            # wheels sort before tarballs, but not always).
            # Alternatively we could just grab the extension, but that's less
            # amusing, even though it took 6 lines of comments to explain this.
            self.filename[::-1],
        )

    @classmethod
    def from_filename(cls, filename, base_url):
        if not re.match('[a-zA-Z0-9_\-\.]+$', filename) or '..' in filename:
            raise ValueError('Unsafe package name: {}'.format(filename))

        name, version = guess_name_version_from_filename(filename)
        return cls(
            filename=filename,
            name=packaging.utils.canonicalize_name(name),
            version=version,
            url=base_url.rstrip('/') + '/' + filename,
        )


@contextlib.contextmanager
def atomic_write(path):
    tmp = tempfile.mktemp(
        prefix='.' + os.path.basename(path),
        dir=os.path.dirname(path),
    )
    try:
        with open(tmp, 'w') as f:
            yield f
    except:
        os.remove(tmp)
        raise
    else:
        os.rename(tmp, path)


# TODO: at some point there will be so many options we'll want to make a config
# object or similar instead of adding more arguments here
def build_repo(package_names, output_path, packages_url, title, logo, logo_width):
    packages = collections.defaultdict(set)
    for filename in package_names:
        try:
            package = Package.from_filename(filename, packages_url)
        except ValueError as ex:
            print('{} (skipping package)'.format(ex), file=sys.stderr)
        else:
            packages[package.name].add(package)

    simple = os.path.join(output_path, 'simple')
    os.makedirs(simple, exist_ok=True)

    current_date = datetime.now().isoformat()

    # /index.html
    with atomic_write(os.path.join(output_path, 'index.html')) as f:
        f.write(jinja_env.get_template('index.html').render(
            title=title,
            packages=sorted(
                (
                    package,
                    sorted(packages[package])[-1].version,
                )
                for package in packages
            ),
            logo=logo,
            logo_width=logo_width,
        ))

    # /simple/index.html
    with atomic_write(os.path.join(simple, 'index.html')) as f:
        f.write(jinja_env.get_template('simple.html').render(
            date=current_date,
            package_names=sorted(packages),
        ))

    for package_name, versions in packages.items():
        package_dir = os.path.join(simple, package_name)
        os.makedirs(package_dir, exist_ok=True)

        # /simple/{package}/index.html
        with atomic_write(os.path.join(package_dir, 'index.html')) as f:
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
    parser.add_argument(
        '--title',
        help='site title (for web interface)', default='My Private PyPI',
    )
    parser.add_argument(
        '--logo',
        help='URL for logo to display (defaults to no logo)',
    )
    parser.add_argument(
        '--logo-width', type=int,
        help='width of logo to display', default=0,
    )
    args = parser.parse_args(argv)

    build_repo(
        args.package_list,
        args.output_dir,
        args.packages_url,
        args.title,
        args.logo,
        args.logo_width,
    )


if __name__ == '__main__':
    exit(main())
