# Contributing to frame-fingerprinter

Thank you for your interest in contributing!

## Development setup

```bash
# 1. Clone the repo
git clone https://github.com/dennisotugo/frame-fingerprinter.git
cd frame-fingerprinter

# 2. Install in editable mode with dev dependencies
make dev
# or manually:
pip install -e ".[dev]"

# 3. Run the tests
make test
```

## Running tests

```bash
# Full suite
pytest tests/ -v

# Single module
pytest tests/test_chain.py -v
```

All tests must pass before opening a pull request.

## Code style

- Follow PEP 8.
- Use type hints for all public functions.
- Keep docstrings up to date.
- Add tests for new functionality.

## Submitting a pull request

1. Fork the repository and create a feature branch.
2. Make your changes with appropriate tests.
3. Ensure all tests pass (`make test`).
4. Open a pull request against `main` with a clear description of the change.

## Reporting issues

Please use the [GitHub issue tracker](https://github.com/dennisotugo/frame-fingerprinter/issues).
