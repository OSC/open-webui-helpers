OPEN_WEBUI_VERSION := 0.11.3
SED := $(shell command -v gsed 2>/dev/null || echo sed)
# 1. Define the potential path to the virtual environment interpreter
VENV_PYTHON := .venv/bin/python
VENV_PIP := .venv/bin/pip3
VENV_RUFF := .venv/bin/ruff
VENV_BLACK := .venv/bin/black

# 2. Check if the venv python executable exists; choose the appropriate interpreter
PYTHON := $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python)
PIP := $(if $(wildcard $(VENV_PIP)),$(VENV_PIP),pip3)
RUFF := $(if $(wildcard $(VENV_RUFF)),$(VENV_RUFF),ruff)
BLACK := $(if $(wildcard $(VENV_BLACK)),$(VENV_BLACK),black)

# Define the dummy state file as your target
.pip_installed: requirements.txt requirements-openwebui.txt
	$(PIP) install -r requirements.txt -r requirements-openwebui.txt open-webui==$(OPEN_WEBUI_VERSION)
	touch .pip_installed

# Create a clean, user-friendly shortcut for daily terminal use
.PHONY: install
install: .pip_installed

.PHONY: lint
lint: install
	$(RUFF) check .

.PHONY: test
test: install
	$(PYTHON) -m pytest --cov=filters --cov-report term-missing

.PHONY: format
format: install
	$(BLACK) filters/ tests/

.PHONY: check-format
check-format: install
	$(BLACK) --check filters tests

.PHONY: update-requirements
update-requirements:
	docker run --rm -i ghcr.io/open-webui/open-webui:$(OPEN_WEBUI_VERSION) pip freeze > requirements-openwebui.txt
	$(SED) -i 's/\+cpu//g' requirements-openwebui.txt

.PHONY: check-requirements
check-requirements: update-requirements
	git diff --exit-code

.PHONY: print-python-version
print-python-version:
	docker run --rm -it ghcr.io/open-webui/open-webui:$(OPEN_WEBUI_VERSION) python --version
