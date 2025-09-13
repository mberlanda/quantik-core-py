# Development Guide

This document provides instructions for setting up a local development environment for the Quantik Core library.

## Prerequisites

- Python 3.10 or higher
- Git

## Setting Up the Development Environment

### 1. Clone the Repository

```bash
git clone https://github.com/mberlanda/quantik-core-py.git
cd quantik-core-py
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

### 3. Activate the Virtual Environment

**On macOS/Linux:**
```bash
source .venv/bin/activate
```

**On Windows:**
```bash
.venv\Scripts\activate
```

### 4. Install Development Dependencies

Install the package in editable mode with all development dependencies:

```bash
pip install -e ".[dev,cbor]"
```

This installs:
- The core package in editable mode
- Development tools (pytest, black, flake8, mypy, etc.)
- Optional CBOR support

## Running Tests

### Basic Test Run

```bash
python -m pytest tests/ -v
```

### Run Tests with Coverage

```bash
python -m pytest tests/ -v --cov=quantik_core --cov-report=html
```

Coverage reports will be generated in the `htmlcov/` directory.

### Run Property-Based Tests

The test suite includes property-based tests using Hypothesis. To run more extensive property testing:

```bash
python -m pytest tests/ -v --hypothesis-show-statistics
```

## Code Quality

### Code Formatting

Format code using Black:

```bash
black src/ tests/
```

Check formatting without making changes:

```bash
black --check src/ tests/
```

### Linting

Run flake8 for style checking:

```bash
flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203,W503
```

### Type Checking

Run mypy for static type analysis:

```bash
mypy src/quantik_core/
```

## Development Workflow

### 1. Make Changes

Edit the code in `src/quantik_core/` and add corresponding tests in `tests/`.

### 2. Run Tests

Always run the test suite before committing:

```bash
python -m pytest tests/ -v
```

### 3. Check Code Quality

Format and lint your code:

```bash
black src/ tests/
flake8 src/ tests/ --max-line-length=88 --extend-ignore=E203,W503
```

### 4. Verify Installation

Test that the package can be imported correctly:

```bash
python -c "from quantik_core import State; print('Import successful')"
```

## Project Structure

```
quantik-core-py/
├── src/
│   └── quantik_core/
│       ├── __init__.py          # Package interface
│       └── core.py              # Core State implementation
├── tests/
│   └── test_core.py             # Comprehensive test suite
├── pyproject.toml               # Project configuration
├── README.md                    # User documentation
├── DEVELOPMENT.md               # This file
└── .gitignore                   # Git ignore rules
```

## Dependency Management

### Core Dependencies

The library has minimal runtime dependencies (only standard library modules).

### Optional Dependencies

- `cbor2`: For CBOR serialization support

### Development Dependencies

- `pytest`: Test framework
- `pytest-cov`: Coverage reporting
- `hypothesis`: Property-based testing
- `black`: Code formatting
- `flake8`: Linting
- `mypy`: Type checking
- `pre-commit`: Git hooks (optional)

### Installing Specific Dependency Groups

```bash
# Just development tools (no CBOR)
pip install -e ".[dev]"

# Just CBOR support
pip install -e ".[cbor]"

# Documentation tools
pip install -e ".[docs]"

# Everything
pip install -e ".[dev,cbor,docs,benchmark]"
```

## Performance Testing

### Basic Performance Check

```bash
python -c "
from quantik_core import State
import time

# Test canonicalization performance
state = State.from_qfen('A.b./..C./d..a/...B')
start = time.time()
for _ in range(1000):
    state.canonical_key()
elapsed = time.time() - start
print(f'1000 canonicalizations: {elapsed:.3f}s ({1000/elapsed:.0f} ops/sec)')
"
```

### Memory Usage

Check memory usage of core operations:

```bash
python -c "
from quantik_core import State
import sys

state = State.empty()
print(f'Empty state size: {sys.getsizeof(state)} bytes')
print(f'Binary representation: {len(state.pack())} bytes')
print(f'Canonical key: {len(state.canonical_key())} bytes')
"
```

## Debugging

### Enable Verbose Test Output

```bash
python -m pytest tests/ -v -s
```

### Run Specific Tests

```bash
# Run a specific test function
python -m pytest tests/test_core.py::test_pack_unpack_empty -v

# Run tests matching a pattern
python -m pytest tests/ -k "canonical" -v
```

### Debug CBOR Issues

```bash
python -c "
from quantik_core import State
state = State.from_qfen('A.../..../..../....')
try:
    cbor_data = state.to_cbor()
    print('CBOR serialization working')
except Exception as e:
    print(f'CBOR error: {e}')
"
```

## Contributing

### Before Submitting a Pull Request

1. Ensure all tests pass: `python -m pytest tests/ -v`
2. Check code coverage is >90%
3. Format code: `black src/ tests/`
4. Lint code: `flake8 src/ tests/`
5. Update documentation if needed
6. Add tests for new functionality

### Commit Message Guidelines

Use clear, descriptive commit messages:

```
feat: add canonical key caching for performance
fix: handle edge case in QFEN parsing
docs: update installation instructions
test: add property-based tests for symmetries
```

## Troubleshooting

### Common Issues

**Import Error:**
```bash
# Reinstall in editable mode
pip install -e .
```

**Test Failures:**
```bash
# Clean pytest cache
rm -rf .pytest_cache/
python -m pytest tests/ -v
```

**Coverage Issues:**
```bash
# Install coverage plugin
pip install pytest-cov
```

### Getting Help

- Check existing issues on GitHub
- Review the test suite for usage examples
- Consult the main README.md for API documentation

## Release Process

(For maintainers only)

1. Update version in `pyproject.toml`
2. Run full test suite with coverage
3. Update CHANGELOG.md
4. Create git tag
5. Build and publish to PyPI
