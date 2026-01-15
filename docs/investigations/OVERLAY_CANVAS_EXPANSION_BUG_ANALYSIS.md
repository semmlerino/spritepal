# Bug Analysis: Overlay Application Canvas Expansion

## Overview
There is a bug in the tile arrangement dialog when applying an overlay: after applying it, the sprite editor canvas becomes larger than expected.

## End-to-End Pipeline Trace

1.  **Preparation:** `ROMWorkflowController` renders the current sprite to a temporary PNG and opens the `GridArrangementDialog`.
2.  **Dialog Setup:** The dialog slices the image into 8x8 tiles (Physical Tiles). The arrangement canvas is initialized with a default width (usually 16) and a **fixed height of 32 rows**.
3.  **Arrangement:** The user places tiles on the arrangement canvas. If a user places a tile at Row 20, Column 10 to align with a specific part of an overlay, the `GridArrangementManager` records this spatial position.
4.  **Application:** `ApplyOperation` samples the overlay at the canvas coordinates (e.g., `x=80, y=160` for Row 20, Col 10) and writes those pixels back to the **original physical tile data**.
5.  **Result Capture:** Upon clicking "OK", `GridArrangementDialog.get_arrangement_result` creates an `ArrangementBridge`. This bridge calculates `_logical_height` as `max(max_placed_row + 1, physical_height)`.
6.  **Editor Reload:** `ROMWorkflowController` receives the bridge and the modified pixels. It sets `self._current_arrangement = bridge` and calls `open_in_editor()`.
7.  **Transformation:** `open_in_editor` calls `bridge.physical_to_logical(image_array)`. This method creates a **new NumPy array** with the dimensions calculated in step 5. If a tile was placed at Row 31, the resulting editor canvas becomes 32 tiles (256 pixels) high.

## Root Causes

*   **Where Dimensions are Overridden:** 
    `ArrangementBridge._build_spatial_mapping` (in `ui/sprite_editor/services/arrangement_bridge.py`) defines the logical canvas size based on the maximum extents of the items placed on the arrangement grid. Specifically, `self._logical_height = max(max_r + 1, self._physical_height)` ensures that if a tile is placed at the bottom of the 32-row dialog canvas, the editor canvas expands to match.
*   **Authoritative Grid Treatment:**
    The system treats the **spatial coordinates** on the arrangement canvas as the authoritative "Logical View" for the editor. While this is intended for users who want to redefine their sprite's layout (e.g., reassembling a character), it is incorrect for users who only use the grid as a temporary alignment jig for overlay sampling.
*   **Identity vs. Placement Dependency:**
    The `ApplyOperation` correctly uses tile identity to patch pixels back into the ROM sequence. However, the `ArrangementBridge` (which controls the editor display) depends entirely on **grid placement**. It forces the editor canvas to be large enough to accommodate the "empty space" between the origin and the furthest placed tile.

## Data Structures & Coordinate Transforms

*   **`Physical Tiles`**: Mapping of `(row, col)` from the original ROM extraction. These are bit-identical and sequence-ordered.
*   **`Grid Mapping`**: Mapping of `(canvas_row, canvas_col) -> (Physical Tile Key)`. This stores the temporary spatial layout.
*   **`ArrangementBridge`**: The transformer that calculates the bounding box of `Grid Mapping` and creates the `logical_data` array for the editor.
*   **The Identity Gap**: The bridge preserves unarranged tiles at their original positions (identity) while moving arranged tiles to their grid positions. This "union" of two layouts is what forces the canvas to expand in both directions to accommodate all tiles.

## Current vs. Intended Behavior

| Aspect | Current (Actual) Behavior | Intended Behavior |
| :--- | :--- | :--- |
| **Canvas Size** | Expands to fit the bounding box of all placed grid items + original tiles. | Must remain at original physical dimensions. |
| **Grid Placement** | Defines the dimensions and layout of the editor workspace. | Should be "preview-only" for alignment/sampling purposes. |
| **Transformation** | `physical_to_logical` creates a large, padded array. | Should ideally be identity or compact-only after overlay. |
| **User Intent** | Conflates "alignment" with "layout redesign." | Alignment for sampling should not force a layout change. |

## Conclusion
The bug is a **leaky abstraction** where the temporary spatial coordinates used for alignment in the dialog "leak" into the permanent logical layout of the sprite editor workspace. Applying an overlay should ideally result in a compact or identity bridge unless the user explicitly requested to "Keep layout".
