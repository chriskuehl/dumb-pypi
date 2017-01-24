"""A simple read-only PyPI static index server generator."""
import argparse
import collections
import operator
import os
import os.path
import re
import shutil
from datetime import datetime

import jinja2
from pip.wheel import Wheel


ARCHIVE_EXTENSIONS = frozenset((
    '.zip', '.tar.gz', '.tgz', '.tar.bz2', '.egg',
))
jinja_env = jinja2.Environment(
    loader=jinja2.PackageLoader('dumb_pypi', 'templates'),
    autoescape=True,
)


def normalize_package_name(name):
    name = name.lower()
    name = re.sub('[-_.]+', '-', name)
    return name


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
        # TODO: pkg_resources has a function for sorting versions correctly
        return (self.name, self.version, self.filename)

    @classmethod
    def from_path(cls, path):
        filename = os.path.basename(path)
        _, ext = os.path.splitext(filename)

        if ext == '.whl':
            wheel = Wheel(filename)
            return cls(
                path=path,
                name=wheel.name,
                version=wheel.version,
            )
        else:
            for e in ARCHIVE_EXTENSIONS:
                if not filename.endswith(e):
                    continue

                # these aren't well structured, so this is best-effort
                name = filename[0:-len(e)]
                if '-' not in name:
                    name, version = name, None
                else:
                    name, version = name.rsplit('-', 1)

                name = normalize_package_name(name)

                return cls(
                    path=path,
                    name=name,
                    version=version,
                )
            else:
                raise NotImplementedError(
                    'Not sure how to parse filename: {}'.format(
                        filename,
                    ),
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
