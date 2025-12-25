# Dependency Injection Quick Reference

## Getting a Manager (99% of cases)

```python
from core.di_container import inject
from core.managers.core_operations_manager import CoreOperationsManager

manager = inject(CoreOperationsManager)
```

## Available Classes and Protocols

| Class/Protocol | What it does |
|----------------|--------------|
| `CoreOperationsManager` | Extract/inject sprites (handles extraction and injection) |
| `ApplicationStateManager` | Session, settings, workflow state |
| `ROMCacheProtocol` | ROM file caching |
| `ConfigurationService` | App directories and paths |

## In Tests

```python
def test_extraction(isolated_managers):
    # isolated_managers sets up DI - just use inject()
    manager = inject(CoreOperationsManager)
    result = manager.validate_extraction_params(params)
```

## What NOT To Do

```python
# WRONG - deprecated, methods removed
from core.managers.registry import ManagerRegistry
manager = ManagerRegistry().get_extraction_manager()

# WRONG - direct instantiation bypasses DI
from core.managers.core_operations_manager import CoreOperationsManager
manager = CoreOperationsManager()  # Missing dependencies!

# RIGHT - use inject()
manager = inject(CoreOperationsManager)
```

## App Startup (for reference only)

```python
# In launch_spritepal.py - already done for you
initialize_managers("SpritePal", settings_path=...)
```

## Two Systems, One Rule

- **DIContainer** (`inject()`) - Use this to get dependencies
- **ManagerRegistry** - Internal lifecycle management (don't call directly)

**Rule**: Always use `inject(ManagerClass)`. Never instantiate managers directly.

---

*Last updated: December 25, 2025*
