# Sprite Editor Subsystem

Inherits all rules from `spritepal/CLAUDE.md`. This file covers only subsystem-specific concerns.

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

- **Tests:** 48 tests across 5 test files covering controller signals, widget validation, and panel synchronization.
  - Located in `ui/sprite_editor/tests/` (collected automatically by pytest via `pyproject.toml`)
  - Run with: `uv run pytest ui/sprite_editor/tests/`
- **Coverage:** Services are more complete than controllers; tests focus on behavioral verification of signals and widget state.
