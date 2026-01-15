# Overlay Application Workflow Mapping (January 2026)

This document provides a comprehensive mapping of the overlay-application workflow within the `GridArrangementDialog` and its integration with the `ROMWorkflowController`.

## 1. Tile Lifecycle and Data Flow

The lifecycle ensures that pixel data is modified in-place based on its original ROM identity, regardless of how tiles are visually rearranged.

### Extraction & Ingestion
*   **Source:** `ROMWorkflowController` holds the raw compressed or uncompressed tile data in `self.current_tile_data` (bytearray).
*   **Dimensions:** It tracks `self.current_width` and `self.current_height` to define the physical layout.
*   **Temp Export:** When "Arrange Tiles" is clicked, `ROMWorkflowController` renders the current data to a temporary PNG file (`temp.png`) using `SpriteRenderer.render_4bpp`.
*   **Layout Parameter:** `ROMWorkflowController` calculates `tiles_per_row = self.current_width // 8` and passes this to `GridArrangementDialog`.

### Arrangement Dialog (UI Workspace)
*   **Ingestion:** `GridArrangementDialog` initializes `GridImageProcessor`.
*   **Slicing:** `GridImageProcessor.process_sprite_sheet_as_grid` loads `temp.png` and slices it into 8x8 tiles.
*   **Identity:** Tiles are stored in `self.tiles` (dict), keyed by `TilePosition(row, col)`.
    *   **Invariant:** `TilePosition(row, col)` strictly represents the **physical location** in the source `temp.png` (and thus `current_tile_data`), *not* the visual location on the arrangement canvas.

### Pixel Modification (Overlay Application)
*   **Apply Logic:** When the overlay is applied, pixel data in `self.tiles` is overwritten.
*   **Identity Preservation:** The keys (`TilePosition`) are never changed during this process. Only the values (`PIL.Image`) are updated.

### Reinjection (Return to Editor)
*   **Result Package:** On dialog acceptance, `get_arrangement_result()` returns an `ArrangementResult` containing `modified_tiles` (a copy of `self.tiles`).
*   **Patching:** `ROMWorkflowController` receives `modified_tiles`.
*   **Reconstruction:** It calls `_update_tile_data_from_modified_tiles`:
    1.  Iterates through `modified_tiles`.
    2.  Calculates the linear byte offset: `(pos.row * tiles_per_row + pos.col) * 32`.
    3.  Encodes the modified PIL image back to 4bpp.
    4.  Patches `self.current_tile_data` at that offset.
*   **Editor Refresh:** The updated `current_tile_data` is re-rendered and loaded into `EditingController`.

---

## 2. Overlay Application Behavior

The overlay logic maps visual canvas coordinates back to source tile identities.

*   **Mapping Source:** `GridArrangementManager` maintains `_grid_mapping`, which maps `(canvas_row, canvas_col)` → `(ArrangementType.TILE, "source_row,source_col")`.
*   **Execution:** `GridArrangementDialog._apply_overlay` creates and executes an `ApplyOperation`.
*   **Sampling:**
    1.  `ApplyOperation` iterates through placed tiles in `_grid_mapping`.
    2.  For a tile at `(canvas_row, canvas_col)`, it calculates the pixel coordinates on the canvas: `x = canvas_col * 8`, `y = canvas_row * 8`.
    3.  It samples an 8x8 region from the `OverlayLayer` at `(x, y)`.
*   **Targeting:**
    1.  It parses the tile key `"source_row,source_col"` to get the original `TilePosition`.
    2.  It updates `self.tiles[TilePosition(source_row, source_col)]` with the sampled pixels.
*   **Data Write-Back:**
    *   The operation is destructive to the pixel data in `self.tiles`.
    *   An `ApplyOverlayCommand` is pushed to the `UndoRedoStack` to allow reversion.

---

## 3. Post-Overlay Expectations

*   **Tile Identities:** Unchanged. `TilePosition` keys remain constant throughout the dialog's life.
*   **ROM Ordering:** Unchanged. `ROMWorkflowController` patches data in-place at calculated offsets, preserving the original sequence of tiles.
*   **Pixel Modification:** Only the pixel data within the 4bpp structures is altered.
*   **Visual Consistency:**
    *   The `GridArrangementDialog` immediately refreshes to show the modified pixels on the canvas.
    *   The main pixel editor reflects these changes after the dialog closes.
*   **Arrangement Independence:** The *visual arrangement* (layout) is saved separately (in `ArrangementConfig`) and does not affect the *physical data* order in the ROM.

---

## 4. UI Consistency

*   **Canvas (`GridGraphicsView`):** Accurately reflects the current state of pixels in `self.tiles` via `_update_displays`.
*   **Apply Button:** Enabled/disabled based on overlay visibility and image presence (`_on_overlay_changed`).
*   **Feedback:**
    *   A status message confirms the number of modified tiles.
    *   The overlay is automatically hidden after application to reveal the result.
    *   Warnings are issued for tiles not covered by the overlay or palette mismatches.

---

## 5. Signal and Event Flow

| Origin | Signal | Target | Effect |
| :--- | :--- | :--- | :--- |
| **User** | Click "Arrange Tiles" | `ROMWorkflowController` | `show_arrangement_dialog`: Renders temp PNG, opens dialog. |
| **User** | Drag Overlay | `OverlayControls` / Mouse | `OverlayLayer` | Updates overlay position/scale/opacity. |
| `OverlayLayer` | `position_changed` (etc.) | `GridArrangementDialog` | `_on_overlay_changed`: Redraws canvas, updates "Apply" button. |
| **User** | Click "Apply Overlay" | `GridArrangementDialog` | `_apply_overlay`: Triggers `ApplyOperation`. |
| `GridArrangementDialog` | (Internal Logic) | `ApplyOperation` | `execute`: Modifies `self.tiles`. |
| `GridArrangementDialog` | (Internal Logic) | `UndoRedoStack` | `push(ApplyOverlayCommand)`. |
| `UndoRedoStack` | `stack_changed` | `GridArrangementDialog` | `_update_displays`: Refreshes canvas with new pixel data. |
| **User** | Click "OK" / Export | `GridArrangementDialog` | `accept`: Closes dialog. |
| `GridArrangementDialog` | (Return) | `ROMWorkflowController` | Receives `ArrangementResult`. |
| `ROMWorkflowController` | (Internal Logic) | `self.current_tile_data` | `_update_tile_data...`: Patches bytearray. |
| `ROMWorkflowController` | (Internal Logic) | `EditingController` | `open_in_editor`: Reloads modified image into editor. |

## 6. Discovered Risks & Ambiguities

*   **Tiles-per-row Synchronicity:** The patching logic in `ROMWorkflowController` relies on the `tiles_per_row` value remaining identical to the one used to initialize the `GridArrangementDialog`. If these drift, tile indexing will be corrupted.
*   **Apply Result Invalidation:** `GridArrangementDialog._on_arrangement_changed` clears `_apply_result` (unless `_is_applying_overlay`). This means any movement on the canvas after an "Apply" clears the internal record of modification, although the pixels themselves remain modified in `self.tiles`.
*   **Multiple Redraws:** `OverlayLayer.import_image` emits multiple signals, each triggering a full canvas redraw in `GridArrangementDialog`.
