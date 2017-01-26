.PHONY: minimal
minimal: venv

venv: vendor/venv-update setup.py requirements-dev.txt
	vendor/venv-update venv= -ppython3 venv install= -rrequirements-dev.txt -e .


.PHONY: test
test: venv
	venv/bin/py.test -v tests
