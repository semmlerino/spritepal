# SpritePal Configuration Guide

This document explains how settings and configuration work in SpritePal.

---

## 1. Settings Files

SpritePal uses JSON files for persistent settings. Three files serve different contexts:

| File | Purpose | When Used |
|------|---------|-----------|
| `.spritepal_settings.json` | Production settings | Normal app launch |
| `.spritepal-test_settings.json` | Unit test settings | When tests use `isolated_managers` fixture |
| `.spritepal-uitest_settings.json` | UI test settings | UI-specific test scenarios |

**Location**: All files are in the project root (`spritepal/`).

---

## 2. Configuration Initialization Flow

Configuration is loaded in a specific order during app startup:

```
launch_spritepal.py (Application Entry)
         │
         ▼
┌──────────────────────────────────────┐
│ Step 1: Early Feature Flags          │  Lines 26-42
│ ConfigurationService() created       │
│ Reads "experimental" settings        │
└──────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ Step 2: Main ConfigurationService    │  Lines 463-474
│ Another instance for path resolution │
│ Computes: settings_file, cache_dir,  │
│ log_dir, config_dir                  │
└──────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ Step 3: ManagerRegistry Init         │  core/managers/registry.py
│ initialize_managers(settings_path)   │
│ Passes settings_file to managers     │
└──────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ Step 4: DI Container Config          │  core/di_container.py
│ configure_container()                │
│ Registers protocols → implementations │
└──────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ Step 5: SessionManager Load          │  core/managers/session_manager.py
│ _load_settings()                     │
│ Merges JSON with defaults            │
└──────────────────────────────────────┘
```

---

## 3. ConfigurationService

**File**: `core/configuration_service.py`

The ConfigurationService computes all application paths from a single root:

```python
from core.di_container import inject
from core.protocols.manager_protocols import ConfigurationServiceProtocol

config = inject(ConfigurationServiceProtocol)

# Available paths:
config.app_root              # Project root (spritepal/)
config.settings_file         # Path to settings JSON
config.log_directory         # ~/.spritepal/logs/
config.cache_directory       # ~/.spritepal_rom_cache/
config.config_directory      # spritepal/config/
config.default_dumps_directory  # ~/Documents/Mesen2/Debugger/
```

---

## 4. Accessing Settings at Runtime

Use dependency injection to access settings:

```python
from core.di_container import inject
from core.protocols.manager_protocols import SettingsManagerProtocol

settings_manager = inject(SettingsManagerProtocol)

# Read a setting
value = settings_manager.get("some_key", default_value)

# Read a nested setting
last_rom = settings_manager.get("rom_injection.last_input_rom", "")

# Write a setting
settings_manager.set("some_key", new_value)
settings_manager.save()  # Persist to disk
```

---

## 5. Adding a New Setting

1. **Add default value** in `core/managers/session_manager.py`:
   ```python
   DEFAULT_SETTINGS = {
       "my_new_feature": {
           "enabled": False,
           "threshold": 50,
       },
       # ... existing defaults
   }
   ```

2. **Access in code**:
   ```python
   enabled = settings_manager.get("my_new_feature.enabled", False)
   threshold = settings_manager.get("my_new_feature.threshold", 50)
   ```

3. **Add to settings JSON** (optional - defaults are used if key missing):
   ```json
   {
     "my_new_feature": {
       "enabled": true,
       "threshold": 75
     }
   }
   ```

---

## 6. Experimental Features

Feature flags for experimental functionality are in the `experimental` namespace:

```json
{
  "experimental": {
    "use_feature_x": false
  }
}
```

**Checking feature flags**:
```python
use_feature = settings_manager.get("experimental.use_feature_x", False)
if use_feature:
    # Use new implementation
else:
    # Use default implementation
```

**Adding a new experimental feature**:
1. Add flag to `DEFAULT_SETTINGS` with `False` default
2. Check flag at feature entry point
3. Document in this guide

---

## 7. Test Configuration

Tests use isolated settings to prevent polluting production config:

```python
# In tests, use isolated_managers fixture
def test_something(isolated_managers):
    # Settings are isolated - changes don't affect production
    settings = inject(SettingsManagerProtocol)
    settings.set("test_key", "test_value")
    # ... test code ...
    # Settings reset automatically after test
```

**Test settings file selection**:
- `isolated_managers` fixture uses `.spritepal-test_settings.json`
- UI tests may use `.spritepal-uitest_settings.json`
- Both are gitignored to prevent accidental commits

---

## 8. Common Settings Keys

| Key Path | Type | Description |
|----------|------|-------------|
| `rom_injection.last_input_rom` | str | Last loaded ROM file path |
| `vram_extraction.default_offset` | int | Default VRAM offset |
| `ui.window_geometry` | dict | Main window position/size |

---

## 9. Troubleshooting

**Settings not persisting?**
- Check file permissions on `.spritepal_settings.json`
- Ensure `settings_manager.save()` is called after changes

**Test affecting production settings?**
- Always use `isolated_managers` fixture in tests
- Check you're not accidentally using `session_managers` without `@pytest.mark.shared_state_safe`

**Feature flag not taking effect?**
- Restart app (some flags are checked only at startup)
- Verify JSON syntax in settings file
- Check default value in `DEFAULT_SETTINGS`

---

*Last updated: December 2024*
