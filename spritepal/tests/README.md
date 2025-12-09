# SpritePal Test Suite

This directory contains the pytest test suite for SpritePal, featuring **Real Component Testing** infrastructure designed to minimize mock usage and improve test quality and maintainability.

## Quick Start: Real Component Testing

### For New Tests (Recommended)
```python
from tests.infrastructure.real_component_factory import RealComponentFactory

def test_extraction_workflow():
    """Test using real components - no mocks needed!"""
    with RealComponentFactory() as factory:
        # Real manager, no casting required
        manager = factory.create_extraction_manager(with_test_data=True)
        
        # Real validation logic
        params = factory._data_repo.get_vram_extraction_data("small")
        is_valid = manager.validate_extraction_params(params)
        assert isinstance(is_valid, bool)  # Real behavior
```

### For Qt Widget Tests
```python
def test_real_widget(qtbot):
    """Test real Qt widgets with proper lifecycle."""
    with RealComponentFactory() as factory:
        widget = factory.create_test_widget(qtbot)
        widget.show()
        qtbot.waitExposed(widget)
        # Test real widget behavior
```

### For Integration Tests
```python
from tests.infrastructure.manager_test_context import manager_context

def test_real_integration():
    """Test real manager integration."""
    with manager_context("extraction", "injection") as ctx:
        extraction = ctx.get_extraction_manager()  # Real ExtractionManager
        injection = ctx.get_injection_manager()    # Real InjectionManager
        # Test real workflow
```

## Testing Philosophy

### Real Components Over Mocks
SpritePal follows the **0.032 mock density threshold** - mocks are used minimally only at system boundaries:

- ✅ **Use Real Components**: Managers, workers, Qt widgets, business logic
- ✅ **Mock System Boundaries**: File I/O, subprocess calls, network requests  
- ✅ **Type Safety**: No unsafe `cast()` operations needed
- ✅ **Authentic Behavior**: Real Qt signals, threading, validation logic

### When to Use Mocks
Mocks are appropriate for:
- External system interfaces (file system, network, subprocess)
- Expensive operations (large file processing)
- Error condition simulation
- Hardware dependencies

See `tests/examples/example_minimal_mock_test.py` for proper mock usage patterns.

## Test Infrastructure

### Core Components
- **RealComponentFactory**: Creates real managers, workers, and UI components with type safety
- **ManagerTestContext**: Manages real manager lifecycles for integration testing
- **DataRepository**: Provides consistent test data (small/medium/comprehensive sizes)
- **Migration Helpers**: Tools for converting mock-based tests to real components

### Directory Structure
```
tests/
├── infrastructure/          # Real component testing framework
│   ├── real_component_factory.py    # Factory for real components
│   ├── manager_test_context.py      # Integration test contexts
│   ├── test_data_repository.py      # Consistent test data
│   └── migration_helpers.py         # Mock-to-real migration tools
├── examples/               # Example patterns and migration guides
│   ├── example_real_component_test.py    # Ideal real component patterns
│   ├── example_minimal_mock_test.py      # When mocks are appropriate
│   └── example_migration.py             # Before/after migration examples
└── test_*.py              # Test files (many using real components)
```

## Test Categories

### Unit Tests with Real Components
- **Core Logic**: `test_extractor.py`, `test_palette_manager.py`
- **Manager Logic**: `test_extraction_manager.py`, `test_injection_manager.py`
- **Utilities**: `test_constants.py`, `test_validation.py`

### Integration Tests
- **Manager Integration**: `test_manager_integration_real_tdd.py`
- **UI Integration**: `test_main_window_state_integration_real.py`
- **Workflow Tests**: `test_unified_dialog_integration_real.py`

### Performance Benchmarks
- Real component performance testing with `pytest-benchmark`
- Memory leak validation with real Qt components
- Threading behavior validation

## Running Tests

### Basic Test Execution
```bash
# All tests with real components
source venv/bin/activate && pytest tests/ -v

# Specific test file
pytest tests/test_extraction_manager.py -v

# Integration tests only
pytest tests/ -m "integration" -v

# Quick unit tests (small test data)
pytest tests/ -m "unit" -v
```

### Coverage Analysis
```bash
# Coverage with real components
pytest tests/ --cov=core --cov=ui --cov-report=html

# Coverage report shows real integration paths tested
open htmlcov/index.html
```

### Performance Testing
```bash
# Benchmark real component performance
pytest tests/ --benchmark-only

# Memory leak detection
pytest tests/ --memray
```

### Migration Tools
```bash
# Analyze mock usage in test files
python -m tests.infrastructure.migration_helpers analyze tests/test_controller.py

# Generate migration report
python -m tests.infrastructure.migration_helpers report

# Generate migration script
python -m tests.infrastructure.migration_helpers generate tests/test_controller.py
```

## Migration Guide

### Converting Existing Tests

1. **Identify Mock Usage**:
   ```bash
   python -m tests.infrastructure.migration_helpers analyze your_test_file.py
   ```

2. **Replace MockFactory Imports**:
   ```python
   # OLD (deprecated)
   from tests.infrastructure.mock_factory import MockFactory
   
   # NEW (preferred)  
   from tests.infrastructure.real_component_factory import RealComponentFactory
   ```

3. **Remove Unsafe Casting**:
   ```python
   # OLD (unsafe)
   mock_manager = MockFactory.create_extraction_manager()
   manager = cast(ExtractionManager, mock_manager)  # TYPE VIOLATION!
   
   # NEW (type-safe)
   with RealComponentFactory() as factory:
       manager = factory.create_extraction_manager()  # Properly typed
   ```

4. **Update Test Logic**:
   ```python
   # OLD (testing mocks)
   mock_manager.extract_sprites.assert_called_once()
   
   # NEW (testing behavior)
   result = manager.extract_sprites(params)
   assert result is not None
   assert isinstance(result, dict)
   ```

See `tests/examples/example_migration.py` for complete before/after examples.

## Performance Benchmarks

Real component testing performance (vs mocks):

| Test Type | Mock Time | Real Component Time | Overhead |
|-----------|-----------|-------------------|----------|
| Unit Test | 1-5ms | 10-50ms | 2-10x (acceptable) |
| Integration | 5-20ms | 50-200ms | 4-10x (valuable) |  
| UI Test | 10-50ms | 100-500ms | 5-10x (authentic) |

**Trade-off**: Slightly slower execution for dramatically improved test value and maintainability.

## Test Guidelines

### Real Component Testing Principles
- **Real First**: Use real components unless there's a specific need for mocking
- **Mock at Boundaries**: Mock external systems (file I/O, network), not business logic
- **Type Safety**: Avoid `cast()` operations - use typed factories instead
- **Authentic Behavior**: Test real Qt signals, threading, and validation logic
- **Proper Cleanup**: Use context managers for resource management

### Code Quality Standards
- **Mock Density**: Target ≤ 0.032 (mocks per line of test code)
- **Type Coverage**: 100% type safety for new test code
- **Signal Testing**: Use `QSignalSpy` and `qtbot.waitSignal()` for Qt testing
- **Worker Testing**: Test real threading behavior with timeouts
- **Memory Management**: Verify cleanup with real component lifecycle testing

### Test Data Management
- **Small Data**: Quick unit tests (< 1KB test files)
- **Medium Data**: Integration tests (1-10KB test files)
- **Comprehensive Data**: Full workflow tests (10KB+ test files)
- **Consistent Paths**: Use `DataRepository` for reliable test data

## Documentation

- **[Real Component Testing Guide](../docs/REAL_COMPONENT_TESTING_GUIDE.md)**: Comprehensive patterns and migration guide
- **[Headless Testing Guide](HEADLESS_TESTING.md)**: CI/CD setup, offscreen mode, and troubleshooting
- **[Testing Examples](examples/)**: Complete code examples for all patterns
- **[Infrastructure Guide](infrastructure/REAL_COMPONENT_TESTING_GUIDE.md)**: Technical implementation details

## Success Metrics

The real component testing migration is **ongoing**:
- ✅ **Infrastructure complete** - RealComponentFactory, DataRepository, migration tools available
- ✅ **New tests use real components** - established patterns in `tests/examples/`
- ✅ **Type safety for new tests** - eliminated unsafe `cast()` operations in migrated tests
- ⚠️ **Migration in progress** - 33 test files still have >5 mock patterns
- ⚠️ **Target mock density: 0.032** - current average is ~0.04-0.05
- 📋 **Next steps** - incrementally migrate heavily-mocked files to RealComponentFactory

## Getting Help

- **Examples**: Check `tests/examples/` for patterns and migration examples
- **Migration Tools**: Use `python -m tests.infrastructure.migration_helpers` for analysis
- **Infrastructure**: See `tests/infrastructure/` for framework documentation
- **Patterns**: Review existing real component tests for established patterns