# Pyright Ignore Audit Report

**Date:** January 30, 2026
**Scope:** 141 instances of `pyright: ignore`
**Status:** Actionable

## Executive Summary

This audit covers 141 instances of `pyright: ignore` found across the codebase. The vast majority (approx. 90%) are `reportExplicitAny` suppressions resulting from the use of untyped dictionaries (`dict[str, Any]`) for core domain objects like sprite data and scan results.

-   **Total Ignores:** 141
-   **Primary Issue:** Widespread use of `dict[str, Any]` for "Sprite Data" and "Scan Results".
-   **Risk:** Moderate. The lack of strict typing on sprite data dictionaries masks potential key errors (e.g., `decompressed_size` vs `size`) and forces runtime checks/casts.
-   **Top Recommendation:** Introduce `TypedDict` definitions for core domain objects (`SpriteData`, `ScanParams`) to replace loose dictionaries.

---

## Detailed Audit

### 1. Core Data Structures (`reportExplicitAny`)

**Locations:**
-   `ui/models/sprite_gallery_model.py` (Sprite storage)
-   `ui/rom_extraction/workers/scan_worker.py` (Scan results)
-   `core/visual_similarity_search.py` (Metadata)
-   `ui/workers/*.py` (Various worker payloads)

**Root Cause:**
The application passes "sprite information" as loose dictionaries (`dict[str, Any]`) between the backend (workers/extractors) and the frontend (models/views). Pyright correctly flags that accessing fields on `Any` or assigning `Any` to typed variables is unsafe.

**Recommended Fix:**
Create a central types file (e.g., `core/domain_types.py`) and define `TypedDict`s to formalize these contracts.

```python
from typing import TypedDict, NotRequired

class SpriteData(TypedDict):
    offset: int
    offset_hex: str
    decompressed_size: int
    size: NotRequired[int]  # Legacy key support
    tile_count: int
    alignment: str
    quality: NotRequired[float]
    compressed: NotRequired[bool]

class ScanParams(TypedDict):
    start_offset: int
    end_offset: int
    alignment: int
```

**Effort:** Medium (Refactor ~15 files)
**Risk:** Low (Static analysis improvement)

### 2. Signal Blockers (`reportUnusedVariable`)

**Locations:**
-   `ui/sprite_editor/views/panels/tool_panel.py`
-   `ui/sprite_editor/views/panels/palette_panel.py`

**Code:**
```python
blocker = QSignalBlocker(self.tool_group)  # pyright: ignore[reportUnusedVariable]
```

**Root Cause:**
`QSignalBlocker` functions via RAII (resource acquisition is initialization); the variable itself is never read, triggering unused variable warnings.

**Recommended Fix:**
Assign to `_` to indicate intentional discard, which standard linters respect and eliminates the need for the ignore.
```python
_ = QSignalBlocker(self.tool_group)
```
**Effort:** Low
**Risk:** None

### 3. Test Infrastructure (`reportExplicitAny`, `reportAttributeAccessIssue`)

**Locations:**
-   `tests/ui/sprite_editor/test_*.py`
-   `tests/infrastructure/qt_pixmap_guard.py`

**Root Cause:**
1.  `QtBot` is often typed as `Any` because `pytest-qt` types are not strictly imported or available.
2.  `QPixmap._test_guard_installed` is a dynamic monkey-patch used for testing safety.

**Recommended Fix:**
1.  **QtBot:** Create a `tests/conftest.py` or `tests/types.py` that exports a `QtBot` TypeAlias (even if just `Any` for now) or imports the real one if available, avoiding repeated ignores.
2.  **Monkey-patch:** The ignore on `_test_guard_installed` is **justified**. Document it as "Dynamic monkey-patch for test safety" and keep the ignore.

**Effort:** Low
**Risk:** Low

### 4. Dynamic/Generic Qt Signals (`reportExplicitAny`)

**Locations:**
-   `ui/common/signal_utils.py`
-   `ui/frame_mapping/signal_error_handling.py`

**Root Cause:**
Utilities dealing with generic Qt signals (`connect`, `disconnect`) must accept `Any` because Qt's signal mechanism is dynamic in Python.

**Recommended Fix:**
These ignores are **justified**. The nature of these utility functions is to handle *any* signal. Tighter typing (like `Callable[..., Any]`) is already used where possible, but `Any` is often unavoidable here.

**Effort:** None (Keep as is)

### 5. `ApplicationStateManager` Checks (`reportArgumentType`)

**Locations:**
-   `core/managers/application_state_manager.py`

**Code:**
```python
return int(value) if value is not None else 500
```

**Root Cause:**
`value` comes from `QSettings.value()`, which returns `Any` (or `object`). `int()` expects a string or number.

**Recommended Fix:**
Explicitly cast or check the type to satisfy the type checker safely.
```python
if isinstance(value, (int, str)):
    return int(value)
return 500
```

**Effort:** Low
**Risk:** Low

---

## Action Plan

1.  **Define `SpriteData` TypedDict** in `core/domain_types.py`.
2.  **Replace `dict[str, Any]`** with `SpriteData` in `SpriteGalleryModel`, `SpriteScanWorker`, and related files.
3.  **Fix `QSignalBlocker`** usages by assigning to `_`.
4.  **Accept/Document** ignores in `signal_utils.py` and monkey-patches as necessary technical debt.
