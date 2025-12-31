# SpritePal Configuration Guide

This document explains how settings and configuration work in SpritePal.

---

## 1. Settings Files

SpritePal uses JSON files for persistent settings. Three files serve different contexts:

| File | Purpose | When Used |
|------|---------|-----------|
| `.spritepal_settings.json` | Production settings | Normal app launch |
| `.spritepal-test_settings.json` | Unit test settings | When tests use `app_context` fixture |
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
│ Step 3: initialize_managers()        │  core/managers/__init__.py
│ Passes settings_file to managers     │
│ Creates AppContext with managers     │
└──────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ Step 4: ApplicationStateManager      │  core/managers/application_state_manager.py
│ _load_settings()                     │
│ Merges JSON with defaults            │
└──────────────────────────────────────┘
```

---

## 3. ConfigurationService

**File**: `core/configuration_service.py`

The ConfigurationService computes all application paths from a single root:

```python
from core.configuration_service import ConfigurationService

config = ConfigurationService()

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

Settings are managed through `ApplicationStateManager`:

```python
from core.app_context import get_app_context

app_state = get_app_context().application_state_manager

# Read a setting
value = app_state.settings.get("some_key", default_value)

# Read a nested setting
last_rom = app_state.settings.get("rom_injection.last_input_rom", "")

# Write a setting
app_state.settings.set("some_key", new_value)
app_state.settings.save_session()  # Persist to disk
```

**Note:** Access settings via `get_app_context().application_state_manager`.

---

## 5. Adding a New Setting

1. **Add default value** in `core/managers/application_state_manager.py`:
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
from core.app_context import get_app_context

app_state = get_app_context().application_state_manager
use_feature = app_state.settings.get("experimental.use_feature_x", False)
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
# In tests, use app_context fixture
def test_something(app_context):
    # Settings are isolated - changes don't affect production
    app_state = app_context.application_state_manager
    app_state.settings.set("test_key", "test_value")
    # ... test code ...
    # Settings reset automatically after test
```

**Test settings file selection**:
- `app_context` fixture uses `.spritepal-test_settings.json`
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
- Ensure `settings_manager.save_session()` is called after changes

**Test affecting production settings?**
- Always use `app_context` fixture in tests
- Check you're not accidentally using `session_app_context` without `@pytest.mark.shared_state_safe`

**Feature flag not taking effect?**
- Restart app (some flags are checked only at startup)
- Verify JSON syntax in settings file
- Check default value in `DEFAULT_SETTINGS`

---

*Last updated: December 26, 2025 (Replaced inject() with get_app_context() pattern)*
