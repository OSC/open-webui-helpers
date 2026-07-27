# Define the dummy state file as your target
.pip_installed: requirements.txt
	pip3 install -r requirements.txt
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
