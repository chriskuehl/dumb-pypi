import pytest

from dumb_pypi import main


@pytest.mark.parametrize(('name', 'expected'), (
    ('setuptools', 'setuptools'),
    ('dumb-in-it', 'dumb-in-it'),
    ('dumb_in_it', 'dumb-in-it'),
    ('aspy.yaml_lol', 'aspy-yaml-lol'),
))
def test_normalize_package_name(name, expected):
    assert main.normalize_package_name(name) == expected
