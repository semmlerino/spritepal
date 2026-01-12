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

## 8. Logging Configuration

SpritePal provides per-category logging control via **Settings → Logging tab**. This feature allows developers and advanced users to enable detailed logging for specific subsystems without flooding the logs with noise from unrelated components.

### Logging Categories

The following categories can be toggled independently:

| Category | Component | Purpose |
|----------|-----------|---------|
| **ROM Extraction** | `core/rom_extractor.py` | Track sprite extraction from ROM files |
| **Tile Rendering** | `core/tile_utils.py` | Monitor 4bpp tile decoding/encoding operations |
| **Thumbnail Worker** | `ui/workers/batch_thumbnail_worker.py` | Log thumbnail generation progress and caching |
| **Tile Hash Database** | `core/services/tile_hash_database.py` | Track tile deduplication and matching |
| **ROM Tile Matcher** | `core/mesen_integration/rom_tile_matcher.py` | Monitor ROM offset discovery via Mesen2 |
| **HAL Compression** | `core/hal_compression.py` | Log HAL (de)compression operations |
| **All UI Workers** | `ui/workers/` | Toggle all UI worker threads collectively |
| **Debug Logging** | Global | Global debug mode (additional verbose output across all categories) |

### Accessing Logging Settings

```python
from core.app_context import get_app_context
from utils.logging_config import get_noisy_categories

# Get current logging state
app_state = get_app_context().application_state_manager
logging_settings = app_state.settings.get("logging", {})

# Check if a specific category is enabled
rom_extraction_enabled = logging_settings.get("rom_extraction", False)

# Query available categories
noisy_categories = get_noisy_categories()
for category, description in noisy_categories.items():
    print(f"{category}: {description}")
```

### Settings UI

The Logging tab in Settings → Logging provides:
- Checkbox for each logging category (ROM Extraction, Tile Rendering, etc.)
- Global "Debug Logging" toggle for comprehensive output
- All settings persist via `ApplicationStateManager`

**Implementation**: `ui/dialogs/settings_dialog.py:_create_logging_tab()`

### Default Behavior

- **Production**: All logging categories disabled by default (clean logs)
- **Tests**: Isolated logging state per-test via `app_context` fixture
- **Configuration**: Persisted in `.spritepal_settings.json` under `logging` key

---

## 9. Common Settings Keys

| Key Path | Type | Description |
|----------|------|-------------|
| `rom_injection.last_input_rom` | str | Last loaded ROM file path |
| `vram_extraction.default_offset` | int | Default VRAM offset |
| `ui.window_geometry` | dict | Main window position/size |
| `logging.<category>` | bool | Per-category logging toggle (see Logging Configuration section) |
| `debug_logging` | bool | Global debug mode toggle |

---

## 10. Troubleshooting

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

*Last updated: January 12, 2026 (Added Logging Configuration section)*
