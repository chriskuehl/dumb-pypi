import pytest

from dumb_pypi import main


@pytest.mark.parametrize(('filename', 'name', 'version'), (
    # wheels
    ('dumb_init-1.2.0-py2.py3-none-manylinux1_x86_64.whl', 'dumb-init', '1.2.0'),
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
        main.Package.from_filename(filename, '../../pool/')


def test_build_repo_smoke_test(tmpdir):
    main.build_repo(
        frozenset(('ocflib-2016.12.10.1.48-py2.py3-none-any.whl',)),
        tmpdir.strpath,
        '../../pool/',
        'My Private PyPI',
    )
    assert tmpdir.join('simple').check(dir=True)
    assert tmpdir.join('simple', 'index.html').check(file=True)
    assert tmpdir.join('simple', 'ocflib').check(dir=True)
    assert tmpdir.join('simple', 'ocflib', 'index.html').check(file=True)


def test_build_repo_even_with_bad_package_names(tmpdir):
    main.build_repo(
        frozenset((
            '..',
            '/blah-2.tar.gz',
            'lol-2.tar.gz/../',
            'ocflib-2016.12.10.1.48-py2.py3-none-any.whl',
        )),
        tmpdir.strpath,
        '../../pool/',
        'My Private PyPI',
    )
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
