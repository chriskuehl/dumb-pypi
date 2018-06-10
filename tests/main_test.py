import json

import pytest

from dumb_pypi import main


@pytest.mark.parametrize(('filename', 'name', 'version'), (
    # wheels
    ('dumb_init-1.2.0-py2.py3-none-manylinux1_x86_64.whl', 'dumb_init', '1.2.0'),
    ('ocflib-2016.12.10.1.48-py2.py3-none-any.whl', 'ocflib', '2016.12.10.1.48'),
    ('aspy.yaml-0.2.2-py2.py3-none-any.whl', 'aspy.yaml', '0.2.2'),
    (
        'numpy-1.11.1rc1-cp27-cp27m-macosx_10_6_intel.macosx_10_9_intel.macosx_10_9_x86_64.macosx_10_10_intel.macosx_10_10_x86_64.whl',  # noqa
        'numpy',
        '1.11.1rc1',
    ),

    # other stuff
    ('aspy.yaml.zip', 'aspy.yaml', None),
    ('ocflib-3-4.tar.gz', 'ocflib-3-4', None),
    ('aspy.yaml-0.2.1.tar.gz', 'aspy.yaml', '0.2.1'),
    ('numpy-1.11.0rc1.tar.gz', 'numpy', '1.11.0rc1'),
    ('pandas-0.2beta.tar.gz', 'pandas', '0.2beta'),
    ('scikit-learn-0.15.1.tar.gz', 'scikit-learn', '0.15.1'),
    ('ocflib-2015.11.23.20.2.tar.gz', 'ocflib', '2015.11.23.20.2'),
    ('mesos.cli-0.1.3-py2.7.egg', 'mesos.cli', '0.1.3-py2.7'),

    # inspired by pypiserver's tests
    ('flup-123-1.0.3.dev-20110405.tar.gz', 'flup-123', '1.0.3.dev-20110405'),
    ('package-123-1.3.7+build.11.e0f985a.zip', 'package-123', '1.3.7+build.11.e0f985a'),
))
def test_guess_name_version_from_filename(filename, name, version):
    assert main.guess_name_version_from_filename(filename) == (name, version)


@pytest.mark.parametrize(('filename', 'name', 'version'), (
    ('dumb-init-0.1.0.linux-x86_64.tar.gz', 'dumb-init', '0.1.0'),
    ('greenlet-0.3.4-py3.1-win-amd64.egg', 'greenlet', '0.3.4'),
    ('numpy-1.7.0.win32-py3.1.exe', 'numpy', '1.7.0'),
    ('surf.sesame2-0.2.1_r291-py2.5.egg', 'surf.sesame2', '0.2.1_r291'),
))
def test_guess_name_version_from_filename_only_name(filename, name, version):
    """Broken version check tests.

    The real important thing is to be able to parse the name, but it's nice if
    we can parse the versions too. Unfortunately, we can't yet for these cases.
    """
    parsed_name, parsed_version = main.guess_name_version_from_filename(filename)
    assert parsed_name == name

    # If you can make this assertion fail, great! Move it up above!
    assert parsed_version != version


@pytest.mark.parametrize('filename', (
    '',
    'lol',
    'lol-sup',
    '-20160920.193125.zip',
    'playlyfe-0.1.1-2.7.6-none-any.whl',  # 2.7.6 is not a valid python tag
))
def test_guess_name_version_from_filename_invalid(filename):
    with pytest.raises(ValueError):
        main.guess_name_version_from_filename(filename)


@pytest.mark.parametrize('filename', (
    '',
    'lol',
    'lol-sup',
    '-20160920.193125.zip',
    '..',
    '/blah-2.tar.gz',
    'lol-2.tar.gz/../',
))
def test_package_invalid(filename):
    with pytest.raises(ValueError):
        main.Package.create(filename=filename)


def test_package_url_no_hash():
    package = main.Package.create(filename='f.tar.gz')
    assert package.url('/prefix') == '/prefix/f.tar.gz'


def test_package_url_with_hash():
    package = main.Package.create(filename='f.tar.gz', hash='sha256=badf00d')
    assert package.url('/prefix') == '/prefix/f.tar.gz#sha256=badf00d'


def test_package_info_all_info():
    package = main.Package.create(
        filename='f-1.0.tar.gz',
        hash='sha256=deadbeef',
        upload_timestamp=1528586805,
    )
    ret = package.json_info('/prefix')
    assert ret == {
        'digests': {'sha256': 'deadbeef'},
        'filename': 'f-1.0.tar.gz',
        'url': '/prefix/f-1.0.tar.gz',
        'upload_time': '2018-06-09 23:26:45',
    }


def test_package_info_minimal_info():
    ret = main.Package.create(filename='f-1.0.tar.gz').json_info('/prefix')
    assert ret == {'filename': 'f-1.0.tar.gz', 'url': '/prefix/f-1.0.tar.gz'}


def test_package_json_excludes_non_versioned_packages():
    pkgs = [main.Package.create(filename='f.tar.gz')]
    ret = main._package_json(pkgs, '/prefix')
    assert ret == {
        'info': {'name': 'f', 'version': None},
        'releases': {},
        'urls': [],
    }


def test_package_json_packages_with_info():
    pkgs = [
        main.Package.create(filename='f-2.0.tar.gz'),
        main.Package.create(filename='f-1.0-py2.py3-none-any.whl'),
        main.Package.create(filename='f-1.0.tar.gz'),
    ]
    ret = main._package_json(pkgs, '/prefix')
    assert ret == {
        'info': {'name': 'f', 'version': '2.0'},
        'releases': {
            '2.0': [
                {
                    'filename': 'f-2.0.tar.gz',
                    'url': '/prefix/f-2.0.tar.gz',
                },
            ],
            '1.0': [
                {
                    'filename': 'f-1.0-py2.py3-none-any.whl',
                    'url': '/prefix/f-1.0-py2.py3-none-any.whl',
                },
                {
                    'filename': 'f-1.0.tar.gz',
                    'url': '/prefix/f-1.0.tar.gz',
                },
            ],
        },
        'urls': [
            {
                'filename': 'f-2.0.tar.gz',
                'url': '/prefix/f-2.0.tar.gz',
            },
        ],
    }


def test_build_repo_smoke_test(tmpdir):
    package_list = tmpdir.join('package-list')
    package_list.write('ocflib-2016.12.10.1.48-py2.py3-none-any.whl\n')
    main.main((
        '--package-list', package_list.strpath,
        '--output-dir', tmpdir.strpath,
        '--packages-url', '../../pool/',
    ))
    assert tmpdir.join('simple').check(dir=True)
    assert tmpdir.join('simple', 'index.html').check(file=True)
    assert tmpdir.join('simple', 'ocflib').check(dir=True)
    assert tmpdir.join('simple', 'ocflib', 'index.html').check(file=True)


def test_build_repo_json_smoke_test(tmpdir):
    package_list = tmpdir.join('package-list')
    package_list.write('\n'.join((
        json.dumps(info) for info in (
            {
                'filename': 'ocflib-2016.12.10.1.48-py2.py3-none-any.whl',
                'uploaded_by': 'ckuehl',
                'upload_timestamp': 1515783971,
                'hash': 'md5=b1946ac92492d2347c6235b4d2611184',
            },
            {
                'filename': 'numpy-1.11.0rc1.tar.gz',
                'upload_timestamp': 1515783971,
            },
            {
                'filename': 'scikit-learn-0.15.1.tar.gz',
            },
        )
    )) + '\n')
    main.main((
        '--package-list-json', package_list.strpath,
        '--output-dir', tmpdir.strpath,
        '--packages-url', '../../pool/',
    ))
    assert tmpdir.join('simple').check(dir=True)
    assert tmpdir.join('simple', 'index.html').check(file=True)
    assert tmpdir.join('simple', 'ocflib').check(dir=True)
    assert tmpdir.join('simple', 'ocflib', 'index.html').check(file=True)


def test_build_repo_no_generate_timestamp(tmpdir):
    package_list = tmpdir.join('package-list')
    package_list.write('pkg-1.0.tar.gz\n')
    main.main((
        '--package-list', package_list.strpath,
        '--output-dir', tmpdir.strpath,
        '--packages-url', '../../pool',
        '--no-generate-timestamp',
    ))
    for p in ('simple/index.html', 'simple/pkg/index.html'):
        assert 'Generated on' not in tmpdir.join(p).read()


def test_build_repo_even_with_bad_package_names(tmpdir):
    package_list = tmpdir.join('package-list')
    package_list.write('\n'.join((
        '..',
        '/blah-2.tar.gz',
        'lol-2.tar.gz/../',
        'ocflib-2016.12.10.1.48-py2.py3-none-any.whl',
        '',
    )))
    main.main((
        '--package-list', package_list.strpath,
        '--output-dir', tmpdir.strpath,
        '--packages-url', '../../pool/',
    ))
    assert tmpdir.join('simple').check(dir=True)
    assert tmpdir.join('simple', 'index.html').check(file=True)
    assert tmpdir.join('simple', 'ocflib').check(dir=True)
    assert tmpdir.join('simple', 'ocflib', 'index.html').check(file=True)


def test_atomic_write(tmpdir):
    a = tmpdir.join('a')
    a.write('sup')
    with main.atomic_write(a.strpath) as f:
        f.write('lol')
    assert a.read() == 'lol'


def test_atomic_write_exception(tmpdir):
    a = tmpdir.join('a')
    a.write('sup')
    with pytest.raises(ValueError):
        with main.atomic_write(a.strpath) as f:
            f.write('lol')
            f.flush()
            raise ValueError('sorry buddy')
    assert a.read() == 'sup'


def test_sorting():
    test_packages = [
        main.Package.create(filename=name)
        for name in (
            'fluffy-server-1.2.0.tar.gz',
            'fluffy_server-1.1.0-py2.py3-none-any.whl',
            'wsgi-mod-rpaf-2.0.0.tar.gz',
            'fluffy-server-10.0.0.tar.gz',
            'aspy.yaml-0.2.1.tar.gz',
            'wsgi-mod-rpaf-1.0.1.tar.gz',
            'aspy.yaml-0.2.1-py3-none-any.whl',
            'fluffy-server-1.0.0.tar.gz',
            'aspy.yaml-0.2.0-py2-none-any.whl',
            'fluffy_server-10.0.0-py2.py3-none-any.whl',
            'aspy.yaml-0.2.1-py2-none-any.whl',
            'fluffy-server-1.1.0.tar.gz',
            'fluffy_server-1.0.0-py2.py3-none-any.whl',
            'fluffy_server-1.2.0-py2.py3-none-any.whl',
        )
    ]
    sorted_names = [package.filename for package in sorted(test_packages)]
    assert sorted_names == [
        'aspy.yaml-0.2.0-py2-none-any.whl',
        'aspy.yaml-0.2.1-py2-none-any.whl',
        'aspy.yaml-0.2.1-py3-none-any.whl',
        'aspy.yaml-0.2.1.tar.gz',
        'fluffy_server-1.0.0-py2.py3-none-any.whl',
        'fluffy-server-1.0.0.tar.gz',
        'fluffy_server-1.1.0-py2.py3-none-any.whl',
        'fluffy-server-1.1.0.tar.gz',
        'fluffy_server-1.2.0-py2.py3-none-any.whl',
        'fluffy-server-1.2.0.tar.gz',
        'fluffy_server-10.0.0-py2.py3-none-any.whl',
        'fluffy-server-10.0.0.tar.gz',
        'wsgi-mod-rpaf-1.0.1.tar.gz',
        'wsgi-mod-rpaf-2.0.0.tar.gz',
    ]
