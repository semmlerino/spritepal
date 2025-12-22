# SpritePal Initialization Flow

This document shows the exact order in which components are initialized.
**Changing this order will break the application.**

## Initialization Sequence

```
Application Entry Point (launch_spritepal.py)
                    │
                    ▼
    ┌───────────────────────────────────────────────────────────────┐
    │  initialize_managers("SpritePal", settings_path=...)          │
    │                                                               │
    │  ┌─────────────────────────────────────────────────────────┐  │
    │  │  1. configure_container()                               │  │
    │  │     Registers SERVICES (not managers):                  │  │
    │  │     • ConfigurationServiceProtocol → ConfigurationService│  │
    │  │     • SettingsManagerProtocol → factory (lazy)          │  │
    │  │     • ROMCacheProtocol → factory (lazy)                 │  │
    │  │     • ROMExtractorProtocol → factory (lazy)             │  │
    │  └─────────────────────────────────────────────────────────┘  │
    │                          │                                    │
    │                          ▼                                    │
    │  ┌─────────────────────────────────────────────────────────┐  │
    │  │  2. Create ApplicationStateManager                      │  │
    │  │     • Handles: session, settings, state, history        │  │
    │  │     • Registers: ApplicationStateManagerProtocol        │  │
    │  │                                                         │  │
    │  │  ⚠️ CRITICAL: Must be registered BEFORE CoreOperations  │  │
    │  │  because: ROMCache → SettingsManager → AppStateManager  │  │
    │  └─────────────────────────────────────────────────────────┘  │
    │                          │                                    │
    │                          ▼                                    │
    │  ┌─────────────────────────────────────────────────────────┐  │
    │  │  3. Create SpritePresetManager                          │  │
    │  │     • Handles: user-defined sprite presets              │  │
    │  │     • Registers: SpritePresetManagerProtocol            │  │
    │  └─────────────────────────────────────────────────────────┘  │
    │                          │                                    │
    │                          ▼                                    │
    │  ┌─────────────────────────────────────────────────────────┐  │
    │  │  4. Create CoreOperationsManager                        │  │
    │  │     • Handles: extraction, injection, palette, nav      │  │
    │  │     • Creates internally: ROMExtractor, ROMService,     │  │
    │  │       VRAMService, PaletteManager                       │  │
    │  │     • Registers: ExtractionManagerProtocol,             │  │
    │  │                  InjectionManagerProtocol               │  │
    │  └─────────────────────────────────────────────────────────┘  │
    │                                                               │
    └───────────────────────────────────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────────────────────────────────┐
    │  register_ui_factories()                                      │
    │                                                               │
    │  ⚠️ MUST be called AFTER initialize_managers()               │
    │                                                               │
    │  Registers:                                                   │
    │  • DialogFactoryProtocol                                      │
    │  • ManualOffsetDialogFactoryProtocol                         │
    │  • (other UI factory protocols)                               │
    └───────────────────────────────────────────────────────────────┘
                    │
                    ▼
           Application Ready
```

## Dependency Chain

The factories use lazy initialization. When you call `inject(ROMExtractorProtocol)`:

```
inject(ROMExtractorProtocol)
    └── ROMExtractor needs ROMCacheProtocol
            └── ROMCache needs SettingsManagerProtocol
                    └── SettingsManager needs ApplicationStateManagerProtocol
                            └── ✓ Already registered (step 2)
```

## What Can Go Wrong

### Error: "No registration for ApplicationStateManagerProtocol"

**Cause**: CoreOperationsManager was created before ApplicationStateManager was registered.

**Fix**: Ensure `configure_container()` runs before manager creation.

### Error: "No registration for DialogFactoryProtocol"

**Cause**: UI code called `inject(DialogFactoryProtocol)` before `register_ui_factories()`.

**Fix**: Entry point must call:
```python
initialize_managers(...)
from ui import register_ui_factories
register_ui_factories()  # <-- Add this
```

### Error: "Factory for X previously failed"

**Cause**: A factory threw an exception, and the container cached the failure.

**Fix**: Clear the container and reinitialize:
```python
from core.di_container import reset_container
reset_container()
initialize_managers(...)
```

## For Tests

Tests use fixtures that handle all this automatically:

```python
def test_extraction(isolated_managers):
    # isolated_managers calls initialize_managers() + register_ui_factories()
    manager = inject(ExtractionManagerProtocol)  # Just works
```

See `tests/fixtures/core_fixtures.py:isolated_managers` for implementation.

## Adding a New Manager

1. Add to `MANAGER_DEPENDENCIES` in `core/managers/registry.py`
2. Create manager class in `core/managers/`
3. Define protocol in `core/protocols/manager_protocols.py`
4. Register in `initialize_managers()` after its dependencies
5. Update this document

---

*See also: [architecture.md](./architecture.md) for layer boundaries*
