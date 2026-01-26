# Frame Mapping Workflow Audit: UI-Logic Desynchronization

**Date:** Jan 24, 2026
**Scope:** Frame Mapping Workspace (UI, Controller, Core)

## 1. State Map & Sources of Truth

The Frame Mapping workflow distributes state across three layers.

| Component | Type | State Held | Source of Truth? |
|-----------|------|------------|------------------|
| **`FrameMappingProject`** | Data Class | `ai_frames`, `game_frames`, `mappings`, `sheet_palette` | **YES** (Core Model) |
| **`FrameMappingController`** | Controller | `_project` (ref), `_game_frame_previews` (cache) | Proxy / Cache |
| **`FrameMappingWorkspace`** | UI | `_selected_ai_frame_id`, `_selected_game_id`, `_current_canvas_game_id` | UI Selection State |
| **`MappingPanel`** | UI | `_game_frame_previews` (copy), `_user_checked_ai_frame_ids` | UI View State |
| **`WorkbenchCanvas`** | UI | `_current_ai_frame`, `_current_game_frame`, `_alignment` | Canvas Visual State |

**Key Dependencies:**
*   **Preview Generation**: Relies on `CaptureRenderer` + `SheetPalette` (for composites).
*   **Injection**: Relies on `InjectionOrchestrator` + `FrameMappingProject`.

## 2. Desynchronization Inventory

### A. Alignment Persistence (Critical Data Loss Risk)
*   **Symptom**: User adjusts alignment (drag/nudge), closes application or loads new project, and changes are lost.
*   **Cause**: `FrameMappingController.update_mapping_alignment` updates the in-memory project model but **does not emit `save_requested`** or trigger a save. Unlike `create_mapping` or `inject_mapping`, alignment changes are transient until a manual save occurs.
*   **Impact**: High. Silent data loss of tedious alignment work.
*   **Fix**: Add `self.save_requested.emit()` to `FrameMappingController.update_mapping_alignment`.

### B. Canvas/Selection "Split Brain"
*   **Symptom**: Potential for the canvas to show a different game frame than the one being edited, leading to erroneous alignment of the wrong pair.
*   **Cause**: `_selected_game_id` (selection) and `_current_canvas_game_id` (visual) are tracked separately.
*   **Mitigation Existing**: `WorkbenchCanvas._on_alignment_changed` explicitly checks `if self._current_canvas_game_id != mapping.game_frame_id` to block edits.
*   **Status**: Mitigated, but brittle. Relying on UI state flags instead of a unified view model.

### C. Palette Update Lag
*   **Symptom**: Editing the sheet palette in `AIFramePaletteEditorWindow` might not immediately update the game frame thumbnails in `MappingPanel` if they rely on baked previews.
*   **Analysis**:
    *   `MappingPanel` thumbnails are generated from `CaptureRenderer` (using capture palette) or loaded from disk (AI frames).
    *   AI Frame thumbnails: Loaded from disk. `AIFramePaletteEditorWindow` saves to disk, then Workspace calls `refresh()`. This *should* work, provided `QPixmap` doesn't cache stale file handles.
    *   Composite Previews (Canvas): Workspace correctly listens to `sheet_palette_changed` and calls `canvas.set_sheet_palette`, which triggers a re-render.
*   **Status**: Low risk, mostly handled.

### D. Missing Undo/Redo
*   **Symptom**: Users cannot undo alignment changes or mapping creations.
*   **Cause**: No `UndoStack` or Command pattern implementation in `FrameMappingController` or `FrameMappingWorkspace`. Only `AIFramePaletteEditorWindow` has undo support (local to that window).
*   **Impact**: Medium/High (UX friction). "Desync" between user expectation and system capability.

## 3. Palette Deep Dive

*   **Accuracy**:
    *   **Capture**: Uses 15-bit SNES palette converted to RGB.
    *   **AI Frames**: 32-bit RGBA PNGs.
    *   **Preview**: `SpriteCompositor` composites RGBA AI frame over Game frame.
    *   **Injection**: `ROMInjector` quantizes AI frame pixels to the target palette.
*   **Risk**: The *Preview* uses `SpriteCompositor` which might use a slightly different blending/quantization algorithm than the *Injector* (`ROMInjector`).
    *   `WorkbenchCanvas` uses `SpriteCompositor(quantize=True)`. This attempts to simulate injection results.
    *   **Warning**: If `sheet_palette` is not set, `SpriteCompositor` might behave differently (using dynamic palette vs fixed).

## 4. Recommendations

### Priority 1: Fix Data Loss (Alignment Persistence)
Modify `ui/frame_mapping/controllers/frame_mapping_controller.py`:
```python
def update_mapping_alignment(self, ...):
    if self._project.update_mapping_alignment(...):
        self.alignment_updated.emit(ai_frame_id)
        self.save_requested.emit()  # <-- ADD THIS
        return True
```
This ensures every drag/nudge event marks the project for auto-save (handled by `FrameMappingWorkspace._auto_save_after_injection` logic, or explicitly connect signal). Note: Workspace currently connects `save_requested` to `_auto_save_after_injection`.

### Priority 2: Implement Undo/Redo
Refactor `FrameMappingController` to use a `QUndoStack`.
*   Wrap `update_mapping_alignment`, `create_mapping`, `remove_mapping` in `QUndoCommand` subclasses.
*   Expose `undo()`/`redo()` methods to the Workspace toolbar.

### Priority 3: Unify Selection State
Move selection state (`selected_ai_id`, `selected_game_id`) into a `FrameMappingSelectionModel` or the Controller itself, rather than managing it in the Workspace widget. This prevents "split brain" where the Drawer thinks row X is selected but the Canvas shows frame Y.

### Priority 4: Stale Entry Warning Improvements
The current "Stale Entries" warning is reactive (during injection). Proactively check `selected_entry_ids` against `mtime` or file content when loading the project to warn users *before* they start working.

## 5. Invariants & Assertions

*   **Invariant 1**: `mapping.ai_frame_id` MUST exist in `project.ai_frames`. (Enforced by `_prune_orphaned_mappings`).
*   **Invariant 2**: `mapping.game_frame_id` MUST exist in `project.game_frames`.
*   **Invariant 3**: Canvas alignment controls MUST only be enabled if `current_canvas_game_id == mapping.game_frame_id`.
