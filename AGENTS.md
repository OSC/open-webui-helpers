# Agent Guidelines

## Running Tests

To run all tests, use:

```bash
make test
```

This will run the full test suite including all filter tests.

## Post-Task Checklist

After completing any development task, run the following commands to ensure code quality:

```bash
make test    # Run all tests and show test coverage
make lint    # Run linting checks
make format  # Format code
```

These commands ensure:
- All tests pass
- All code had test coverage from `make test` output
- Code follows linting standards
- Code is properly formatted

## Test Files

### Accounting Filter (`tests/filters/test_accounting.py`)
- Tests for `get_request_account`, `get_usage`, `get_metrics`, `send_metrics`, `send_error_metric`
- Tests for `inlet` and `outlet` methods

### Backend Check Filter (`tests/filters/test_backend_check.py`)
- Tests for `inlet` method covering:
  - Models found successfully
  - Model not found with wait enabled and scale up then found
  - Model not found with wait disabled (raises exception)
  - Model not found with wait enabled but scale up then not found (raises exception)
  - Query of models fails (raises exception)
  - Request from WebUI returns body directly