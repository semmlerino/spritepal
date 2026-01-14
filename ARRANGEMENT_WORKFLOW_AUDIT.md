# Sprite Arrangement & Overlay Workflow Audit

## 1. Workflow Map

### A) Opening & Arrangement Mode
- **User Action:** Open Sprite -> Click "Arrange Tiles" in Editor.
- **Inputs:** `current_tile_data` (from Editor memory), `ArrangementConfig` (from sidecar file).
- **Transforms:** 
  - `show_arrangement_dialog` writes `current_tile_data` to temp PNG.
  - `GridArrangementDialog` loads PNG, slices into `self.tiles`.
  - `_restore_arrangement_state` applies layout from config.
- **Expected:** Layout restored. Overlay restored (pos/scale/opacity).
- **Actual (Pre-Fix):** Overlay scale was RESET to 1.0/Auto. (Fixed)

### B) Overlay Import & Positioning
- **User Action:** Import Overlay, Scale/Move.
- **Inputs:** Overlay image file.
- **Transforms:** `OverlayLayer` stores `_image`, `_x`, `_y`, `_scale`. Visuals updated.
- **State:** `OverlayLayer` holds float coordinates.

### C) Apply Overlay (Commit)
- **User Action:** Click "Apply Overlay to Arranged Tiles".
- **Inputs:** `OverlayLayer` state, `self.tiles`, `grid_mapping`.
- **Transforms:** `ApplyOperation.execute()`
  - Iterates mapped tiles.
  - Calls `OverlayLayer.sample_region(tile_x, tile_y, ...)`.
  - **Pre-Fix:** `sample_region` returned `None` if tile not **fully** covered.
  - **Post-Fix:** `sample_region` returns clipped RGBA image for partial overlap.
  - **Behavior Change:** `ApplyOperation` completely replaces original tile with sample. Untouched areas become transparent (0).
- **Writes:** `self.tiles` updated in memory. `ApplyResult` stored.
- **UX Update:** 
  - Automatically hides the overlay (`visible=False`) after application.
  - Dynamically disables the "Apply" button when overlay is hidden.
  - Blocks `_apply_overlay` execution with a warning if triggered while hidden.
- **Code Cleanup:** Removed brittle `blockSignals` anti-pattern in `OverlayControls` to ensure emitted signals always reflect true model state.

### D) Dialog Acceptance
- **User Action:** Click OK / Export.
- **Transforms:** `GridArrangementDialog` packages `modified_tiles` into `ArrangementResult`.
- **Writes:** `ArrangementResult` returned to `ROMWorkflowController`.

### E) Persistence & Reload
- **User Action:** Dialog closes. `ROMWorkflowController` handles result.
- **Transforms:** 
  - `_update_tile_data_from_modified_tiles` patches `current_tile_data` (bytearray).
  - `_save_arrangement_config` saves layout to JSON.
  - `open_in_editor()` reloads editor with new `current_tile_data`.
- **Expected:** Modifications persist in Editor. Arrangement layout persists in JSON.
- **Actual (Pre-Fix):** `overlay_scale` lost in JSON. Reopening dialog showed misaligned overlay.

## 2. Failure Matrix

| Failure Point | Root Cause | Symptom | Fix |
| :--- | :--- | :--- | :--- |
| **Persistence** | `ArrangementConfig` missing `overlay_scale` field. | Reopening Arrangement Dialog resets overlay scale, misaligning it. | Added `overlay_scale` to `ArrangementConfig`. Updated `GridArrangementDialog` to save/restore it. |
| **Apply Logic** | `OverlayLayer.sample_region` enforced strict containment. | Partially covered tiles were ignored (untouched). | Updated `sample_region` to handle intersection/clipping. |
| **Composition** | `ApplyOperation` behavior clarified. | N/A | `ApplyOperation` intentionally replaces tile content. Untouched areas become transparent. |

## 3. Fixes Implemented

### Core Persistence
- Modified `core/arrangement_persistence.py`: Added `overlay_scale` to dataclass, `save()`, and `load()`.
- Modified `ui/grid_arrangement_dialog.py`: 
  - In `get_arrangement_result`: Inject `overlay_scale` into metadata.
  - In `_restore_arrangement_state`: Restore `overlay_scale` before position to ensure correct centering logic.

### Overlay Logic
- Modified `ui/row_arrangement/overlay_layer.py`: 
  - Rewrote `sample_region` to calculate intersection between tile and overlay.
  - Returns a tile-sized RGBA image with transparent padding for uncovered areas.
- Modified `core/apply_operation.py`:
  - In `execute`: Removed composition logic. The sampled region (including transparent areas) now strictly replaces the original tile content.

## 4. Verification
- Created `tests/ui/test_arrangement_overlay_fixes.py` asserting:
  1. `ArrangementConfig` persists `overlay_scale`.
  2. `ApplyOperation` modifies a partially covered tile and clears untouched areas (checking for strict replacement).
- **Result:** Both tests PASSED after updates.
