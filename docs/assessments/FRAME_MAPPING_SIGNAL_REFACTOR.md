# Frame Mapping Signal System Refactor Plan

## Overview

**Goal:** Behavior-preserving refactor to address signal system technical debt AND advance architecture per review.md guidelines.

**Current State:** 50+ signals across 3 layers (Service → Controller → Workspace) with mature patterns (debouncing, targeted updates, early disconnect). Recent commits (73efa162, 5509dadf) established good foundations.

**Status Summary:**
| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Lambda Memory Leak Elimination | **DONE** |
| 2 | Signal Handler Error Boundaries | **DONE** |
| 3 | Bundle Parameter-Heavy Signals | **DONE** |
| 4 | Centralize Selection State | DEFERRED (low priority) |
| 5 | Undo/Redo Signal-Driven Sync | **DONE** |
| 6 | Golden Trace Infrastructure | **DONE** |

**Architectural Principles (from review.md):**
- Views emit intents (`*_requested`), Controller emits deltas (`*_changed`)
- Bundle parameter-heavy signals into dataclasses
- Centralize selection state
- Avoid View → View connections
- Prefer direct calls over signal chains once past UI boundary

**Remaining Issues:**
| Priority | Issue | Impact |
|----------|-------|--------|
| MEDIUM | Missing error handling in signal handlers | UI corruption on exceptions |
| MEDIUM | Selection state scattered across workspace | "Edits applied to stale selection" bugs |
| MEDIUM | Manual undo/redo UI sync | Error-prone as system grows |

---

## Phase 1: Lambda Memory Leak Elimination - DONE

> **Status:** Completed. All context menu lambdas replaced with `functools.partial`.

### Problem (Resolved)
Context menu lambdas captured `self` + local variables, creating potential circular references.

**Fixed locations:**
- `ui/frame_mapping/views/ai_frames_pane.py` - uses `functools.partial`
- `ui/frame_mapping/views/captures_library_pane.py` - uses `functools.partial`
- `ui/frame_mapping/views/mapping_panel.py` - uses `functools.partial`

### Step 1.1: AIFramesPane Context Menu

**Change:**
```python
# BEFORE:
rename_action.triggered.connect(lambda: self._show_rename_dialog(frame_id))

# AFTER:
from functools import partial
rename_action.triggered.connect(partial(self._show_rename_dialog, frame_id))
```

**Files:** `ui/frame_mapping/views/ai_frames_pane.py`

**Verify:**
```bash
pytest tests/ui/frame_mapping/views/test_ai_frames_pane.py -v
# Manual: Right-click AI frame, verify all menu actions work
```

**Rollback:** `git checkout -- ui/frame_mapping/views/ai_frames_pane.py`

### Step 1.2: CapturesLibraryPane Context Menu

Same pattern for 4 lambdas at lines 250, 255, 258, 267.

**Files:** `ui/frame_mapping/views/captures_library_pane.py`

**Verify:**
```bash
pytest tests/ui/frame_mapping/views/test_captures_library_pane.py -v
```

### Step 1.3: MappingPanel Context Menu

Same pattern for 4 lambdas at lines 606, 610, 615, 620.

**Files:** `ui/frame_mapping/views/mapping_panel.py`

**Verify:**
```bash
pytest tests/ui/frame_mapping/views/test_mapping_panel.py -v
```

### Step 1.4: Add Memory Leak Regression Test

**New file:** `tests/ui/frame_mapping/views/test_context_menu_cleanup.py`

```python
def test_context_menu_releases_references(qtbot):
    """Verify context menu lambdas don't create circular references."""
    import weakref, gc
    pane = AIFramesPane()
    # ... setup and trigger context menu ...
    menu_ref = weakref.ref(menu)
    menu.close()
    gc.collect()
    assert menu_ref() is None, "Menu not released - memory leak"
```

---

## Phase 2: Signal Handler Error Boundaries (MEDIUM)

### Problem
Signal handlers lack try/except; exceptions propagate to Qt event loop.

**Affected handlers (verified):**
- `ui/workspaces/frame_mapping_workspace.py:1256-1281` (`_on_alignment_updated`)
- `ui/workspaces/frame_mapping_workspace.py` (`_on_preview_cache_invalidated`)

### Step 2.1: Create Error Boundary Decorator

**New file:** `ui/frame_mapping/signal_error_handling.py`

```python
from functools import wraps
from utils.logging_config import get_logger

logger = get_logger(__name__)

def signal_error_boundary(handler_name: str | None = None):
    """Decorator to catch and log exceptions in signal handlers."""
    def decorator(func):
        name = handler_name or func.__name__
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                logger.exception("Error in signal handler %s", name)
        return wrapper
    return decorator
```

### Step 2.2: Apply to Critical Handlers

**Files:** `ui/workspaces/frame_mapping_workspace.py`

```python
@signal_error_boundary("_on_alignment_updated")
def _on_alignment_updated(self, ai_frame_id: str) -> None:
    # ... existing implementation unchanged ...
```

**Verify:**
```bash
pytest tests/ui/frame_mapping/ -v -k "alignment"
```

---

## Phase 3: Bundle Parameter-Heavy Signals - DONE

> **Status:** Completed. `AlignmentState` dataclass implemented.

### Problem (Resolved)
`alignment_changed` had 7 positional parameters, making it fragile and hard to trace.

### Implementation
- **AlignmentState dataclass:** `ui/frame_mapping/views/workbench_types.py:46`
- **WorkbenchCanvas signal:** `alignment_changed = Signal(AlignmentState)` at line 226
- All emission sites and handlers updated to use the dataclass

---

## Phase 4: Centralize Selection State (MEDIUM - per review.md)

### Problem
Selection state is scattered:
- `_state.selected_ai_frame_id` in workspace
- Canvas tracks its own "current game frame"
- "Edits applied to stale selection" edge cases

### Step 4.1: Create SelectionModel

**New file:** `ui/frame_mapping/selection_model.py`

```python
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal

@dataclass
class SelectionState:
    ai_frame_id: str | None = None
    game_frame_id: str | None = None
    mapping_id: str | None = None  # Derived from ai_frame_id if mapped

class SelectionModel(QObject):
    """Single source of truth for frame mapping selection."""
    selection_changed = Signal(SelectionState)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = SelectionState()

    def select_ai_frame(self, frame_id: str | None) -> None:
        self._state = SelectionState(ai_frame_id=frame_id, ...)
        self.selection_changed.emit(self._state)
```

### Step 4.2: Wire SelectionModel to Panes

Replace scattered selection tracking with single model.

**Verify:**
```bash
pytest tests/ui/frame_mapping/ -v -k "selection"
```

---

## Phase 5: Undo/Redo Signal-Driven Sync (MEDIUM)

### Problem
Undo operations restore state but require manual UI refresh, which is error-prone.

### Step 5.1: Add Signal Emission to Undo Commands

**Files:** `ui/frame_mapping/undo/` (command classes)

**Change:** Make `undo()` methods emit the same signals as forward operations:

```python
class UpdateAlignmentCommand:
    def undo(self):
        self._controller._apply_alignment(self._ai_frame_id, self._old)
        # NEW: Emit signal so UI auto-updates
        self._controller.alignment_updated.emit(self._ai_frame_id)
```

**Apply to:**
- `UpdateAlignmentCommand` → `alignment_updated`
- `CreateMappingCommand` → `mapping_created`
- `RemoveMappingCommand` → `mapping_removed`

**Verify:**
```bash
pytest tests/unit/ui/frame_mapping/controllers/test_frame_mapping_undo.py -v
```

---

## Phase 6: Golden Trace Infrastructure - DONE

> **Status:** Completed. Signal trace recorder and golden trace tests implemented.

### Implementation

**New file:** `tests/infrastructure/signal_trace_recorder.py`
- `SignalEvent` and `SignalTrace` dataclasses for recording emissions
- `SignalCollector` class for connecting to real Qt signals or mocks
- Assertion helpers: `assert_trace_contains`, `assert_signal_emitted`, `assert_signal_args`

**New file:** `tests/ui/frame_mapping/test_golden_signal_traces.py`
- `TestCreateMappingUndoSignals`: Verifies undo emits `mapping_removed` or `mapping_created`
- `TestRemoveMappingUndoSignals`: Verifies undo emits both `mapping_created` and `alignment_updated`
- `TestUpdateAlignmentUndoSignals`: Verifies undo emits `alignment_updated`
- `TestSignalCollectorIntegration`: Unit tests for the trace recorder itself

**Regression targets covered:**
- 246b9b35: Missing signal emissions in 7 undo commands
- cb38ae69: Selection sync broken after undo/redo

**Verify:**
```bash
pytest tests/ui/frame_mapping/test_golden_signal_traces.py -v
```

---

## Behavioral Contracts Checklist

### Invariants to Preserve

- [ ] `mapping_created` always followed by `save_requested`
- [ ] `sheet_palette_changed` triggers preview invalidation for all game frames
- [ ] `alignment_updated` never causes canvas content clear (targeted update only)
- [ ] No signal handler blocks for >100ms
- [ ] Worker thread signals disconnect BEFORE `wait()` call
- [ ] Debounced operations capture state at schedule-time, not fire-time

### Error Handling

- [ ] Signal handler exceptions log but don't crash Qt event loop
- [ ] Failed operations emit `error_occurred` signal
- [ ] Partial batch failures don't prevent subsequent attempts

---

## Verification Commands

**Per-step:**
```bash
uv run ruff check . && uv run ruff format . && uv run basedpyright core ui utils
pytest tests/ui/frame_mapping/ -v --tb=short
```

**Full suite (after each phase):**
```bash
pytest tests/ui/frame_mapping/ -v -n auto --dist=loadscope
```

**Rollback procedure:**
```bash
git diff  # Review changes
git checkout -- <file>  # Revert specific file
pytest tests/ui/frame_mapping/ -v  # Verify baseline restored
```

---

## Execution Order

**Completed:**
1. ~~**Phase 1** (Lambda leaks)~~ - DONE
2. ~~**Phase 3** (AlignmentState dataclass)~~ - DONE

**Next (stability fixes):**
3. **Phase 2** (Error boundaries) - Steps 2.1-2.2, single commit

**Architectural (per review.md):**
4. **Phase 4** (SelectionModel) - Steps 4.1-4.2, single commit

**Follow-up:**
5. **Phase 5** (Undo signals) - Step 5.1, verify with golden traces
6. **Phase 6** (Golden traces) - Verification infrastructure

**Remaining scope:** ~4 files modified, 3 new files, ~200 lines changed

---

## Files to Modify

| File | Phase | Status |
|------|-------|--------|
| `ui/frame_mapping/views/ai_frames_pane.py` | 1.1 | **DONE** |
| `ui/frame_mapping/views/captures_library_pane.py` | 1.2 | **DONE** |
| `ui/frame_mapping/views/mapping_panel.py` | 1.3 | **DONE** |
| `ui/frame_mapping/views/workbench_types.py` | 3.1 | **DONE** (AlignmentState) |
| `ui/frame_mapping/views/workbench_canvas.py` | 3.2 | **DONE** |
| `ui/frame_mapping/signal_error_handling.py` | 2.1 | TODO: Error boundary decorator |
| `ui/workspaces/frame_mapping_workspace.py` | 2.2, 4.2 | TODO: Apply decorator; wire SelectionModel |
| `ui/frame_mapping/selection_model.py` | 4.1 | TODO: Centralized selection state |
| `ui/frame_mapping/undo/*.py` | 5.1 | **DONE**: Undo commands emit signals |
| `tests/infrastructure/signal_trace_recorder.py` | 6.1 | **DONE**: Golden trace utility |
| `tests/ui/frame_mapping/test_golden_signal_traces.py` | 6.2 | **DONE**: Golden trace tests |

---

## Alignment with review.md

| Recommendation | Status | Phase |
|----------------|--------|-------|
| Bundle parameter-heavy signals into dataclasses | **DONE** | 3 (AlignmentState) |
| Centralize selection state | TODO | 4 (SelectionModel) |
| Replace many tiny signals with delta signals | Deferred | Future work |
| Add trace ID for cascades | TODO | 6 (golden traces) |
| Signal taxonomy (*_requested vs *_changed) | N/A | Already followed |
| Avoid View → View connections | N/A | No such connections found |

**Not addressed in this plan (future work):**
- Consolidating signals into 1-3 delta signals (e.g., `mapping_changed(ai_id, change: MappingChange)`)
- Runtime trace IDs in signal payloads

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Error boundary hides bugs | Log at ERROR level with full traceback |
| SelectionModel adds complexity | Start with workspace-only; migrate panes incrementally |
| Undo signal changes cause loops | Commands emit same signals as forward ops; no new handlers |
| Golden traces become stale | Only regenerate intentionally; treat as documentation |
