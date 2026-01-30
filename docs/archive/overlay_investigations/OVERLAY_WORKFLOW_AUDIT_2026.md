# Overlay Workflow Audit & Mapping (January 2026)

This document maps the full overlay-application workflow for the tile arrangement dialog, verifying the isolation of tile identity from pixel modification.

## 1. Tile Lifecycle and Data Flow

The tile lifecycle relies on a **"Physical vs. Logical"** distinction, where "Physical" represents the linear ROM data folded into a strip, and "Logical" represents the user's visual arrangement.

### Origin (Physical Data)
- **Source:** Tiles originate in `ROMWorkflowController.current_tile_data` as a linear sequence of 4bpp SNES tiles.
- **Handoff:** For the arrangement dialog, this data is rendered into a temporary PNG (`temp_png`) using the current physical width (`current_width`).
- **Implicit Assumption:** The `current_width` determines the "physical" row/column structure used for indexing.

### Arrangement Dialog (Slicing)
- **Slicing:** `GridArrangementDialog` initializes `GridImageProcessor`, which slices `temp_png` into individual `Image` objects.
- **Identity:** Tiles are keyed by `TilePosition(row, col)`, representing their position in the *physical* source image (and thus their linear index in the ROM).
- **Representation:** `self.tiles` stores these source images. The `Canvas` stores a mapping of `Canvas(r, c) -> Source(TilePosition)`.

### Modification (Overlay Application)
- **Intersection:** The `ApplyOperation` calculates intersections between the **Overlay** and the **Canvas Grid**.
- **Update:** It updates the pixel data of the `TilePosition` corresponding to the canvas cell.
- **Crucial Invariant:** The dictionary keys (`TilePosition`) are **never changed**. Only the `Image` values associated with them are replaced.

### Reinjection (Patching)
- **Return:** The dialog returns `ArrangementResult.modified_tiles` (Source Position -> New Image).
- **Patching:** `ROMWorkflowController._update_tile_data_from_modified_tiles` iterates this dictionary.
  - It calculates the byte offset: `(row * tiles_per_row + col) * 32`.
  - It patches `self.current_tile_data` directly with the new 4bpp data.
- **Risk:** This relies on `tiles_per_row` matching exactly between the dialog's initialization and the controller's patching logic.

### Editor Display
- **Refresh:** `open_in_editor()` is called to refresh the view.
- **Rendering:** It renders the *patched* `current_tile_data` into a new physical image.
- **Transformation:** If `keep_arrangement` was selected, `ArrangementBridge.physical_to_logical` transforms this image into the user's arranged view.
- **Model:** The `EditingController` receives this final image (Logical if arranged, Physical if not).

## 2. Overlay Application Behavior

- **Mapping:** The overlay image (`OverlayLayer`) exists in canvas pixel coordinates.
- **Selection:** `ApplyOperation` iterates through the **Canvas Grid** (where the user placed the tiles).
- **Sampling:**
  - For each populated canvas cell at `(canvas_row, canvas_col)`, it calculates the pixel rectangle.
  - It samples the overlay image at that rectangle.
  - It quantizes the sample to the selected palette (or grayscale).
- **Write-back:**
  - It looks up which **Source Tile** is at that canvas position.
  - It updates that source tile's image data in the `modified_tiles` dictionary.
- **Independence:** The overlay logic does not care about the source tile's original location; it only cares where the user placed it on the canvas relative to the overlay.

## 3. Post-Overlay Expectations

- **Tile Identities:** ✅ Verified preserved. The keys of `modified_tiles` are strictly the source `TilePosition`s.
- **ROM Ordering:** ✅ Verified preserved. The patching process writes back to fixed offsets calculated from the source `TilePosition`.
- **Pixel Editor State:**
  - The editor receives an image that visually reflects the arrangement (if kept).
  - Under the hood, `current_tile_data` holds the correct physical bytes.
  - The user sees the modified pixels in their arranged context.
- **In-Game Layout:** Since `current_tile_data` is patched linearly based on original identities, the in-game rendering (which uses the physical ROM data) will show the modified pixels in their correct original slots, completely ignoring the temporary arrangement used in the dialog.

## 4. UI Consistency

- **Arrangement Dialog:** Accurately reflects that the overlay applies to "what you see".
- **Editor Workspace:**
  - If `keep_arrangement` is true, the editor shows the logical layout, matching the dialog.
  - If false, it reverts to the physical strip, but the pixels are modified.
- **Ambiguities:**
  - The "Export Arrangement" feature in the dialog generates a *new* image file, which is separate from the "Apply Overlay" flow that modifies the ROM data.
  - `ArrangementConfig` stores the overlay *state* (path, position) but **not** the modified pixel data. Pixel data persistence is strictly the responsibility of the main ROM/Project save flow.

## 5. Signal and Event Flow

### A. Dialog Initialization & Overlay
1. **Trigger:** `ROMWorkflowController.show_arrangement_dialog()`
2. **Event:** `GridArrangementDialog` initializes.
3. **Event:** User manipulates `OverlayControls` -> emits `overlay_layer` signals (`position_changed`, etc.).
4. **Action:** User clicks "Apply" -> `_apply_overlay` -> `ApplyOperation.execute()`.
5. **State:** `ApplyOverlayCommand` pushed to undo stack.
6. **Update:** `_update_displays()` called -> Refreshes canvas.

### B. Handoff & Injection
1. **Trigger:** Dialog `accept()`
2. **Data:** `ArrangementResult` passed to `ROMWorkflowController`.
3. **Action:** `_update_tile_data_from_modified_tiles` patches `current_tile_data`.
4. **Event:** `sprite_extracted` signal emitted (with new image) during `open_in_editor()`.
5. **State:** `workflow_state_changed` emitted ("edit").

### C. ROM Save
1. **Trigger:** "Save to ROM" button.
2. **Action:** `ROMWorkflowController.save_to_rom()` called.
3. **Transformation:** If arrangement active, `logical_to_physical` is called to "unscramble" the editor image back to physical order.
4. **Disk I/O:** `ROMInjector` writes data to disk.
5. **Event:** `offset_changed` emitted (to force refresh).

## Flagged Risks

1.  **Tight Coupling of `tiles_per_row`:**
    The system relies on `current_width // 8` being identical at dialog launch and at result processing. If `current_width` is modified externally or if `open_in_editor` recalculates dimensions differently in between, the patch offsets will be wrong, corrupting the sprite.

2.  **Overlay State Desync:**
    The `ArrangementConfig` saves overlay state (position/scale). If the user applies an overlay, closes the dialog *without* saving the layout (`keep_arrangement=False`), the pixel changes are kept (in RAM), but the overlay configuration is lost. If they reopen the dialog, the overlay will be reset, potentially making it hard to re-apply exact changes.
