"""A simple read-only PyPI static index server generator."""
import argparse
import collections
import contextlib
import itertools
import json
import math
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


CHANGELOG_ENTRIES_PER_PAGE = 5000


def remove_extension(name: str) -> str:
    if name.endswith(('gz', 'bz2')):
        name, _ = name.rsplit('.', 1)
    name, _ = name.rsplit('.', 1)
    return name


def guess_name_version_from_filename(
        filename: str,
) -> Tuple[str, Optional[str]]:
    if filename.endswith('.whl'):
        m = distlib.wheel.FILENAME_RE.match(filename)
        if m is not None:
            return m.group('nm'), m.group('vn')
        else:
            raise ValueError(f'Invalid package name: {filename}')
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
    parsed_version: packaging.version.Version
    hash: Optional[str]
    requires_python: Optional[str]
    upload_timestamp: Optional[int]
    uploaded_by: Optional[str]

    def __lt__(self, other: Tuple[Any, ...]) -> bool:
        assert isinstance(other, Package), type(other)
        return self.sort_key < other.sort_key

    @property
    def sort_key(self) -> Tuple[str, packaging.version.Version, str]:
        """Sort key for a filename."""
        return (
            self.name,
            self.parsed_version,

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
        dt = datetime.utcfromtimestamp(self.upload_timestamp)
        return _format_datetime(dt)

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

    def url(self, base_url: str, *, include_hash: bool = True) -> str:
        hash_part = f'#{self.hash}' if self.hash and include_hash else ''
        return f'{base_url.rstrip("/")}/{self.filename}{hash_part}'

    def json_info(self, base_url: str) -> Dict[str, Any]:
        ret: Dict[str, Any] = {
            'filename': self.filename,
            'url': self.url(base_url, include_hash=False),
            'requires_python': self.requires_python,
        }
        if self.upload_timestamp is not None:
            ret['upload_time'] = self.formatted_upload_time
        if self.hash is not None:
            algo, h = self.hash.split('=')
            ret['digests'] = {algo: h}
        return ret

    @classmethod
    def create(
            cls,
            *,
            filename: str,
            hash: Optional[str] = None,
            requires_python: Optional[str] = None,
            upload_timestamp: Optional[int] = None,
            uploaded_by: Optional[str] = None,
    ) -> 'Package':
        if not re.match(r'[a-zA-Z0-9_\-\.\+]+$', filename) or '..' in filename:
            raise ValueError(f'Unsafe package name: {filename}')

        name, version = guess_name_version_from_filename(filename)
        return cls(
            filename=filename,
            name=packaging.utils.canonicalize_name(name),
            version=version,
            parsed_version=packaging.version.parse(version or '0'),
            hash=hash,
            requires_python=requires_python,
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
        os.replace(tmp, path)


def _format_datetime(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def _package_json(files: List[Package], base_url: str) -> Dict[str, Any]:
    # https://warehouse.pypa.io/api-reference/json.html
    # note: the full api contains much more, we only output the info we have
    by_version: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for file in files:
        if file.version is not None:
            by_version[file.version].append(file.json_info(base_url))

    return {
        'info': {'name': files[0].name, 'version': files[0].version},
        'releases': by_version,
        'urls': by_version[files[0].version] if files[0].version else [],
    }


class Settings(NamedTuple):
    output_dir: str
    packages_url: str
    title: str
    logo: str
    logo_width: int
    generate_timestamp: bool


def build_repo(packages: Dict[str, Set[Package]], settings: Settings) -> None:
    simple = os.path.join(settings.output_dir, 'simple')
    pypi = os.path.join(settings.output_dir, 'pypi')
    current_date = _format_datetime(datetime.utcnow())

    jinja_env = jinja2.Environment(
        loader=jinja2.PackageLoader('dumb_pypi', 'templates'),
        autoescape=True,
    )
    jinja_env.globals['title'] = settings.title
    jinja_env.globals['packages_url'] = settings.packages_url
    jinja_env.globals['logo'] = settings.logo
    jinja_env.globals['logo_width'] = settings.logo_width

    # Sorting package versions is actually pretty expensive, so we do it once
    # at the start.
    sorted_packages = {name: sorted(files) for name, files in packages.items()}

    for package_name, sorted_files in sorted_packages.items():
        # /simple/{package}/index.html
        simple_package_dir = os.path.join(simple, package_name)
        os.makedirs(simple_package_dir, exist_ok=True)
        with atomic_write(os.path.join(simple_package_dir, 'index.html')) as f:
            f.write(jinja_env.get_template('package.html').render(
                date=current_date,
                generate_timestamp=settings.generate_timestamp,
                package_name=package_name,
                files=sorted_files,
                packages_url=settings.packages_url,
            ))

        # /pypi/{package}/json
        pypi_package_dir = os.path.join(pypi, package_name)
        os.makedirs(pypi_package_dir, exist_ok=True)
        with atomic_write(os.path.join(pypi_package_dir, 'json')) as f:
            json.dump(_package_json(sorted_files, settings.packages_url), f)

    # /simple/index.html
    os.makedirs(simple, exist_ok=True)
    with atomic_write(os.path.join(simple, 'index.html')) as f:
        f.write(jinja_env.get_template('simple.html').render(
            date=current_date,
            generate_timestamp=settings.generate_timestamp,
            package_names=sorted(sorted_packages),
        ))

    # /changelog
    changelog = os.path.join(settings.output_dir, 'changelog')
    os.makedirs(changelog, exist_ok=True)
    files_newest_first = sorted(
        itertools.chain.from_iterable(packages.values()),
        key=lambda package: (package.upload_timestamp or 0, package.filename),
        reverse=True,
    )
    page_count = math.ceil(len(files_newest_first) / CHANGELOG_ENTRIES_PER_PAGE)
    for page_idx, start_idx in enumerate(range(0, len(files_newest_first), CHANGELOG_ENTRIES_PER_PAGE)):
        chunk = files_newest_first[start_idx:start_idx + CHANGELOG_ENTRIES_PER_PAGE]
        page_number = page_idx + 1
        with atomic_write(os.path.join(changelog, f'page{page_number}.html')) as f:
            pagination_first = "page1.html" if page_number != 1 else None
            pagination_last = f"page{page_count}.html" if page_number != page_count else None
            pagination_prev = f"page{page_number - 1}.html" if page_number != 1 else None
            pagination_next = f"page{page_number + 1}.html" if page_number != page_count else None
            f.write(jinja_env.get_template('changelog.html').render(
                files_newest_first=chunk,
                page_number=page_number,
                page_count=page_count,
                pagination_first=pagination_first,
                pagination_last=pagination_last,
                pagination_prev=pagination_prev,
                pagination_next=pagination_next,
            ))

    # /index.html
    with atomic_write(os.path.join(settings.output_dir, 'index.html')) as f:
        f.write(jinja_env.get_template('index.html').render(
            packages=sorted(
                (
                    package,
                    sorted_versions[-1].version,
                )
                for package, sorted_versions in sorted_packages.items()
            ),
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
            print(f'{ex} (skipping package)', file=sys.stderr)
        else:
            packages[package.name].add(package)

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
    parser.add_argument(
        '--no-generate-timestamp',
        action='store_false', dest='generate_timestamp',
        help=(
            "Don't template creation timestamp in outputs.  This option makes "
            'the output repeatable.'
        ),
    )
    args = parser.parse_args(argv)

    settings = Settings(
        output_dir=args.output_dir,
        packages_url=args.packages_url,
        title=args.title,
        logo=args.logo,
        logo_width=args.logo_width,
        generate_timestamp=args.generate_timestamp,
    )
    build_repo(args.packages, settings)
    return 0


if __name__ == '__main__':
    exit(main())
