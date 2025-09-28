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
    autopep8 --in-place --aggressive --aggressive ./src/**/*.py ./tests/**/*.py
    black ./src ./tests
}

activate_venv
lint