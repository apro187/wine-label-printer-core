VENV=.venv
PYTHON=${VENV}/bin/python
PIP=${VENV}/bin/pip

.PHONY: venv install test clean

venv:
	python3 -m venv ${VENV}
	${PIP} install --upgrade pip

install: venv
	${PIP} install -e .
	${PIP} install -r requirements.txt

test:
	${PYTHON} -m pytest -q tests

clean:
	rm -rf ${VENV} build dist *.egg-info
