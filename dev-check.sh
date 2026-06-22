#!/usr/bin/env bash

# Development check script for quantik-core-py
# This script sets up the development environment and runs all quality checks

set -euo pipefail

# Check if .venv folder exists
if [ ! -d ".venv" ]; then
    # Create virtual environment
    python -m venv .venv

    # Install development dependencies
    .venv/bin/python -m pip install -e ".[dev,cbor]"
fi

PYTHON=".venv/bin/python"

# Run pytest with coverage
"${PYTHON}" -m pytest tests/ -v --cov=quantik_core

# Check code formatting with black
"${PYTHON}" -m black --check --diff src tests examples validate_qfen_fixtures.py

# Run flake8 linting (critical errors only)
"${PYTHON}" -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Run flake8 linting (full check with warnings)
"${PYTHON}" -m flake8 . --count --exit-zero --statistics

# Run mypy type checking
"${PYTHON}" -m mypy src/quantik_core/

# Build the package
"${PYTHON}" -m build

# Check package with twine
"${PYTHON}" -m twine check dist/*
