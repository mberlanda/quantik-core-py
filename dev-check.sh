#!/usr/bin/env bash

# Development check script for quantik-core-py
# This script sets up the development environment and runs all quality checks

set -euo pipefail

# Check if .venv folder exists
if [ ! -d ".venv" ]; then
    # Create virtual environment
    python -m venv .venv
    
    # Activate virtual environment
    source .venv/bin/activate
    
    # Install development dependencies
    pip install -e ".[dev,cbor]"
else
    # Activate virtual environment
    source .venv/bin/activate
fi

# Run pytest with coverage
pytest tests/ -v --cov=quantik_core

# Check code formatting with black
black --diff .

# Run flake8 linting (critical errors only)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Run flake8 linting (full check with warnings)
flake8 . --count --exit-zero --statistics

# Run mypy type checking
mypy src/quantik_core/

# Build the package
python -m build

# Check package with twine
twine check dist/*
