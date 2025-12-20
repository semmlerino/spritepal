# Real Component Testing Infrastructure Guide

## Overview

This guide documents the new Real Component Testing Infrastructure that replaces the problematic MockFactory with type-safe, real component testing.

## Problem Statement (Phase 1 Analysis)

The existing MockFactory approach had critical issues:
- **3,035 mock occurrences** preventing real integration testing
- **15+ unsafe cast() calls** causing type safety issues
- **83 manager mock occurrences** that don't behave like real managers
- Workers using unsafe type casting, assuming specific manager types
- No proper lifecycle management or cleanup

## Solution Architecture

### 1. DataRepository (`test_data_repository.py`)
Provides consistent test data management:
- **Predefined test scenarios** with expected outcomes
- **Real test data files** (VRAM, CGRAM, OAM, ROM)
- **Automatic cleanup** of temporary files
- **Size variants** (small, medium, comprehensive)

### 2. RealComponentFactory (`real_component_factory.py`)
Creates real components with type safety:
- **Real managers** with test data injection
- **Type-safe creation** without casting
- **Generic typed factories** for compile-time safety
- **Proper lifecycle management**

### 3. ManagerTestContext (`manager_test_context.py`)
Manages test lifecycle properly:
- **Context managers** for safe resource management
- **Isolated testing** with no shared state
- **Parallel test support** with thread safety
- **Automatic cleanup** of all resources

### 4. TypedWorkerBase (`typed_worker_base.py`)
Provides type-safe worker testing:
- **Generic base classes** with type parameters
- **Type validation** without unsafe casting
- **Signal monitoring** and verification
- **Worker test helpers** for common patterns

## Migration Guide

### Before (MockFactory with Unsafe Casting)

```python
from tests.infrastructure.mock_factory import MockFactory
from typing import cast

def test_extraction_old_way():
    factory = MockFactory()
    mock_manager = factory.create_extraction_manager()
    
    # UNSAFE: Required cast to use manager
    manager = cast(ExtractionManager, mock_manager)
    
    # Mock doesn't behave like real manager
    manager.extract_sprites.return_value = {"mocked": "data"}
    
    # Worker with unsafe assumption
    worker = Mock()
    worker.manager = mock_manager  # Type unclear
```

### After (RealComponentFactory with Type Safety)

```python
from tests.infrastructure.real_component_factory import RealComponentFactory

def test_extraction_new_way(isolated_managers, tmp_path):
    # Use isolated_managers fixture for test isolation
    factory = RealComponentFactory(manager_registry=isolated_managers)

    # Real manager from the isolated registry
    manager = isolated_managers.extraction_manager

    # Real methods work as expected
    params = factory._data_repo.get_vram_extraction_data("medium")
    is_valid = manager.validate_extraction_params(params)

    # Type-safe worker creation
    worker = factory.create_extraction_worker(params)
```

## Key Components

### 1. Type-Safe Manager Creation

```python
# Create typed factory for compile-time safety
extraction_factory = TypedManagerFactory(ExtractionManager)
manager = extraction_factory.create_with_test_data("medium")
# manager is typed as ExtractionManager - no cast needed!
```

### 2. Test Context Management

```python
# Managed lifecycle with automatic cleanup
with manager_context("extraction", "injection") as ctx:
    extraction = ctx.get_extraction_manager()  # Returns ExtractionManager
    injection = ctx.get_injection_manager()    # Returns InjectionManager
    
    # Create and run workers
    worker = ctx.create_worker("extraction", params)
    completed = ctx.run_worker_and_wait(worker)
```

### 3. Typed Worker Pattern

```python
class MyWorker(TypedWorkerBase[ExtractionManager, dict, list]):
    def _execute_work(self) -> list:
        # Type-safe access to manager
        self.manager.extract_sprites(self.params)
        return results

# Test with type safety
helper = WorkerTestHelper(MyWorker)
worker = helper.create_worker(manager, params)
completed = helper.run_and_wait()
```

### 4. Test Data Management

```python
repo = get_test_data_repository()

# Get consistent test data
vram_data = repo.get_vram_extraction_data("medium")
rom_data = repo.get_rom_extraction_data("small")
injection_data = repo.get_injection_data("comprehensive")

# All paths are real, temporary files
assert Path(vram_data["vram_path"]).exists()
```

## Benefits

### Type Safety
- **No unsafe cast() operations** - all types known at compile time
- **Generic type parameters** for workers and managers
- **Type validation** built into the infrastructure

### Real Components
- **Actual manager instances** with real behavior
- **Real worker execution** with proper threading
- **Real signal propagation** and Qt event handling

### Better Testing
- **Integration testing** with real components
- **Predictable test data** from repository
- **Proper lifecycle management** with cleanup

### Parallel Testing
- **Thread-safe contexts** for parallel execution
- **Isolated test environments** with no shared state
- **Resource pooling** for efficiency

## Usage Examples

### Simple Unit Test

```python
def test_manager_unit(isolated_managers):
    # Access managers through the isolated registry
    manager = isolated_managers.extraction_manager
    assert manager.is_initialized()
```

### Integration Test

```python
def test_full_workflow():
    with manager_context("all") as ctx:
        # Real managers
        extraction = ctx.get_extraction_manager()
        injection = ctx.get_injection_manager()
        
        # Real workflow
        extract_worker = ctx.create_worker("extraction")
        ctx.run_worker_and_wait(extract_worker)
        
        inject_worker = ctx.create_worker("injection")
        ctx.run_worker_and_wait(inject_worker)
```

### Parallel Testing

Parallel testing is handled automatically by pytest-xdist. Use `isolated_managers` fixture for proper isolation:

```bash
pytest tests/ -n auto  # Uses all available cores
```

## Pytest Fixtures

The infrastructure provides ready-to-use pytest fixtures:

```python
def test_with_fixtures(
    real_factory: RealComponentFactory,
    test_context: ManagerTestContext,
    extraction_manager_real: ExtractionManager
):
    # Use real components directly
    assert extraction_manager_real.is_initialized()
```

## Migration Checklist

- [ ] Replace `MockFactory` imports with `RealComponentFactory`
- [ ] Remove all `cast()` operations for managers/workers
- [ ] Replace mock creation with real component creation
- [ ] Use `manager_context` for lifecycle management
- [ ] Replace mock data with `DataRepository`
- [ ] Update worker tests to use `TypedWorkerBase`
- [ ] Add proper cleanup with context managers
- [ ] Update pytest fixtures to use real components

## Performance Considerations

- Real components are slightly slower than mocks
- Use "small" test data for unit tests
- Use "medium" or "comprehensive" for integration tests
- Parallel contexts improve test suite speed
- Temporary files are automatically cleaned up

## Conclusion

The Real Component Testing Infrastructure provides:
1. **Type safety** without unsafe casting
2. **Real component behavior** for accurate testing
3. **Proper lifecycle management** with cleanup
4. **Consistent test data** from repository
5. **Migration path** from mock-based testing

This infrastructure eliminates the 3,035 mock occurrences and 15+ unsafe cast() calls identified in Phase 1, providing a robust foundation for reliable, type-safe testing.