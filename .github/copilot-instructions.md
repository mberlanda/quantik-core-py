# GitHub Copilot Instructions

## Code Quality Standards

All generated code must comply with the following linting and formatting standards:

### Python Formatting
- **Black**: Code must pass `black --check .` without any formatting issues
- Use Black's default configuration (88 character line length for Black)
- Ensure consistent code formatting throughout the project

### Code Linting (Flake8)
- **Critical Errors**: Code must pass `flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
  - E9: Runtime syntax errors
  - F63: Invalid syntax in type comments
  - F7: Syntax errors in docstrings
  - F82: Undefined names in `__all__`
- **General Standards**: Follow `flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics`
  - Maximum line length: 127 characters
  - Maximum cyclomatic complexity: 10
  - All other flake8 warnings should be minimized

### Type Checking
- **MyPy**: Code must pass `mypy src/quantik_core/` without type errors
- Always include proper type hints for function parameters and return values
- Use appropriate type annotations for variables when type inference is unclear
- Import types from `typing` module when necessary

## Development Environment

### Virtual Environment
- Always assume the local virtual environment is activated: `source .venv/bin/activate`
- When suggesting commands or scripts, assume this environment is active
- Reference packages and dependencies as if running within the virtual environment

## Code Generation Guidelines

### General Principles
1. **Clean Code**: Write readable, maintainable code that follows Python best practices
2. **Type Safety**: Always include comprehensive type hints
3. **Documentation**: Include docstrings for all public functions, classes, and modules
4. **Error Handling**: Include appropriate exception handling where needed

### Specific Requirements
- Use double quotes for strings (Black default)
- Prefer f-strings for string formatting
- Use list/dict comprehensions where appropriate and readable
- Follow PEP 8 naming conventions
- Avoid overly complex functions (keep cyclomatic complexity ≤ 10)
- Break long lines appropriately to stay within 127 character limit

### Import Organization
- Group imports in the standard order: standard library, third-party, local imports
- Use absolute imports when possible
- Sort imports alphabetically within each group

### Function and Class Design
- Keep functions focused and single-purpose
- Use descriptive variable and function names
- Include type hints for all parameters and return values
- Add docstrings following Google or NumPy docstring conventions

## Testing Considerations
- When generating test code, ensure it also follows the same linting standards
- Include type hints in test functions
- Use descriptive test function names that explain what is being tested

## Example Code Structure

```python
from typing import Dict, List, Optional, Union
import logging

def process_data(
    input_data: List[Dict[str, Union[str, int]]], 
    filter_criteria: Optional[str] = None
) -> Dict[str, List[str]]:
    """
    Process input data according to specified criteria.
    
    Args:
        input_data: List of dictionaries containing data to process
        filter_criteria: Optional string to filter results
        
    Returns:
        Dictionary with processed results
        
    Raises:
        ValueError: If input_data is empty
    """
    if not input_data:
        raise ValueError("Input data cannot be empty")
    
    # Implementation here...
    return {}
```

## Pre-commit Verification
Before suggesting any code, ensure it would pass:
1. `black --check .`
2. `flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
3. `flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics`
4. `mypy src/quantik_core/`

Always prioritize code quality and maintainability over brevity.
