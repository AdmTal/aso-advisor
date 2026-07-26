.PHONY: help install test lint fix check example clean build

help:
	@echo "install   install the package with the development extras"
	@echo "test      run the tests"
	@echo "lint      run ruff"
	@echo "fix       run ruff with --fix"
	@echo "check     lint, test, and audit the example workspace"
	@echo "example   audit the example workspace"
	@echo "build     build the wheel and the source distribution"
	@echo "clean     remove the build output and the caches"

install:
	pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check src tests

fix:
	ruff check --fix src tests

example:
	aso --workspace examples/trailwise audit --no-state --no-report

check: lint test example

build:
	python -m build

clean:
	rm -rf build dist *.egg-info .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
