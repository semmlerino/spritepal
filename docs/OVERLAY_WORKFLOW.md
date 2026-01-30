# Overlay Application Workflow

**Last updated:** January 30, 2026

This document maps the overlay-application workflow for the tile arrangement dialog, describing how tile identity is preserved during pixel modification and reinjection.

> **Consolidated from:** Multiple investigation documents created during overlay workflow debugging (January 2026). Archived versions available in `docs/archive/overlay_investigations/`.

---

## 1. Tile Lifecycle and Data Flow

The tile lifecycle relies on a **"Physical vs. Logical"** distinction:
- **Physical:** Linear ROM data representing tiles in their ROM order
- **Logical:** User's visual arrangement on the canvas

### Origin (Physical Data)
- **Source:** Tiles originate in `ROMWorkflowController.current_tile_data` as a linear sequence of 4bpp SNES tiles.
- **Handoff:** For the arrangement dialog, this data is rendered into a temporary PNG using the current physical width (`current_width`).
- **Implicit Assumption:** The `current_width` determines the "physical" row/column structure used for indexing.

### Arrangement Dialog (Slicing)
- **Slicing:** `GridArrangementDialog` initializes `GridImageProcessor`, which slices the temp PNG into individual `Image` objects.
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

---

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

---

## 3. Post-Overlay Invariants

| Invariant | Status | Notes |
|-----------|--------|-------|
| **Tile Identities** | ✅ Preserved | Keys of `modified_tiles` are strictly the source `TilePosition`s |
| **ROM Ordering** | ✅ Preserved | Patching writes to fixed offsets calculated from source `TilePosition` |
| **In-Game Layout** | ✅ Unchanged | Physical ROM data determines rendering; arrangement is purely visual |

**Pixel Editor State:**
- The editor receives an image that visually reflects the arrangement (if kept).
- Under the hood, `current_tile_data` holds the correct physical bytes.
- The user sees the modified pixels in their arranged context.

---

## 4. UI Consistency Notes

| Scenario | Behavior |
|----------|----------|
| **Keep layout = true** | Editor shows logical layout matching the dialog |
| **Keep layout = false** | Editor reverts to physical strip (pixels still modified) |
| **Export Arrangement** | Generates new image file; separate from Apply Overlay flow |
| **ArrangementConfig** | Stores overlay *state* (path, position), NOT pixel data |

---

## 5. Signal and Event Flow

### A. Dialog Initialization & Overlay
1. `ROMWorkflowController.show_arrangement_dialog()` triggers dialog
2. `GridArrangementDialog` initializes
3. User manipulates `OverlayControls` → emits `overlay_layer` signals
4. User clicks "Apply" → `_apply_overlay` → `ApplyOperation.execute()`
5. `ApplyOverlayCommand` pushed to undo stack
6. `_update_displays()` refreshes canvas

### B. Handoff & Injection
1. Dialog `accept()` triggered
2. `ArrangementResult` passed to `ROMWorkflowController`
3. `_update_tile_data_from_modified_tiles` patches `current_tile_data`
4. `sprite_extracted` signal emitted during `open_in_editor()`
5. `workflow_state_changed` emitted ("edit")

### C. ROM Save
1. "Save to ROM" button triggered
2. `ROMWorkflowController.save_to_rom()` called
3. If arrangement active: `logical_to_physical` unscrambles editor image
4. `ROMInjector` writes data to disk
5. `offset_changed` emitted to force refresh

---

## 6. Known Risks

1. **Tight Coupling of `tiles_per_row`:**
   The system relies on `current_width // 8` being identical at dialog launch and at result processing. If dimensions change between operations, patch offsets will be wrong.

2. **Overlay State Desync:**
   `ArrangementConfig` saves overlay state (position/scale). If user applies overlay then closes dialog without keeping layout, pixel changes remain in RAM but overlay configuration is lost.

---

## Key Code References

| Component | Location |
|-----------|----------|
| Tile data source | `ROMWorkflowController.current_tile_data` |
| Overlay application | `ApplyOperation` in `core/apply_operation.py` |
| Tile slicing | `GridImageProcessor.process_sprite_sheet_as_grid` |
| Arrangement manager | `GridArrangementManager` in `ui/row_arrangement/` |
| Physical↔Logical transform | `ArrangementBridge` in `ui/sprite_editor/services/` |

---

*Last updated: January 30, 2026*
