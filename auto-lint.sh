#!/usr/bin/env bash
set -euo pipefail

activate_venv() {
    if [ ! -d ".venv" ]; then
        python -m venv .venv
        source .venv/bin/activate
        pip install -e ".[dev,cbor]"
    else
        source .venv/bin/activate
    fi
}

lint() {
    autopep8 --in-place --aggressive --aggressive ./examples/*.py ./src/**/*.py ./tests/**/*.py
    black ./examples ./src ./tests
}

activate_venv
lint