# Sprite Editor Subsystem

Inherits all rules from `spritepal/CLAUDE.md`. This file covers only subsystem-specific concerns.

## Entry Points

| Use Case | Code |
|----------|------|
| **Standalone app** | `python launch_editor.py` from `spritepal/` |
| **Programmatic** | `from ui.sprite_editor import SpriteEditorApplication; app = SpriteEditorApplication(); app.run()` |
| **Window only** | `from ui.sprite_editor import SpriteEditorMainWindow` |
| **Embed as tab** | `from ui.sprite_edit_tab import SpriteEditTab` |

See `ui/sprite_editor/README.md` for full documentation.

## UI Structure (for Screenshots/Debugging)

The embedded sprite editor uses nested containers:

```
MainWindow
└── center_stack (QStackedWidget)
    ├── [0] ExtractionWorkspace (ROM/VRAM extraction tabs)
    └── [1] SpriteEditorWorkspace
            └── _mode_stack (QStackedWidget)
                ├── [0] VRAMEditorPage (Extract→Edit→Inject→Multi-Palette)
                └── [1] ROMWorkflowPage (Asset browser + editor)
```

**Switching views programmatically:**

```python
# Switch to Sprite Editor workspace
window.switch_to_workspace(1)

# Switch modes within sprite editor
editor = window._sprite_editor_workspace
editor._mode_combo.setCurrentIndex(0)  # VRAM Mode
editor._mode_combo.setCurrentIndex(1)  # ROM Mode

# Switch tabs within VRAM mode
vram_page = editor._vram_page
vram_page.set_current_tab(0)  # Extract
vram_page.set_current_tab(1)  # Edit
vram_page.set_current_tab(2)  # Inject
vram_page.set_current_tab(3)  # Multi-Palette
```

**Taking screenshots** (requires `QT_QPA_PLATFORM=xcb` for WSL):

```python
import os
os.environ['QT_QPA_PLATFORM'] = 'xcb'

from core.configuration_service import ConfigurationService
from core.app_context import create_app_context
from launch_spritepal import SpritePalApp

config = ConfigurationService()
config.ensure_directories_exist()
context = create_app_context('SpritePal', settings_path=config.settings_file, configuration_service=config)
app = SpritePalApp(sys.argv, context=context)

window = app.main_window
window.show()
window.resize(1200, 900)

# Navigate to desired view, then:
pixmap = window.grab()
pixmap.save('/tmp/screenshot.png')
```

## Layer Rules

```
views/ → controllers/ → services/ → core/
              ↓              ↓
          managers/      models/
```

**Enforced boundaries:**
- `views/` never imports `models/` or `services/` directly—only `controllers/` and `managers/`
- `services/` uses `core/tile_utils.py` and `core/palette_utils.py` for SNES format logic—don't reinvent
- `models/` are pure Python (no Qt imports)

## Gotchas

### Undo lambdas must capture values

```python
# Bug: closure captures reference, not value
undo_manager.record_action(
    "paint",
    lambda: model.set_pixel(x, y, old_value),  # old_value mutates!
)

# Fix: default argument captures value at definition time
undo_manager.record_action(
    "paint",
    lambda ov=old_value: model.set_pixel(x, y, ov),
)
```

### Workers must emit errors, never swallow

Workers have an `error` signal. Use it. The error propagates: `Worker.error` → `Controller` → `MainController.show_error_dialog()`.

```python
except OSError as e:
    self.error.emit(f"Read failed: {e}")  # Required
    return
```

## Existing Utilities

Don't rewrite these:

| Need | Use |
|------|-----|
| BGR555 ↔ RGB888 | `core/palette_utils.py` |
| 4bpp encode/decode | `core/tile_utils.py` |
| Signal cleanup | `ui/common/signal_utils.safe_disconnect()` |
| Worker cancellation | `BaseWorker.is_cancelled()` (check every 32 tiles) |

## Current State

- **Tests:** 106 tests across 7 test files covering controller signals, widget validation, panel synchronization, and UI redesign components.
  - Located in `ui/sprite_editor/tests/` (collected automatically by pytest via `pyproject.toml`)
  - Run with: `uv run pytest ui/sprite_editor/tests/`
  - `test_redesign_widgets.py` - Unit tests for new UI widgets (IconToolbar, SpriteAssetBrowser, etc.)
  - `test_redesign_integration.py` - Integration tests for widget-controller signal chains
- **Coverage:** Services are more complete than controllers; tests focus on behavioral verification of signals and widget state.
