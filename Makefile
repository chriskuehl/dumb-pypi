.PHONY: minimal
minimal: venv

venv: vendor/venv-update
	vendor/venv-update venv= -ppython3 venv install= -rrequirements-dev.txt -e .
