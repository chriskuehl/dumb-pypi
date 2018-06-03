"""A simple read-only PyPI static index server generator."""
import argparse
import collections
import contextlib
import json
import operator
import os
import os.path
import re
import sys
import tempfile
from datetime import datetime
from typing import Any
from typing import Dict
from typing import Generator
from typing import IO
from typing import Iterator
from typing import List
from typing import NamedTuple
from typing import Optional
from typing import Sequence
from typing import Set
from typing import Tuple

import distlib.wheel
import jinja2
import packaging.utils
import packaging.version


jinja_env = jinja2.Environment(
    loader=jinja2.PackageLoader('dumb_pypi', 'templates'),
    autoescape=True,
)


def remove_extension(name: str) -> str:
    if name.endswith(('gz', 'bz2')):
        name, _ = name.rsplit('.', 1)
    name, _ = name.rsplit('.', 1)
    return name


def guess_name_version_from_filename(
        filename: str,
) -> Tuple[str, Optional[str]]:
    if filename.endswith('.whl'):
        try:
            wheel = distlib.wheel.Wheel(filename)
        except distlib.DistlibException:
            raise ValueError(f'Invalid package name: {filename}')
        else:
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
            raise ValueError(f'Invalid package name: {filename}')

        # impossible
        assert version is None or len(version) > 0, version

        return name, version


class Package(NamedTuple):
    filename: str
    name: str
    version: Optional[str]
    hash: Optional[str]
    upload_timestamp: Optional[int]
    uploaded_by: Optional[str]

    def __lt__(self, other: tuple) -> bool:
        assert isinstance(other, Package), type(other)
        return self.sort_key < other.sort_key

    @property
    def sort_key(self) -> Tuple[str, packaging.version.Version, str]:
        """Sort key for a filename."""
        return (
            self.name,
            packaging.version.parse(self.version or '0'),

            # This looks ridiculous, but it's so that like extensions sort
            # together when the name and version are the same (otherwise it
            # depends on how the filename is normalized, which means sometimes
            # wheels sort before tarballs, but not always).
            # Alternatively we could just grab the extension, but that's less
            # amusing, even though it took 6 lines of comments to explain this.
            self.filename[::-1],
        )

    @property
    def formatted_upload_time(self) -> str:
        assert self.upload_timestamp is not None
        return _format_datetime(datetime.fromtimestamp(self.upload_timestamp))

    @property
    def info_string(self) -> str:
        # TODO: I'd like to remove this "info string" and instead format things
        # nicely for humans (e.g. in a table or something).
        #
        # This might mean changing the web interface to use different pages for
        # humans than the /simple/ ones it currently links to. (Even if pip can
        # parse links from a <table>, it might add significantly more bytes.)
        info = self.version or 'unknown version'
        if self.upload_timestamp is not None:
            info += f', {self.formatted_upload_time}'
        if self.uploaded_by is not None:
            info += f', {self.uploaded_by}'
        return info

    def url(self, base_url: str) -> str:
        return f'{base_url.rstrip("/")}/{self.filename}'

    @classmethod
    def create(
            cls,
            *,
            filename: str,
            hash: Optional[str] = None,
            upload_timestamp: Optional[int] = None,
            uploaded_by: Optional[str] = None,
    ) -> 'Package':
        if not re.match('[a-zA-Z0-9_\-\.]+$', filename) or '..' in filename:
            raise ValueError('Unsafe package name: {}'.format(filename))

        name, version = guess_name_version_from_filename(filename)
        return cls(
            filename=filename,
            name=packaging.utils.canonicalize_name(name),
            version=version,
            hash=hash,
            upload_timestamp=upload_timestamp,
            uploaded_by=uploaded_by,
        )


@contextlib.contextmanager
def atomic_write(path: str) -> Generator[IO[str], None, None]:
    tmp = tempfile.mktemp(
        prefix='.' + os.path.basename(path),
        dir=os.path.dirname(path),
    )
    try:
        with open(tmp, 'w') as f:
            yield f
    except BaseException:
        os.remove(tmp)
        raise
    else:
        os.rename(tmp, path)


def _format_datetime(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


# TODO: at some point there will be so many options we'll want to make a config
# object or similar instead of adding more arguments here
def build_repo(
        packages: Dict[str, Set[Package]],
        output_path: str,
        packages_url: str,
        title: str,
        logo: str,
        logo_width: int,
) -> None:
    simple = os.path.join(output_path, 'simple')
    os.makedirs(simple, exist_ok=True)

    current_date = _format_datetime(datetime.now())

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
        # /simple/{package}/index.html
        simple_package_dir = os.path.join(simple, package_name)
        os.makedirs(simple_package_dir, exist_ok=True)
        with atomic_write(os.path.join(simple_package_dir, 'index.html')) as f:
            f.write(jinja_env.get_template('package.html').render(
                date=current_date,
                package_name=package_name,
                versions=sorted(
                    versions,
                    key=operator.attrgetter('sort_key'),
                    # Newer versions should sort first.
                    reverse=True,
                ),
                packages_url=packages_url,
            ))


def _lines_from_path(path: str) -> List[str]:
    f = sys.stdin if path == '-' else open(path)
    return f.read().splitlines()


def _create_packages(
        package_infos: Iterator[Dict[str, Any]],
) -> Dict[str, Set[Package]]:
    packages: Dict[str, Set[Package]] = collections.defaultdict(set)
    for package_info in package_infos:
        try:
            package = Package.create(**package_info)
        except ValueError as ex:
            # TODO: this should really be optional; i'd prefer it to fail hard
            print('{} (skipping package)'.format(ex), file=sys.stderr)
        else:
            packages[package.name].add(Package.create(**package_info))

    return packages


def package_list(path: str) -> Dict[str, Set[Package]]:
    return _create_packages({'filename': line} for line in _lines_from_path(path))


def package_list_json(path: str) -> Dict[str, Set[Package]]:
    return _create_packages(json.loads(line) for line in _lines_from_path(path))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    package_input_group = parser.add_mutually_exclusive_group(required=True)
    package_input_group.add_argument(
        '--package-list',
        help='path to a list of packages (one per line)',
        type=package_list,
        dest='packages',
    )
    package_input_group.add_argument(
        '--package-list-json',
        help='path to a list of packages (one JSON object per line)',
        type=package_list_json,
        dest='packages',
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
        args.packages,
        args.output_dir,
        args.packages_url,
        args.title,
        args.logo,
        args.logo_width,
    )
    return 0


if __name__ == '__main__':
    exit(main())
