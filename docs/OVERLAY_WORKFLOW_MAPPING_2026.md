# Overlay Application Workflow Mapping (January 2026)

This report maps the end-to-end workflow for overlay application within the tile arrangement dialog, tracing how data moves from the ROM, through the temporary visual workspace, and back into the ROM.

---

### 1. Tile Lifecycle and Data Flow

The lifecycle of a tile is divided into **Physical State** (how it exists in the ROM/sprite sheet) and **Logical State** (how it is presented to the user).

*   **Origin**: Tiles are extracted from the ROM at a specific hex offset. If the sprite is HAL-compressed, it is decompressed into a contiguous block of 4bpp tile data.
*   **Physical Representation**: 
    *   In `ROMWorkflowController`, tiles are stored as raw bytes in `self.current_tile_data`.
    *   In `GridArrangementDialog`, these bytes are rendered into a temporary PNG and then sliced by `GridImageProcessor` into `self.tiles`, a dictionary mapping `TilePosition(physical_row, physical_col)` to a PIL `Image`.
    *   **Crucial Invariant**: The `TilePosition` key in `self.tiles` always refers to the tile's original coordinates in the physical sprite sheet.
*   **Logical Representation**:
    *   The **Arrangement Canvas** uses `GridArrangementManager` to store a `grid_mapping`. This maps `(canvas_row, canvas_col)` to the physical identity `(ArrangementType.TILE, "physical_row,physical_col")`.
    *   The **Pixel Editor** (after dialog acceptance) uses `ArrangementBridge` to transform the physical bytes into a "Logical" image array where tiles are moved to their canvas positions for contiguous editing.
*   **Modification**: Pixel data is modified during the "Apply Overlay" step or via the Pixel Editor. Tile identities (their source row/col) and their linear order in the ROM data remain strictly unchanged.
*   **Reinjection**: Before saving, `ArrangementBridge.logical_to_physical` reverses any visual rearrangement, restoring the pixels to their physical offsets in the byte buffer before `ROMInjector` compresses and writes them back.

### 2. Overlay Application Behavior

The overlay process maps external image pixels onto the physical tile data using the canvas as a spatial reference.

*   **Mapping**: `ApplyOperation` iterates through the `grid_mapping`. For every `(canvas_row, canvas_col)` that contains a tile:
    1.  It calculates the pixel bounding box of that tile on the **Canvas**.
    2.  It samples that region from the **Overlay Image** (considering the overlay's scale and position on the canvas).
    3.  It quantizes the sampled pixels to the sprite's palette.
    4.  It writes the resulting pixels into `modified_tiles[TilePosition(physical_row, physical_col)]`.
*   **Independence**: The logic depends on the *canvas position* to know *what* to sample, but it writes the data back to the *tile identity*. If a tile is not placed on the canvas, it is not modified (a warning is issued).
*   **Data Write-back**: `ApplyOverlayCommand` updates the dialog's `self.tiles` dictionary. Upon clicking OK, `ROMWorkflowController` encodes these PIL images back to 4bpp bytes and patches them into the physical `self.current_tile_data` buffer.

### 3. Post-Overlay Expectations

After applying an overlay and accepting the dialog, the system enforces the following state:

*   **Identity**: `TilePosition(0, 0)` still refers to the first tile in the ROM buffer, even if it was moved to the bottom-right of the canvas.
*   **Ordering**: The linear sequence of tiles in `self.current_tile_data` is preserved. Only the internal pixel content of those 32-byte blocks is changed.
*   **Visual Persistence**: If "Keep layout" is checked, the `ArrangementBridge` remains active in the `EditingController`. The user sees the "Arranged" view in the editor, but the underlying data being edited is a physical buffer.
*   **In-Game Layout**: Since only pixel data was modified and the ROM injection offset/order is unchanged, the in-game layout (OAM/Tilemap) remains identical; only the visuals of the tiles change.

### 4. UI Consistency

*   **Identity Reflection**: The "Sprite Grid" (source) shows tiles in their physical order. Tiles that are "placed" on the canvas are dimmed in the source grid to indicate they are "in use."
*   **State Accuracy**: 
    *   The `GridArrangementDialog` accurately reflects the state of `self.tiles`. If an overlay is applied, the canvas items are updated to show the new pixels.
    *   **Mismatch Risk**: If the `tiles_per_row` (Target Sheet Width) is changed *after* an arrangement is built but *before* an overlay is applied, the physical indexing of `self.tiles` could theoretically drift if not handled carefully (though currently, the dialog re-processes the sheet on width change).
*   **Modified State**: The `ROMWorkflowController` tracks `_current_arrangement`. If active, the Editor Title or Status Bar indicates "Logical View" or "Arranged."

### 5. Signal and Event Flow

| Event / Signal | Emitter | Listener | Side Effect |
| :--- | :--- | :--- | :--- |
| **`clicked`** | `apply_overlay_btn` | `GridArrangementDialog` | Triggers `_apply_overlay()` logic. |
| **`image_changed`** | `OverlayLayer` | `GridArrangementDialog` | Updates "Apply" button enabled state; triggers canvas redraw. |
| **`execute()`** | `ApplyOverlayCommand` | `UndoRedoStack` | Updates `dialog.tiles` and calls `_update_displays()`. |
| **`accepted`** | `GridArrangementDialog` | `ROMWorkflowController` | Triggers result processing. |
| **`palette_mode_changed`** | `PaletteColorizer` | `GridPreviewGenerator` | Invalidates preview cache; forces re-colorization of canvas items. |
| **`arrangement_changed`** | `GridArrangementManager`| `GridArrangementDialog` | Clears `_apply_result` (overlay data) to prevent stale data application. |

**Flagged Risks & Inconsistencies:**
*   **Implicit Dependency**: `ROMWorkflowController._update_tile_data_from_modified_tiles` relies on a `tiles_per_row` value passed back from the dialog. If this value does not perfectly match the one used to slice the original sheet, the physical patching will target the wrong byte offsets.
*   **Redundant Redraws**: `OverlayLayer` property changes (scale, pos, visibility) each trigger a full `scene.clear()` and redraw of every tile on the canvas, which may cause flicker or performance lag with large sprites.
*   **Silent State**: `self.tiles` is modified in-place by the Undo/Redo commands. If the dialog were to crash or be closed without `accept()`, the `ROMWorkflowController`'s copy remains safe, but the `PaletteColorizer` cache must be manually cleared to ensure the next open shows fresh data.
*   **Identity Confusion**: If the user adds the same physical tile to the canvas multiple times (duplicates), `ApplyOperation` will sample multiple regions but only the *last* one sampled for that identity will persist in `modified_tiles`. The UI does not currently warn that duplicate tiles will "compete" for the same ROM data.
