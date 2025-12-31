# Code Validation System

A comprehensive validation system for code-generating agents to prevent syntax errors and ensure consistent code quality.

## Overview

This validation system provides:

- **AST-based syntax validation** - Catches syntax errors before code is written
- **Automatic code formatting** with Black integration
- **Import sorting** with isort compatibility
- **Line ending normalization** (CRLF → LF)
- **Agent-specific validators** for test code, Qt code, and type annotations
- **Mock density monitoring** for test quality assurance

## Quick Start

### Basic Validation

```python
from scripts.code_validation import validate_generated_code

code = '''
def my_function(param: str) -> str:
    return f"Hello {param}"
'''

is_valid, formatted_code, issues = validate_generated_code(code)
if is_valid:
    # Write the validated code to file
    with open('output.py', 'w') as f:
        f.write(formatted_code)
else:
    # Handle validation errors
    for issue in issues:
        print(f"Error: {issue}")
```

### Command Line Usage

```bash
# Validate specific files
source venv/bin/activate
python scripts/code_validation.py file1.py file2.py

# Strict mode (warnings become errors)
python scripts/code_validation.py --strict file.py

# Skip formatting/import sorting
python scripts/code_validation.py --no-format --no-sort-imports file.py
```

### Monitor Mock Density

```bash
# Check mock density in test files
python scripts/monitor_mock_density.py tests/

# Fail if violations found
python scripts/monitor_mock_density.py tests/ --fail-on-violation

# Save detailed report
python scripts/monitor_mock_density.py tests/ --output report.txt --json-output data.json
```

## Core Functions

### `validate_generated_code(code, language='python', format_code=True, sort_imports=True, strict_mode=False)`

Main validation function that:
1. Normalizes line endings (CRLF → LF)
2. Validates syntax with AST parsing
3. Sorts imports with isort (optional)
4. Formats code with Black (optional)
5. Performs additional checks (imports, type hints)

**Returns:** `(is_valid: bool, formatted_code: str, issues: list[str])`

### `validate_test_code(code, **kwargs)`

Specialized validator for test code that includes:
- Test function naming checks (`test_*` prefix)
- Missing docstring detection
- Pytest fixture import validation
- All standard validations

### `validate_qt_code(code, **kwargs)`

Specialized validator for Qt code that checks for:
- Proper Qt imports
- Signal connection patterns (avoiding GUI in lambdas)
- Qt boolean evaluation issues (`is not None` vs truthiness)
- Proper `super().__init__()` calls
- All standard validations

### `validate_file(filepath, **kwargs)`

Validates an existing file, automatically choosing the appropriate validator based on:
- File name patterns (test files → `validate_test_code`)
- Content analysis (Qt imports → `validate_qt_code`)
- Default fallback → `validate_generated_code`

## Agent Integration Patterns

### Pattern 1: Validation Before Writing

```python
def write_validated_code(filepath: Path, code: str) -> bool:
    """Write code only if validation passes."""
    is_valid, formatted_code, issues = validate_generated_code(code)
    
    if not is_valid:
        for issue in issues:
            print(f"Validation error: {issue}")
        return False
    
    filepath.write_text(formatted_code)
    return True
```

### Pattern 2: Test Code Generation

```python
def generate_test_code(test_name: str, functionality: str) -> str:
    """Generate validated test code."""
    code = f'''
import pytest

def test_{test_name}():
    """Test {functionality}."""
    # Test implementation here
    assert True
'''
    
    is_valid, formatted_code, issues = validate_test_code(code)
    
    if not is_valid:
        raise ValueError(f"Generated test code failed validation: {issues}")
    
    return formatted_code
```

### Pattern 3: Qt Widget Generation

```python
def generate_qt_widget(class_name: str, base_class: str) -> str:
    """Generate validated Qt widget code."""
    code = f'''
from PyQt6.QtWidgets import {base_class}

class {class_name}({base_class}):
    """Generated Qt widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the user interface."""
        pass
'''
    
    is_valid, formatted_code, issues = validate_qt_code(code)
    
    if not is_valid:
        # Handle Qt-specific validation failures
        raise ValueError(f"Generated Qt code failed validation: {issues}")
    
    return formatted_code
```

## Configuration Options

### Black Formatting

The validator uses Black with these settings:
- Line length: 88 characters
- Target versions: Python 3.8+
- Standard Black formatting rules

### Isort Configuration

Import sorting uses Black-compatible settings:
- Profile: "black"
- Line length: 88
- Multi-line output: 3
- Trailing commas: True

### Mock Density Limits

Default mock density threshold: **0.02** (2% of lines)

Configurable via `--max-density` parameter:
```bash
python scripts/monitor_mock_density.py --max-density 0.05 tests/
```

## Validation Rules

### Syntax Validation
- ✅ **AST parsing** - Catches all Python syntax errors
- ✅ **Line/column reporting** - Precise error location
- ✅ **Context display** - Shows problematic code

### Import Validation
- ⚠️ **Star imports** - Warns about `from module import *`
- ⚠️ **Relative imports** - Warns about potential package issues
- ⚠️ **Import placement** - Warns about imports after code

### Type Annotation Validation
- ⚠️ **Missing return types** - Functions without return annotations
- ⚠️ **Missing parameter types** - Parameters without type hints
- ⚠️ **Type consistency** - Basic type usage checks

### Test-Specific Validation
- ⚠️ **Test naming** - Functions should start with `test_`
- ⚠️ **Missing docstrings** - Test functions without documentation
- ⚠️ **Fixture imports** - Pytest usage without imports

### Qt-Specific Validation
- ⚠️ **GUI in lambdas** - Creating GUI objects in signal connections
- ⚠️ **Boolean evaluation** - Using truthiness instead of `is not None`
- ⚠️ **Missing super calls** - Qt widgets without proper initialization

### Mock Density Validation
- ❌ **High mock density** - Too many mocks per line of code
- 📊 **Detailed analysis** - AST-based mock detection
- 📈 **Trend reporting** - Mock usage patterns over time

## Error Handling

### Validation Errors (Failures)
- **Syntax errors** - Code will not run
- **High mock density** - Code quality issues (if `--fail-on-violation`)
- **Strict mode warnings** - All issues treated as errors

### Validation Warnings (Non-failures)
- **Style issues** - Code runs but violates conventions
- **Type hint issues** - Missing or incomplete annotations
- **Import issues** - Suboptimal import patterns

### Graceful Degradation
- **Missing Black** - Validation continues without formatting
- **Missing isort** - Validation continues without import sorting
- **AST failures** - Falls back to line-based analysis

## Integration with CI/CD

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: validate-generated-code
        name: Validate Generated Code
        entry: python scripts/code_validation.py
        language: system
        types: [python]
        stages: [commit]
```

### GitHub Actions

```yaml
# .github/workflows/validate.yml
- name: Validate Code Quality
  run: |
    source venv/bin/activate
    python scripts/code_validation.py --strict src/**/*.py
    python scripts/monitor_mock_density.py tests/ --fail-on-violation
```

### Local Development

```bash
# Add to Makefile or development script
validate:
	source venv/bin/activate && \
	python scripts/code_validation.py --strict src/ && \
	python scripts/monitor_mock_density.py tests/ --fail-on-violation
```

## Performance Considerations

### Validation Speed
- **AST parsing** - Very fast for syntax validation
- **Black formatting** - Moderate speed, caches internally
- **Import sorting** - Fast, minimal overhead

### Memory Usage
- **Small files** - Minimal memory impact
- **Large files** - Proportional to file size
- **Batch processing** - Processes files sequentially

### Caching
- **Black internal caching** - 15-minute cache for unchanged content
- **AST parsing** - No caching (fast enough)
- **Import analysis** - No caching required

## Dependencies

### Required
- **Python 3.8+** - Core language features
- **ast** - Built-in syntax validation
- **pathlib** - File handling

### Optional (with graceful degradation)
- **black** - Code formatting
- **isort** - Import sorting
- **json** - Detailed reporting

### Development/Testing
- **pytest** - Test framework
- **PyQt6/PySide6** - Qt validation testing

## Common Use Cases

### 1. Code Generation Agents
Validate all generated code before writing to prevent syntax errors:

```python
# In your agent's code generation method
generated_code = self.generate_python_code(requirements)
is_valid, formatted_code, issues = validate_generated_code(generated_code)

if not is_valid:
    self.handle_generation_failure(issues)
else:
    self.write_code_to_file(formatted_code)
```

### 2. Template-Based Code Generation
Validate filled templates:

```python
template_code = self.fill_template(template, parameters)
is_valid, formatted_code, issues = validate_generated_code(template_code)
# Handle validation results...
```

### 3. Code Transformation
Validate after applying transformations:

```python
transformed_code = self.apply_transformations(original_code)
is_valid, formatted_code, issues = validate_generated_code(transformed_code)
# Ensure transformations didn't break syntax...
```

### 4. Test Quality Assurance
Monitor test code quality:

```bash
# In CI pipeline
python scripts/monitor_mock_density.py tests/ --max-density 0.03 --fail-on-violation
```

## Troubleshooting

### Common Issues

**"Black not available - skipping formatting"**
- Install Black: `pip install black`
- Or continue without formatting: Expected behavior

**"isort not available - skipping import sorting"**  
- Install isort: `pip install isort`
- Or continue without sorting: Expected behavior

**"Import after code - move to top"**
- False positive for `from __future__ import annotations`
- Can be ignored or fixed by moving imports

**"Qt boolean evaluation warning"**
- Use `is not None` instead of truthiness for Qt objects
- Prevents empty container evaluation issues

### Debugging Validation

```python
# Enable detailed error reporting
is_valid, formatted_code, issues = validate_generated_code(
    code, 
    strict_mode=True  # Treat warnings as errors for debugging
)

for issue in issues:
    print(f"Issue: {issue}")
    # Examine each issue in detail
```

### Performance Issues

```python
# Skip expensive operations for quick validation
is_valid, formatted_code, issues = validate_generated_code(
    code,
    format_code=False,    # Skip Black formatting
    sort_imports=False    # Skip import sorting
)
```

---

## Summary

This validation system ensures that code-generating agents produce high-quality, syntactically correct Python code. By integrating validation into the agent workflow, you can:

1. **Prevent syntax errors** before code reaches files
2. **Maintain consistent formatting** across generated code
3. **Follow best practices** for test and Qt code
4. **Monitor code quality** with mock density analysis
5. **Integrate with CI/CD** for automated quality gates

The system is designed to be **fast**, **reliable**, and **easy to integrate** into any code generation workflow.