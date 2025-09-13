# GitHub Actions Workflows

This directory contains GitHub Actions workflows for automated testing, building, and publishing of the quantik-core package.

## Workflows

### 1. `test.yml` - Comprehensive Testing
- **Trigger**: Push to main/develop, Pull requests
- **Matrix**: Tests across multiple OS (Ubuntu, Windows, macOS) and Python versions (3.10-3.13)
- **Features**:
  - Linting with flake8
  - Code formatting check with black
  - Type checking with mypy
  - Unit tests with pytest and coverage reporting
  - Coverage upload to Codecov

### 2. `integration.yml` - Integration Testing
- **Trigger**: Push to main/develop, Pull requests
- **Purpose**: Tests real-world package installation and usage
- **Features**:
  - Tests package build and wheel installation
  - Validates basic import and functionality
  - Tests optional CBOR functionality
  - Runs example scripts

### 3. `build.yml` - Build Verification
- **Trigger**: Push to main/develop, Pull requests
- **Purpose**: Ensures package builds correctly
- **Features**:
  - Builds source distribution and wheel
  - Validates package with twine check
  - Tests installation across multiple platforms
  - Uploads build artifacts

### 4. `publish.yml` - Automated Publishing
- **Trigger**: GitHub release creation
- **Purpose**: Automatically publishes to PyPI on releases
- **Features**:
  - Runs tests before publishing
  - Uses trusted publishing (recommended) or API tokens
  - Only runs on successful test completion

## Setup Requirements

### For Codecov (Optional)
1. Sign up at https://codecov.io
2. Connect your GitHub repository
3. No additional secrets needed (uses GitHub token)

### For PyPI Publishing

#### Option A: Trusted Publishing (Recommended)
1. Go to your PyPI project settings
2. Add GitHub as a trusted publisher
3. Configure: `owner/repo`, workflow: `publish.yml`, environment: `pypi`

#### Option B: API Tokens
1. Generate a PyPI API token
2. Add it as a GitHub secret: `PYPI_API_TOKEN`
3. Uncomment the token configuration in `publish.yml`

## Usage

1. **Push code** → Triggers test, integration, and build workflows
2. **Create PR** → All workflows run for validation
3. **Create release** → Publishes to PyPI automatically

## Local Development

Run the same checks locally:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v --cov=quantik_core

# Check formatting
black --check .

# Lint code
flake8 .

# Type check
mypy src/quantik_core/

# Build package
python -m build

# Check package
twine check dist/*
```
