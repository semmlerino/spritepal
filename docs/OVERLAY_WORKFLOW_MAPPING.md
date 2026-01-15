# Overlay-Application Workflow Mapping (SpritePal)

This diagnostic mapping describes the complete overlay-application workflow within SpritePal's tile arrangement system, tracing data from ROM extraction through temporary visual rearrangement to final reinjection.

## 1. Tile Identity Flow
Tile identity is maintained through a stable coordinate-based system:
*   **Physical Identity:** Each tile is uniquely identified by a `TilePosition(row, col)`, representing its coordinates in the original extraction grid (the "Physical Layout").
*   **Assignment:** These IDs are assigned once during extraction in `GridImageProcessor.process_sprite_sheet_as_grid` and remain constant regardless of visual movement.
*   **Data Structure:** Pixel data is stored in `GridArrangementDialog.tiles` as a `dict[TilePosition, Image.Image]`.
*   **Risk:** The system assumes a fixed extraction grid (e.g., 16 tiles per row). If `tiles_per_row` is changed between extraction and arrangement, the `TilePosition` index mapping will break, leading to incorrect tile patching.

## 2. Arrangement Dialog Behavior
The arrangement dialog serves as a temporary visual redirection layer:
*   **Backing Model:** `GridArrangementManager` tracks state via `grid_mapping: dict[tuple[int, int], tuple[ArrangementType, str]]`, which maps **Canvas Coordinates** `(r, c)` to **Arrangement Items** (e.g., `(TILE, "row,col")`).
*   **Separation of Concerns:** The `arrangement_scene` (UI) and `arrangement_manager` (Logic) are synced. Movement on the canvas updates the `grid_mapping` but does **not** modify the underlying `tiles` pixel data dictionary.
*   **Persistence:** The mapping is persisted in sidecar `.spritepal_arrangement.json` files via `ArrangementConfig`, ensuring visual layouts survive across sessions.

## 3. Overlay Application Workflow
The overlay process is a deterministic pixel-sampling operation:
*   **Targeting:** `ApplyOperation` determines which pixels to sample by iterating through the `grid_mapping`.
*   **Spatial Dependency:** Sampling logic uses the **Canvas Position** `(r, c)` to determine the `(x, y)` coordinates on the overlay image.
*   **Identity Mapping:** It then looks up the `TilePosition` associated with that canvas slot in the `grid_mapping` and writes the sampled pixels to that specific physical identity.
*   **Modification:** The operation produces an `ApplyResult` with `modified_tiles`. These are applied to the dialog's `self.tiles` via `ApplyOverlayCommand` (supporting Undo).
*   **Consistency:** The UI suggests that "what you see is what you get"—if a tile is under the "M" of a "MAX" overlay on the canvas, it receives those "M" pixels, regardless of where that tile originated in the ROM.

## 4. Reinjection into ROM
Modified tiles are reconciled with the original ROM structure:
*   **Patching Bytes:** Upon dialog acceptance, `ROMWorkflowController._update_tile_data_from_modified_tiles` encodes the modified PIL images back into 4bpp bytes and patches `self.current_tile_data` (the raw buffer) at the physical byte-offset calculated from the `TilePosition`.
*   **Bidirectional Bridge:** `ArrangementBridge` manages the final transformation during ROM save:
    *   `logical_to_physical`: Reverses the visual arrangement, restoring tiles to their original extraction order.
    *   The `EditingController` provides the logical image; the bridge flattens it back to the physical structure required for `ROMInjector`.
*   **Invariant:** Only pixel data is modified. Tile count, compression type, and ROM offsets remain identical to the original extraction.

## 5. Signal and Event Flow

| Signal | Emitted By | Received By | State Mutated / Effect |
| :--- | :--- | :--- | :--- |
| `arrangement_changed` | `GridArrangementManager` | `GridArrangementDialog` | Triggers `_update_displays`; clears `_apply_result`. |
| `visibility_changed` | `OverlayLayer` | `GridArrangementDialog` | Updates `apply_overlay_btn` enabled state; redraws canvas. |
| `scale_changed` | `OverlayLayer` | `GridArrangementDialog` | Triggers canvas redraw; affects `ApplyOperation` sampling. |
| `applyRequested` | `OverlayPanel` | `ROMWorkflowController` | Triggers `_on_apply_overlay` in main workspace (different from dialog). |
| `arrangeClicked` | `ROMWorkflowPage` | `ROMWorkflowController` | Launches `GridArrangementDialog`. |
| `palette_mode_changed`| `PaletteColorizer` | `GridArrangementDialog` | Updates `palette_toggle_btn`; clears render cache. |

## 6. Critical Observations & Risks
*   **Canvas Position Leakage:** `ApplyOperation` is the only point where canvas coordinates `(r, c)` influence logical pixel data. If a user overlaps two tiles on the canvas, the `grid_mapping` will only contain one at that position, and the other will remain unmodified (triggering an `UNPLACED` or `UNCOVERED` warning).
*   **Stale Result Guard:** `_on_arrangement_changed` proactively clears `_apply_result`. This prevents the controller from attempting to retrieve "modified tiles" that were sampled for a layout that no longer exists.
*   **Redundancy:** `_update_arrangement_canvas` clears the entire `QGraphicsScene` and redraws every item whenever any overlay property (like 1px movement) changes. This is a potential performance bottleneck for large sprite sheets.
*   **Implicit Order:** `ROMWorkflowController` relies on `tiles_per_row` being passed correctly back to `_update_tile_data_from_modified_tiles`. If the dialog was initialized with a different width than the controller's current model, the patching offset will be incorrect.
