# Overlay Application Logic Mapping & Diagnostics

**Date:** January 15, 2026
**Project:** SpritePal
**Status:** Mapping-only (No fixes implemented)

## 1. Minimal Reproduction & Variants

**Reproduction Steps:**
1. Open a sprite in the **Sprite Editor**.
2. Launch the **Arrangement Dialog** (`GridArrangementDialog`).
3. Import an image via the **Overlay Reference** panel.
4. Position and scale the overlay over tiles placed on the **Arrangement Grid**.
5. Click **Apply Overlay to Arranged Tiles**.
6. Accept the dialog to return to the editor.

**Variants:**
*   **Sprite Size:** Affects the number of tiles and the initial auto-scaling of the overlay.
*   **Overlay Scale:** Changes the sampling density (uses `Image.Resampling.BOX`).
*   **Grid Mapping:** The visual position of tiles on the canvas determines which part of the overlay they "capture".

## 2. End-to-End Flow & Call Sequence

When the user clicks "Apply", the following sequence occurs:

1.  **`GridArrangementDialog._apply_overlay()`**: Orchestrates the process.
    *   **`ApplyOperation.validate()`**: Checks if all placed tiles are covered by the overlay.
    *   **`ApplyOperation.execute(force=True)`**: Performs the actual sampling.
2.  **`OverlayLayer.sample_region(tile_x, tile_y, ...)`**: Calculates the intersection of the tile and overlay in **Canvas Space** (pixel coordinates).
    *   It crops the relevant part from the overlay source, resizes it to match the tile dimensions (if scaled), and pastes it into a transparent RGBA tile.
3.  **`ApplyOperation._quantize_to_palette()`**: Converts the RGBA sampled tile to indexed color (SNES 4bpp compatible).
    *   Transparent pixels (Alpha < 128) → Index 0.
    *   Opaque pixels → Closest RGB match in the active palette.
4.  **`UndoRedoStack.push(ApplyOverlayCommand)`**: destructively updates `dialog.tiles` (the internal PIL image cache).
5.  **`GridArrangementDialog.get_arrangement_result()`**: Packages the modified tiles into an `ArrangementResult` upon dialog acceptance.
6.  **`ROMWorkflowController._update_tile_data_from_modified_tiles()`**: Encodes the modified PIL images back into 4bpp SNES bytes and patches `current_tile_data`.
7.  **`ROMWorkflowController.open_in_editor()`**: Reloads the editor workspace with the newly patched data.

## 3. Coordinate Spaces & Data Structures

| Space | Definition | Component |
| :--- | :--- | :--- |
| **Source Image** | Pixels of the extracted sprite sheet. | `GridImageProcessor` |
| **Tile Index** | Logical `(row, col)` position in the source grid. | `TilePosition` |
| **Canvas Space** | Pixel coordinates on the arrangement grid. | `GridGraphicsView` |
| **Overlay Source** | Raw pixels of the imported overlay file. | `OverlayLayer._image` |
| **Overlay Visual** | Scaled and positioned overlay on the canvas. | `OverlayGraphicsItem` |

**Key Data Structures:**
*   `grid_mapping`: `dict[(canvas_r, canvas_c), (type, key)]` — Identifies what is at each grid cell.
*   `self.tiles`: `dict[TilePosition, Image.Image]` — The authoritative pixel data within the dialog.
*   `current_tile_data`: `bytes` — The authoritative pixel data in the main controller.

## 4. Signal Flow Map

| Emitter | Signal | Receiver | Side Effect |
| :--- | :--- | :--- | :--- |
| `OverlayControls` | `valueChanged` | `OverlayLayer` | Updates `x`, `y`, `scale`, or `opacity`. |
| `OverlayLayer` | `position_changed` | `OverlayGraphicsItem` | Moves the visual overlay in the scene. |
| `OverlayLayer` | `image_changed` | `GridArrangementDialog` | Updates "Apply" button enabled state. |
| `apply_overlay_btn` | `clicked` | `GridArrangementDialog` | Triggers `_apply_overlay`. |
| `UndoRedoStack` | `command.execute()` | `GridArrangementDialog` | Calls `_update_displays` to refresh the scene. |

## 5. State Variable Transitions

| Variable | Location | Before Apply | After Apply | Method Responsible |
| :--- | :--- | :--- | :--- | :--- |
| `tiles[pos]` | `GridArrangementDialog` | Original PIL Image | Sampled PIL Image | `ApplyOverlayCommand.execute` |
| `visible` | `OverlayLayer` | `True` | `False` | `GridArrangementDialog._apply_overlay` |
| `_apply_result`| `GridArrangementDialog` | `None` | `ApplyResult` | `GridArrangementDialog._apply_overlay` |
| `tile_data` | `ROMWorkflowController`| Original Bytes | Patched Bytes | `_update_tile_data_from_modified_tiles` |

## 6. Identified Inconsistencies & Fragility

*   **Identity Coupling (`Fragile`):** `ApplyOperation` identifies tiles by their `TilePosition` in the source grid. If the user changes the "Tiles per Row" setting, these identities shift, potentially breaking existing arrangements or overlay applications.
*   **Coordinate Precision (`Ambiguous`):** `OverlayLayer` uses `float` for position/scale, but `ApplyOperation` calculates `tile_x/y` as integer multiples of tile size. Floating point epsilon is used in `covers_tile` and `sample_region`, but rounding errors near tile boundaries may cause unexpected "uncovered" warnings.
*   **Hardcoded Quantization (`Inconsistent`):** `ApplyOperation._quantize_to_palette` multiplies indices by 16 (`best_idx * 16`). This is hardcoded for SNES 4bpp and may not be appropriate for other bit depths if supported in the future.
*   **State Desynchronization (`Inconsistent`):** The modified pixels only exist as `PIL.Image` objects in the dialog until the user clicks "Export" or "OK". If the dialog crashes or is cancelled, these pixels are lost, even if "Apply" was clicked.
*   **Re-entrancy Guard (`Fragile`):** `_is_applying_overlay` is a manual flag used to prevent the UI from clearing the application result when the overlay is auto-hidden. This indicates a tight coupling between UI visibility and data validity.
*   **Scale Center Logic (`Fragile`):** `OverlayLayer.set_scale` modifies `_x` and `_y` to maintain the visual center. If `set_position` and `set_scale` are called in the wrong order during state restoration, the overlay will drift.
