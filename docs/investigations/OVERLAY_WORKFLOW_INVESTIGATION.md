# Overlay Application Workflow Investigation

**Date:** January 15, 2026  
**Status:** Completed Investigation  

## 1. Trace: Complete Overlay Workflow

1.  **Trigger**: User clicks "Apply Overlay to Arranged Tiles" in the `GridArrangementDialog`.
2.  **Validation**: `ApplyOperation.validate()` checks for:
    *   **Uncovered Tiles**: Tiles on the canvas not fully overlapping with the overlay.
    *   **Unplaced Tiles**: Source tiles not present on the canvas.
    *   **Palette Mismatch**: Pixels that don't align with the current 16-color SNES palette.
3.  **Sampling**: `ApplyOperation.execute()` iterates through the `grid_mapping` (canvas positions).
    *   It calls `OverlayLayer.sample_region(tile_x, tile_y, ...)` for each position.
    *   **Crucial Behavior**: If a tile is only partially covered, `sample_region` returns a tile-sized image where uncovered areas are **fully transparent**.
4.  **Quantization**: `ApplyOperation._quantize_to_palette()` converts RGBA samples to 4bpp indices.
    *   **Crucial Behavior**: Transparent pixels (alpha < 128) are converted to **palette index 0**.
    *   Resulting indexed data **replaces** the tile content in the dialog's `self.tiles` dictionary.
5.  **Data Flow to Editor**:
    *   `ArrangementResult` packages the `modified_tiles` and the `ArrangementBridge`.
    *   `ROMWorkflowController` patches the modified pixels into the `current_tile_data` byte array.
    *   `open_in_editor()` reloads the image, applying the `ArrangementBridge` transformation.

## 2. Component Responsibilities

| Component | Responsibility |
| :--- | :--- |
| **GridArrangementDialog** | UI orchestration, status reporting, and undo/redo of "Apply" commands. |
| **OverlayLayer** | Maintains overlay image, pos, scale. Performs pixel-perfect sampling from Canvas space. |
| **ApplyOperation** | Logic for sampling, quantization, and tile dictionary replacement. |
| **ArrangementBridge** | Bidirectional mapping between physical (ROM) and logical (arranged) layouts. |
| **ROMWorkflowController** | Persists modifications to raw bytes and manages editor state. |

## 3. Fragile Areas & Implicit Behavior

*   **Destructive Partial Application**: Tiles not perfectly aligned with the overlay will have their edges "wiped" (set to index 0). There is no "composite with original" logic; it is a strict replacement.
*   **Identity Mapping Conflict**: The `ArrangementBridge` enforces that the logical canvas must be at least as large as the physical ROM layout (`self._physical_width`). This prevents shrinking the logical view to a compact 2x2 arrangement if the original sprite was 16x1.
*   **Shared Source Tile Collision**: If a user places the same source tile (e.g., "0,0") at two different canvas locations (e.g., (0,0) and (5,5)), `ApplyOperation` will sample both, but the second sample will overwrite the first in the `modified_tiles` dictionary.
*   **Static Physical Capacity**: `ROMWorkflowController` expands the physical canvas to fit decompressed data but rarely shrinks it, leading to "sticky" large canvas sizes after an arrangement is cleared.

## 4. Hypotheses for Unexpected Results

*   **Hypothesis 1 (Unexpected Canvas Size)**: The logical width in the editor often matches the ROM width rather than the arrangement width because the bridge enforces physical minimums.
*   **Hypothesis 2 (Missing Content)**: Tiles appear missing or blank if they were sampled from a transparent part of the overlay or if `ApplyOperation` skipped them due to a lack of coverage.
*   **Hypothesis 3 (Layout Desync)**: If `logical_width` in the dialog (set by `width_spin`) differs from the editor's expectation, `_update_tile_data_from_modified_tiles` might patch the wrong ROM offsets.

## 5. Candidate Fixes & Refactors

1.  **Composite Mode**: Update `ApplyOperation` to only replace pixels where the overlay alpha is above a threshold, preserving original pixels elsewhere.
2.  **Arrangement-Only View**: Allow the `ArrangementBridge` to ignore unarranged tiles and shrink the logical canvas to the arrangement's bounding box.
3.  **Unique Tile Support**: If multiple canvas positions use the same source tile, provide a warning or a strategy (e.g., "average", "first", "last").
4.  **Auto-Shrink Logic**: Update `ROMWorkflowController` to recalculate and shrink physical dimensions when an arrangement is cleared or a new ROM is loaded.
