.PHONY: minimal
minimal: venv

venv: vendor/venv-update setup.py requirements-dev.txt
	vendor/venv-update venv= -ppython3 venv install= -rrequirements-dev.txt -e .


.PHONY: test
test: venv
	venv/bin/coverage erase
	venv/bin/coverage run -m pytest -v tests
	# TODO: add --fail-under 100
	venv/bin/coverage report --show-missing
	venv/bin/pre-commit install -f --install-hooks
	venv/bin/pre-commit run --all-files
