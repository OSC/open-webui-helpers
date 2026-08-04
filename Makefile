OPEN_WEBUI_VERSION := 0.10.2
SED := $(shell command -v gsed 2>/dev/null || echo sed)

# Define the dummy state file as your target
.pip_installed: requirements.txt requirements-openwebui.txt
	pip3 install -r requirements.txt -r requirements-openwebui.txt open-webui==$(OPEN_WEBUI_VERSION)
	touch .pip_installed

# Create a clean, user-friendly shortcut for daily terminal use
.PHONY: install
install: .pip_installed

.PHONY: lint
lint: install
	ruff check .

.PHONY: test
test: install
	python -m pytest --cov=filters --cov-report term-missing

.PHONY: format
format: install
	black filters/ tests/

.PHONY: check-format
check-format: install
	black --check filters tests

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
