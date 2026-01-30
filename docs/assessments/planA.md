# Assessment: Signal Architecture Refactoring Suggestions

## Current State (from codebase analysis)

| Metric | Value |
|--------|-------|
| Total signals in `ui/frame_mapping/` | 137 |
| Parameter-heavy signals (4+ args) | 4 |
| Signal naming compliance | ~95% (`*_requested`, `*_changed`, `*_selected`) |
| View-to-view connections | **None** (all route through Workspace) |
| Signal hub | `FrameMappingWorkspace._connect_signals()` (27 connections) |

---

## Evaluation of Each Suggestion

### 1. Replace "many tiny update signals" with 1–3 delta signals
**Verdict: Partially applicable**

You already have `alignment_updated(ai_id)` doing exactly this. The suggestion to add `MappingChange`/`PaletteChange` typed payloads is sound for **future extensibility** but isn't urgent given your current signal count is manageable and naming is consistent.

**When it would help:** If you find yourself adding `mapping_x_changed`, `mapping_y_changed`, `mapping_scale_changed` as separate signals. Bundle them into `mapping_changed(MappingDelta)` instead.

### 2. Bundle parameter-heavy signals into dataclasses
**Verdict: YES - High value, low risk**

Your `alignment_changed` signal has 7 parameters:
```python
# workbench_canvas.py:223
alignment_changed = Signal(int, int, bool, bool, float, float, str)
# offset_x, offset_y, flip_h, flip_v, scale, extra_param, status_string
```

This is the exact anti-pattern the suggestion addresses. Benefits:
- Versionable (add fields without breaking connections)
- Self-documenting (field names vs positional args)
- Easier tracing (print dataclass, not 7 values)

**Recommendation:** Create `AlignmentState` dataclass, refactor this signal first.

### 3. Make chains "command → result" rather than "signal → signal → signal"
**Verdict: Already doing this well**

Your architecture already follows this pattern:
- Views emit intents (`ai_frame_selected`)
- Workspace calls handler methods (`_on_ai_frame_selected()`)
- Logic helper/controller updates state
- Signals notify UI of changes

The "7 layers" mentioned in review.md isn't problematic if each layer has a clear purpose. Your layers are: View → Workspace → LogicHelper → StateManager → Controller → Service.

**No change needed** unless you're seeing specific "which signal do I emit?" bugs.

### 4. Centralize selection state into SelectionModel
**Verdict: Worth considering**

Current state:
- `WorkspaceStateManager` holds `selected_ai_frame_id`, `selected_game_id`
- `WorkspaceLogicHelper` provides accessors
- Selection signals exist in both `AIFramesPane` and `FrameBrowserPanel`

A unified `SelectionModel(ai_id, game_id, mapping_id)` could eliminate:
- "Wrong capture selected" edge cases
- "Edits applied to stale selection" bugs
- Duplicate signal definitions

**Recommendation:** If you're experiencing these bugs, this is worth doing. If not, current approach is fine.

### 5. Add trace ID for cascades
**Verdict: Low priority**

This is debugging infrastructure. Worth adding if you're spending significant time tracing signal chains. For now, Python's built-in `logging` with `DEBUG` level at signal emission points achieves similar traceability.

**Recommendation:** Defer until you need it. When you do, consider adding optional `action_id: str | None = None` to delta signals.

### 6. Signal taxonomy (`*_requested`, `*_changed`, `*_updated`)
**Verdict: Already compliant**

Your codebase is 95% compliant with this naming convention. The remaining 5% are legacy or represent state query operations (`project_changed`, `error_occurred`, `finished`) which are reasonable exceptions.

---

## Summary: What I'd Actually Do

| Priority | Suggestion | Effort | Value |
|----------|-----------|--------|-------|
| **High** | Bundle `alignment_changed` into dataclass | Small | High |
| Medium | Centralize selection into `SelectionModel` | Medium | Medium (if bugs exist) |
| Low | Delta signals with `MappingChange` | Medium | Low (no current pain) |
| Skip | Trace IDs | Medium | Low (debugging only) |
| Skip | Signal taxonomy | N/A | Already done |

---

## Recommended Implementation (if proceeding)

### Step 1: Create AlignmentState dataclass
```python
# core/data_models/alignment_state.py
@dataclass(frozen=True)
class AlignmentState:
    offset_x: int
    offset_y: int
    flip_h: bool
    flip_v: bool
    scale: float
    # Add fields as needed
```

### Step 2: Refactor WorkbenchCanvas signal
```python
# Before
alignment_changed = Signal(int, int, bool, bool, float, float, str)

# After
alignment_changed = Signal(AlignmentState)
```

### Step 3: Update all connection sites
- `frame_mapping_workspace.py:305-378`
- Any handlers receiving these parameters

### Files to modify:
- `core/data_models/alignment_state.py` (new)
- `ui/frame_mapping/views/workbench_canvas.py`
- `ui/workspaces/frame_mapping_workspace.py`
- Tests for affected signals

---

---

## Investigation: Your "Persistent Issues"

Based on codebase analysis, here's what I found:

### Bugs Already Fixed
| Bug | Status | Commit |
|-----|--------|--------|
| Canvas alignment stale after programmatic updates | **FIXED** | 5509dadf |
| Controls re-enabled after `clear_alignment()` | **FIXED** | Current |
| Frames disappear after auto-align | **Documented** | Tests added |

### Remaining Issues (Likely Your Pain Points)

**1. Auto-Align Doesn't Account for Scale/Flip Transforms**
- `workbench_canvas.py:1645-1851` - `_compute_optimal_alignment()` and `_on_auto_align()`
- When scale != 1.0 or flip_h=True, auto-align calculates offset using untransformed bbox
- Tests document expected behavior: `test_workbench_canvas_auto_align_bug.py:250-382`
- **Root cause:** Calculation bug, not state bug

**2. Async Preview Race Conditions**
- `AsyncPreviewService` emits results after user switches frames
- No visible cancellation logic when frame changes
- Can result in stale preview appearing for wrong frame

**3. Browsing Mode Edge Cases**
- When browsing captures not in mapping, canvas enters browsing mode (line 395)
- Alignment sync behavior unclear in this mode

### What SelectionModel Would Fix

| Issue | SelectionModel Helps? |
|-------|----------------------|
| Auto-align transform bug | No (calculation issue) |
| Async preview race | **Yes** (atomic selection state) |
| Stale canvas after update | Already fixed, but would prevent regression |
| Browsing mode confusion | **Yes** (explicit mode in state) |

### My Assessment

Your "persistent issues" seem to be a mix of:
1. **Auto-align calculation bugs** (not state-related)
2. **Async race conditions** (state-related, SelectionModel helps)

The SelectionModel refactor alone won't fix auto-align. But if you're seeing stale previews or wrong-frame edits, it would help.

---

## Revised Recommendation

Given what I've found, I'd prioritize differently:

| Priority | Action | Why |
|----------|--------|-----|
| **P0** | Fix auto-align transform handling | This is likely your main UX pain |
| P1 | Bundle `alignment_changed` into dataclass | Makes debugging easier |
| P2 | Add preview request cancellation | Prevents stale previews |
| P3 | SelectionModel refactor | Good architecture, but P0-P2 may resolve symptoms |

---

## Implementation Plan (if approved)

### Phase 1: Fix Auto-Align Transform Bug

**Root Cause Analysis:**
The tests in `test_workbench_canvas_auto_align_bug.py` (lines 250-382) document the expected behavior:

1. **Scale bug (line 250):** With scale=0.5, AI content center at (100,100) should have visual center at (50,50). Offset to align with game center (20,20) should be -30, not calculated from unscaled position.

2. **Flip bug (line 318):** With flip_h=True, content center at (20,50) mirrors to (80,50). Offset should be calculated from flipped position.

**Files to modify:**
- `ui/frame_mapping/views/workbench_canvas.py`
  - `_on_auto_align()` (lines 1782-1851) - verify scale/flip applied correctly in offset calculation
  - `_compute_optimal_alignment()` (lines 1645-1780) - verify flip transforms applied before position search

**Implementation:**
1. First run existing tests to confirm they fail: `pytest tests/ui/frame_mapping/views/test_workbench_canvas_auto_align_bug.py -v`
2. Trace the calculation in `_on_auto_align` (else branch, lines 1822-1840):
   - `scaled_ai_center_x = ai_center_x * scale` - this IS accounting for scale
   - But verify `_ai_frame_item.pos()` reflects this correctly
3. Fix likely in how offset translates to item position, or in `set_alignment()` application

**Verify:**
```bash
pytest tests/ui/frame_mapping/views/test_workbench_canvas_auto_align_bug.py -v
pytest tests/ui/frame_mapping/views/test_workbench_canvas_alignment.py -v
```

### Phase 2: AlignmentState Dataclass
**Files:**
- `core/data_models/alignment_state.py` (new)
- `ui/frame_mapping/views/workbench_canvas.py`
- `ui/workspaces/frame_mapping_workspace.py`
- Related tests

**Change:** Replace 7-parameter signal with typed dataclass

### Phase 3: Preview Cancellation (if needed after P0/P1)
**Files:**
- `ui/frame_mapping/services/async_preview_service.py`
- `ui/frame_mapping/workspace_logic_helper.py`

**Change:** Add request ID tracking and cancellation on frame change

---

## Verification Plan

After implementation, verify end-to-end:

### Automated Tests
```bash
# Phase 1 verification
pytest tests/ui/frame_mapping/views/test_workbench_canvas_auto_align_bug.py -v
pytest tests/ui/frame_mapping/views/test_workbench_canvas_alignment.py -v

# Phase 2 verification (after dataclass refactor)
pytest tests/ui/frame_mapping/ -v -k "alignment"

# Full suite regression
pytest -n auto --dist=loadscope
```

### Manual Verification
```bash
# Launch app
uv run python launch_spritepal.py
```
1. Load a mapping project
2. Select an AI frame with content not centered
3. Set scale to 0.5, click Auto-Align → content center should align with game center
4. Toggle Flip H, click Auto-Align → flipped content center should align
5. Test with Match Scale checked → scale should adjust to fit content in tiles

### Visual Verification (headless)
```bash
# Render before and after to compare
uv run python scripts/render_workbench.py -p mapping.spritepal-mapping.json -m 0 -o /tmp/workbench.png
```

---

## Summary

| Phase | Scope | Effort |
|-------|-------|--------|
| Phase 1 | Fix auto-align scale/flip bugs | ~1-2 hours |
| Phase 2 | AlignmentState dataclass refactor | ~2-3 hours |
| Phase 3 | Preview cancellation (if needed) | ~1 hour |

**Critical files:**
- `ui/frame_mapping/views/workbench_canvas.py` (1645-1851)
- `tests/ui/frame_mapping/views/test_workbench_canvas_auto_align_bug.py`

Proceeding with Phase 1 first since it addresses the confirmed UX pain point.
