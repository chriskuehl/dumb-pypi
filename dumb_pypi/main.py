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
import hashlib
import jinja2
import packaging.utils
import packaging.version
import pkg_resources
from pip.wheel import Wheel
import tarfile
from zipfile import ZipFile
from graphviz import Digraph
import subprocess


jinja_env = jinja2.Environment(
    loader=jinja2.PackageLoader('dumb_pypi', 'templates'),
    autoescape=True,
)

def emailParser(input):
    return_value = []
    users = input.split(',')
    for user in users:
        return_value.append('<a href="mailto:%s">%s</a>' % (user, user))
    return ', '.join(return_value)

def dependencyParser(input):
    if input in local_projects:
        link = '../%s' % input
    else:
        link = 'https://pypi.python.org/pypi/%s' % input
    return '<a href="%s">%s</a>' % (link, input)

def linkParser(input):
    return '<a href="%s">%s</a>' % (input, input)

def hasKey(input, key):
    return input.get(key, None) is not None

jinja_env.filters['emailParser'] = emailParser
jinja_env.filters['linkParser'] = linkParser
jinja_env.filters['hasKey'] = hasKey
jinja_env.filters['dependencyParser'] = dependencyParser

def remove_extension(name):
    if name.endswith(('gz', 'bz2')):
        name, _ = name.rsplit('.', 1)
    name, _ = name.rsplit('.', 1)
    return name

def md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

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
            raise ValueError(f'Invalid package name: {filename}')

        # impossible
        assert version is None or len(version) > 0, version

        return name, version


local_projects = set()


class Package(collections.namedtuple('Package', (
    'filename',
    'name',
    'original_source_path',
    'path',
    'version',
    'hash',
    'upload_timestamp',
    'uploaded_by'
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

    @property
    def formatted_upload_time(self):
        return _format_datetime(datetime.fromtimestamp(self.upload_timestamp))

    @property
    def info_string(self):
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

    def url(self, base_url):
        return f'{base_url.rstrip("/")}/{self.path}'

    def _get_metadata(self, path):
        return_info = {}
        with open(os.path.join(path), 'r') as f:
            for line in f.readlines():
                line = line.strip('\n')
                attribute = line.split(':')[0]
                value = line.replace(attribute + ':', '').strip()
                attribute = attribute.replace('-', '_').lower()
                if not return_info.get(attribute, None):
                    return_info[attribute] = []
                return_info[attribute].append(value)
        return return_info


    @property
    def update_info(self):
        return_info = {}
        deps = []
        info_found = False
        if not self.original_source_path:
            return
        if not os.path.exists(self.original_source_path):
            return
        tmp = tempfile.mktemp()
        if self.original_source_path.endswith('.whl'):
            zipFile = ZipFile(self.original_source_path)
            for member in zipFile.namelist():
                if member.endswith('METADATA'):
                    zipFile.extract(member, tmp)
                    return_info = self._get_metadata(os.path.join(tmp, member))
                if 'metadata.json' in member:
                    zipFile.extract(member, tmp)
                    with open(os.path.join(tmp, member), 'r') as f:
                        row_data = json.loads(f.read())
                        deps = row_data['run_requires'][0].get('requires',[])
        else:
            tar = tarfile.open(self.original_source_path)
            for member in tar.getmembers():
                if 'PKG-INFO' in member.name and not info_found: # PKG-INFO is also in the egg-info
                    tar.extract(member, tmp)
                    return_info = self._get_metadata(
                            os.path.join(tmp, member.name))
                    info_found = True
                if 'requires' in member.name:
                    tar.extract(member, tmp)
                    with open(os.path.join(tmp, member.name), 'r') as f:
                        for line in f.readlines():
                            line = line.strip('\n')
                            deps.append(line)
        return_info['dependencies'] = [x.lower() for x in deps]
        return return_info

    @classmethod
    def create(
            cls,
            *,
            filename,
            path=None,
            hash=None,
            upload_timestamp=None,
            uploaded_by=None,
            original_source_path=None
    ):
        if not re.match('[a-zA-Z0-9_\-\.]+$', filename) or '..' in filename:
            raise ValueError('Unsafe package name: {}'.format(filename))

        name, version = guess_name_version_from_filename(filename)
        local_projects.add(name)
        return cls(
            filename=filename,
            name=packaging.utils.canonicalize_name(name),
            version=version,
            path=path,
            original_source_path=original_source_path,
            hash=hash,
            upload_timestamp=upload_timestamp,
            uploaded_by=uploaded_by
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
    except BaseException:
        os.remove(tmp)
        raise
    else:
        os.rename(tmp, path)


def _format_datetime(dt):
    return dt.strftime('%Y-%m-%d %H:%M:%S')


# TODO: at some point there will be so many options we'll want to make a config
# object or similar instead of adding more arguments here
def build_repo(packages, output_path, packages_url, title, logo, logo_width):
    simple = os.path.join(output_path, 'simple')
    os.makedirs(simple, exist_ok=True)
    dot = Digraph()
    nodes = {}
    current_date = _format_datetime(datetime.now())

    # /index.html
    with atomic_write(os.path.join(output_path, 'index.html')) as f:
        f.write(jinja_env.get_template('index.html').render(
            title=title,
            packages=sorted(
                (
                    package,
                    sorted(packages[package])[-1],
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
        versions = sorted(
                    versions,
                    key=operator.attrgetter('sort_key'),
                    # Newer versions should sort first.
                    reverse=True,
                )
        deps = versions[0].update_info['dependencies']
        if not nodes.get(package_name, None):
            nodes[package_name] = []
        for dep in deps:
            if not nodes.get(dep, None):
                nodes[dep] = []
            nodes[package_name].append(dep)
        # /simple/{package}/index.html
        with atomic_write(os.path.join(package_dir, 'index.html')) as f:
            f.write(jinja_env.get_template('package.html').render(
                date=current_date,
                package_name=package_name,
                versions=versions,
                packages_url=packages_url,
            ))
    for node in nodes.keys():
        dot.node(node)
        for link in nodes[node]:
            dot.edge(node, link)
    output_path_dot = '%s/deps.dot' % output_path
    output_path_png = open('%s/deps.png' % output_path, 'w')
    dot.save(output_path_dot)
    subprocess.call(['dot','-Tpng', output_path_dot], stdout=output_path_png)

def _lines_from_path(path):
    f = sys.stdin if path == '-' else open(path)
    return f.read().splitlines()


def _create_packages(package_infos):
    packages = collections.defaultdict(set)
    for package_info in package_infos:
        try:
            package = Package.create(**package_info)
        except ValueError as ex:
            # TODO: this should really be optional; i'd prefer it to fail hard
            print('{} (skipping package)'.format(ex), file=sys.stderr)
        else:
            packages[package.name].add(Package.create(**package_info))

    return packages


def package_list_from_path(path):
    if not path.endswith('/'):
        path = path + '/'
    files_name = []
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            if os.path.isfile(os.path.join(root, name)) and name.endswith(
                    ('tar.gz', 'tar.bz2', 'whl')):
                files_name.append({
                    'filename': name,
                    'path': os.path.join(root.replace(path, ''), name),
                })
    return _create_packages({'filename': line['filename'],
                             'hash': md5(os.path.join(path, line['path'])),
                             'path': line['path'],
                             'original_source_path':os.path.join(path,
                                                                 line['path'])}
                            for line in files_name)


def package_list(path):
    return _create_packages({'filename': line} for line in _lines_from_path(path))


def package_list_json(path):
    return _create_packages(json.loads(line) for line in _lines_from_path(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)

    package_input_group = parser.add_mutually_exclusive_group(required=True)
    package_input_group.add_argument(
        '--package-list',
        help='path to a list of packages (one per line)',
        type=package_list,
        dest='packages',
    )
    package_input_group.add_argument(
        '--package-path-folder',
        help='path to folder of packages',
        type=package_list_from_path,
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


if __name__ == '__main__':
    exit(main())
