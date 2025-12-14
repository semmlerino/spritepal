# SpritePal Pytest Markers Guide

This document provides comprehensive guidance on using the systematic pytest marker system implemented for the SpritePal test suite. The markers enable fine-grained control over test execution, environment compatibility, and performance optimization.

## Overview

The marker system organizes tests into clear categories that allow for:
- **Environment-aware execution**: Run only tests compatible with your environment
- **Performance optimization**: Skip slow tests during development
- **Parallel execution control**: Safely run tests in parallel or force serial execution
- **Development workflow enhancement**: Focus on specific test types during development

> **Note**: Parallel test execution (`-n auto`) requires `pytest-xdist`, which is not installed by default.
> To enable: `uv add pytest-xdist --dev`. Commands in this guide show serial execution by default.

## Quick Usage Examples

### Common Test Execution Patterns

```bash
# Fast development feedback - headless tests only, skip slow ones
pytest -m 'headless and not slow'

# Unit tests only - fastest possible execution
pytest -m 'unit'

# Integration tests (add -n auto if pytest-xdist is installed)
pytest -m 'integration and parallel_safe'

# All GUI tests (requires display)
pytest -m 'gui'

# Serial tests only (when parallel execution causes issues)
pytest -m 'serial'

# Tests that can run in CI/headless environments
pytest -m 'headless or mock_only'

# Performance and benchmark tests
pytest -m 'performance or benchmark'

# Skip all slow tests for quick validation
pytest -m 'not slow'

# Run only tests that don't require Qt (pure Python logic)
pytest -m 'no_qt'
```

## Marker Categories

### 1. Execution Environment Markers

#### Primary Environment Classification:
- **`gui`**: Tests requiring display/X11 environment (automatically skipped in headless)
- **`headless`**: Tests safe for CI/headless environments
- **`mock_only`**: Tests using only mocked components (fastest, most reliable)

#### Usage:
```bash
# Safe for CI/automated environments
pytest -m 'headless'

# Only when you have a display available
pytest -m 'gui'

# Fastest possible test execution
pytest -m 'mock_only'
```

### 2. Test Type Markers

#### Test Classification:
- **`unit`**: Fast, isolated tests with no external dependencies
- **`integration`**: Tests that may require files, databases, or services
- **`benchmark`**: Performance benchmarking tests
- **`performance`**: Performance validation tests
- **`stress`**: Stress/load testing
- **`slow`**: Tests taking >1 second to execute

#### Usage:
```bash
# Development cycle - fast feedback
pytest -m 'unit and not slow'

# Full integration testing
pytest -m 'integration'

# Performance analysis
pytest -m 'performance or benchmark'
```

### 3. Qt Component Markers

#### Qt Usage Classification:
- **`qt_real`**: Uses real Qt components (widgets, dialogs, etc.)
- **`qt_mock`**: Uses mocked Qt components
- **`qt_app`**: Requires QApplication instance
- **`no_qt`**: No Qt dependencies whatsoever

#### Usage:
```bash
# Tests that require real Qt (need display)
pytest -m 'qt_real'

# Tests safe for headless with Qt mocking
pytest -m 'qt_mock'

# Pure Python tests (no Qt at all)
pytest -m 'no_qt'
```

### 4. Threading and Concurrency Markers

#### Concurrency Classification:
- **`thread_safety`**: Thread safety tests
- **`timer`**: Tests involving QTimer functionality
- **`worker_threads`**: Tests using worker threads
- **`signals_slots`**: Qt signal/slot mechanism tests

#### Usage:
```bash
# All threading-related tests
pytest -m 'thread_safety or worker_threads'

# Qt-specific concurrency tests
pytest -m 'signals_slots or timer'
```

### 5. Execution Control Markers

#### Parallelization Control:
- **`serial`**: Must run in serial (not parallel)
- **`parallel_safe`**: Confirmed safe for parallel execution
- **`process_pool`**: Uses process pools that need serial execution
- **`singleton`**: Manipulates singletons that conflict in parallel
- **`qt_application`**: Manages QApplication that conflicts in parallel

#### Usage:
```bash
# Tests safe for parallel execution (add -n auto if pytest-xdist is installed)
pytest -m 'parallel_safe'

# Force serial execution
pytest -m 'serial'

# All tests excluding those that conflict in parallel
pytest -m 'not (singleton or qt_application)'
```

### 6. Component and Resource Markers

#### Component Testing:
- **`dialog`**: Tests involving dialogs
- **`mock_dialogs`**: Tests that mock dialog exec() methods
- **`widget`**: Tests involving widgets
- **`preview`**: Tests involving preview components
- **`manager`**: Tests focused on manager classes

#### Resource Requirements:
- **`rom_data`**: Requires ROM files or data
- **`file_io`**: Involves file operations
- **`cache`**: Involves caching mechanisms
- **`memory`**: Memory management tests

#### Usage:
```bash
# UI component tests
pytest -m 'dialog or widget'

# Resource-intensive tests
pytest -m 'rom_data or file_io'

# Manager functionality tests
pytest -m 'manager'
```

## Advanced Usage Patterns

### Development Workflows

#### 1. Fast Development Cycle
```bash
# Quick validation during development
pytest -m 'headless and not slow and not integration' --maxfail=5
```

#### 2. Pre-commit Validation
```bash
# Comprehensive but efficient pre-commit check
pytest -m 'unit or (integration and parallel_safe)' -n auto
```

#### 3. Full Test Suite (CI)
```bash
# Complete test execution in CI
pytest -m 'headless or mock_only' --tb=short
```

#### 4. GUI Testing (Local Development)
```bash
# Full GUI testing when display is available
pytest -m 'gui or qt_real' --tb=short
```

### Performance Optimization

#### Parallel Execution Strategy
```bash
# Maximum parallel efficiency (requires pytest-xdist: uv add pytest-xdist --dev)
pytest -m 'parallel_safe and not slow'  # Add -n auto if xdist installed

# Followed by serial tests
pytest -m 'serial or singleton'
```

#### Memory-Conscious Execution
```bash
# Avoid memory-intensive tests during development
pytest -m 'not (memory or rom_data or benchmark)'
```

### Environment-Specific Testing

#### Headless/CI Environment
```bash
# Optimal for automated environments
pytest -m 'headless and not gui' --tb=line
```

#### Local Development with Display
```bash
# Full spectrum testing
pytest -m 'not slow' --tb=short
```

#### WSL/Windows Subsystem for Linux
```bash
# WSL-safe tests only
pytest -m '(headless or mock_only) and not wsl'
```

## Marker Validation and Consistency

The pytest configuration includes automatic validation to prevent conflicting markers:

### Automatic Conflict Detection
- **gui** + **headless**: Warns about conflicting environment requirements
- **qt_real** + **no_qt**: Warns about conflicting Qt requirements  
- **serial** + **parallel_safe**: Warns about conflicting execution requirements

### Automatic Marker Inference
- Tests with `qt_real` or `rom_data` are automatically marked as `slow`
- GUI tests in headless environments are automatically skipped
- Real Qt components without mocking are skipped in headless environments

## Custom Marker Combinations

### Creating Test Suites
```bash
# Critical path tests only
pytest -m 'critical and not slow'

# Regression test suite
pytest -m 'stability or phase1_fixes'

# Performance validation suite
pytest -m 'performance or benchmark or memory'

# Development safety net
pytest -m 'unit and parallel_safe' -n auto --maxfail=10
```

### Excluding Problem Areas
```bash
# Skip known slow or problematic areas during development
pytest -m 'not (slow or memory or singleton)'

# Skip external dependencies
pytest -m 'not (rom_data or file_io)'
```

## Best Practices

### 1. Marker Selection Guidelines
- **Always use environment markers**: Choose `gui`, `headless`, or `mock_only`
- **Specify Qt requirements**: Use `qt_real`, `qt_mock`, or `no_qt`
- **Indicate parallelization safety**: Use `serial` or `parallel_safe`
- **Mark resource requirements**: Use `rom_data`, `file_io`, etc. as appropriate

### 2. Test Development Workflow
1. Start with `unit` + `headless` + `mock_only` for fastest development
2. Add `integration` when testing component interactions
3. Use `qt_real` + `gui` only when testing actual Qt behavior
4. Always mark `serial` if your test manipulates shared state

### 3. CI/CD Configuration
- Use `headless or mock_only` for automated environments
- Separate GUI tests into dedicated jobs with display capabilities
- Run `serial` tests separately from `parallel_safe` tests
- Use `critical` marker for tests that must always pass

### 4. Performance Optimization
- Regular developers: `pytest -m 'not slow'` for quick feedback
- Integration testing: `pytest -m 'parallel_safe'` (add `-n auto` if pytest-xdist installed)
- Full validation: Run complete suite in CI, not locally

## Troubleshooting

### Common Issues and Solutions

#### 1. Tests Skipped in Headless Environment
```bash
# Problem: GUI tests are being skipped
# Solution: Use mocked versions or check marker consistency
pytest -m 'qt_mock and not gui'
```

#### 2. Parallel Execution Failures
```bash
# Problem: Tests fail when run in parallel
# Solution: Mark problematic tests as serial
pytest -m 'serial'  # Run these separately
```

#### 3. Slow Test Suite
```bash
# Problem: Test suite takes too long
# Solution: Focus on essential tests during development
pytest -m 'unit and not slow' --maxfail=5
```

#### 4. Environment Incompatibility
```bash
# Problem: Tests fail in different environments
# Solution: Use environment-appropriate markers
pytest -m 'headless' # For CI
pytest -m 'gui'      # For local with display
```

## Migration from Legacy Markers

### Deprecated Markers
- `mock` → Use `mock_only` or `mock_managers`
- `mock_gui` → Use `qt_mock`

### Automated Migration
The marker system is backward compatible, but update test files to use new markers:

```python
# Old style
@pytest.mark.mock_gui
def test_dialog():
    pass

# New style
@pytest.mark.qt_mock
@pytest.mark.headless
@pytest.mark.dialog
def test_dialog():
    pass
```

## Monitoring and Validation

### Marker Usage Analysis
Use the enhanced marker application script to analyze marker distribution:

```bash
python3 scripts/mark_serial_tests.py
```

### Performance Validation
Monitor test execution times and adjust markers accordingly:

```bash
# Profile slow tests
pytest --durations=10 -m 'slow'

# Validate parallel safety (add -n auto if pytest-xdist installed)
pytest -m 'parallel_safe' --tb=short
```

This comprehensive marker system enables precise control over test execution, improving both development productivity and CI reliability while maintaining comprehensive test coverage across different environments.