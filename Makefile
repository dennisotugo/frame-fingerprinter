# Common development targets for frame-fingerprinter
#
# Usage:
#   make install     Install the package and all dependencies
#   make dev         Install in editable mode with dev dependencies
#   make test        Run the full test suite
#   make clean       Remove build / cache artefacts
#   make help        Show this message

PYTHON ?= python3
PIP    ?= $(PYTHON) -m pip

.PHONY: all install dev test clean help

all: help

## install: Install the package (production mode)
install:
	$(PIP) install --upgrade pip
	$(PIP) install .

## dev: Install in editable mode with dev dependencies
dev:
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

## test: Run the full test suite
test:
	$(PYTHON) -m pytest tests/ -v

## clean: Remove Python build artefacts and cache directories
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true

## help: Show available targets
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'
