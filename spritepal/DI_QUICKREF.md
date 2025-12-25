# Dependency Access Quick Reference

## Recommended Pattern: AppContext

```python
from core.app_context import get_app_context

context = get_app_context()
state_manager = context.application_state_manager
operations_manager = context.core_operations_manager
```

## Available via AppContext

| Attribute | What it does |
|-----------|--------------|
| `application_state_manager` | Session, settings, workflow state |
| `core_operations_manager` | Extract/inject sprites |
| `sprite_preset_manager` | Sprite presets and configurations |
| `configuration_service` | App directories and paths |
| `rom_cache` | ROM file caching (lazy-initialized) |
| `rom_extractor` | ROM extraction operations (lazy-initialized) |

## In Tests

```python
def test_extraction(isolated_managers):
    # isolated_managers sets up DI - use get_app_context()
    context = get_app_context()
    manager = context.core_operations_manager
    result = manager.validate_extraction_params(params)
```

## Legacy Pattern (Deprecated)

```python
# DEPRECATED - still works but will emit warning
from core.di_container import inject
from core.managers.core_operations_manager import CoreOperationsManager

manager = inject(CoreOperationsManager)  # Deprecated
```

## What NOT To Do

```python
# WRONG - direct instantiation bypasses DI
from core.managers.core_operations_manager import CoreOperationsManager
manager = CoreOperationsManager()  # Missing dependencies!

# RIGHT - use get_app_context()
from core.app_context import get_app_context
manager = get_app_context().core_operations_manager
```

## App Startup (for reference only)

```python
# In launch_spritepal.py - already done for you
from core.app_context import create_app_context
context = create_app_context("SpritePal", settings_path=...)
```

## Migration Guide

Replace inject() calls with get_app_context():

```python
# Before
from core.di_container import inject
from core.managers.application_state_manager import ApplicationStateManager
manager = inject(ApplicationStateManager)

# After
from core.app_context import get_app_context
manager = get_app_context().application_state_manager
```

---

*Last updated: December 25, 2025*
