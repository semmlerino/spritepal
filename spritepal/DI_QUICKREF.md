# Dependency Injection Quick Reference

## Getting a Manager (99% of cases)

```python
from core.di_container import inject
from core.protocols.manager_protocols import ExtractionManagerProtocol

manager = inject(ExtractionManagerProtocol)
```

## Available Protocols

| Protocol | What it does |
|----------|--------------|
| `ExtractionManagerProtocol` | Extract sprites from ROM/VRAM |
| `InjectionManagerProtocol` | Inject sprites into ROM |
| `ApplicationStateManagerProtocol` | Session, settings, workflow state |
| `SettingsManagerProtocol` | Persistent settings (cache, paths) |
| `ROMCacheProtocol` | ROM file caching |
| `ConfigurationServiceProtocol` | App directories and paths |

## In Tests

```python
def test_extraction(isolated_managers):
    # isolated_managers sets up DI - just use inject()
    manager = inject(ExtractionManagerProtocol)
    result = manager.validate_extraction_params(params)
```

## What NOT To Do

```python
# WRONG - deprecated, methods removed
from core.managers.registry import ManagerRegistry
manager = ManagerRegistry().get_extraction_manager()

# WRONG - tight coupling
from core.managers.core_operations_manager import CoreOperationsManager
manager = CoreOperationsManager()

# RIGHT - loose coupling via protocol
manager = inject(ExtractionManagerProtocol)
```

## App Startup (for reference only)

```python
# In launch_spritepal.py - already done for you
initialize_managers("SpritePal", settings_path=...)
from ui import register_ui_factories
register_ui_factories()  # MUST be after initialize_managers()
```

## Two Systems, One Rule

- **DIContainer** (`inject()`) - Use this to get dependencies
- **ManagerRegistry** - Internal lifecycle management (don't call directly)

**Rule**: Always use `inject(ProtocolType)`. Never instantiate managers directly.
