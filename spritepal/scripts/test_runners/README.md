# Test Runner Scripts

This directory contains specialized test execution scripts for different testing scenarios and environments.

## Recommended Testing Approach

**Use Qt offscreen mode** for headless testing (automatically configured in `conftest.py`):

```bash
# Standard test execution (offscreen mode enabled automatically)
uv run pytest

# Or explicitly set offscreen mode
QT_QPA_PLATFORM=offscreen uv run pytest
```

This is the canonical approach for SpritePal. See `CLAUDE.md` for details.

## Test Execution Scripts

### Available Scripts
- `run_tests_safe.py` - Safe test execution with error handling and cleanup
- `run_tests.py` - Standard test runner with enhanced reporting
- `run_ui_workflow_tests.py` - UI workflow integration tests

### Manual Testing
- `test_rom_cache_manual.py` - Manual testing script for ROM cache functionality
- `test_simple_real_integration.py` - Simple real-world integration test scenarios

## Features

### Enhanced Error Handling
- Captures and reports test failures with context
- Provides detailed logging for debugging test issues
- Handles Qt application lifecycle properly

## Usage

```bash
# Run tests with enhanced safety checks
python scripts/test_runners/run_tests_safe.py

# Run specific manual tests
python scripts/test_runners/test_rom_cache_manual.py
```

## Environment Requirements

- Qt6 libraries
- pytest and pytest-qt
- Appropriate test data files

See the main project documentation for complete setup instructions.
