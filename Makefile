.PHONY: minimal
minimal: venv

venv: vendor/venv-update setup.py requirements-dev.txt Makefile
	vendor/venv-update venv= -ppython3.6 venv install= -rrequirements-dev.txt -e .

.PHONY: test
test: venv
	venv/bin/coverage erase
	venv/bin/coverage run -m pytest -v tests
	venv/bin/coverage report --show-missing --fail-under 100
	venv/bin/pre-commit install -f --install-hooks
	venv/bin/pre-commit run --all-files

.PHONY: release
release: venv
	venv/bin/python setup.py sdist bdist_wheel
	venv/bin/twine upload --skip-existing dist/*

.PHONY: test-repo
test-repo: venv
	venv/bin/dumb-pypi \
		--package-list testing/package-list \
		--packages-url http://just.an.example/ \
		--output-dir test-repo \
		--logo https://i.fluffy.cc/tZRP1V8hdKCdrRQG5fBCv74M0VpcPLjP.svg \
		--logo-width 42

.PHONY: push-github-pages
push-github-pages: venv test-repo
	venv/bin/markdown-to-presentation push --source test-repo .
