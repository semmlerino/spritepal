# Arrange Tiles / Arrangement Grid System Mapping & Diagnosis

This document provides a technical map of the Arrange Tiles system in SpritePal, tracing its end-to-end workflows, state management, and signal flows.

## 1. System Overview & Core Components

The arrangement system enables a "Logical View" for editing sprites whose tiles are scattered or non-contiguous in the ROM. It bridges the gap between the physical layout (ROM storage) and a user-defined logical layout.

### Key Components
- **`GridArrangementDialog`**: The main UI orchestrator.
- **`GridArrangementManager`**: The logical state machine tracking tile placements and groups.
- **`ArrangementBridge`**: The data transformer that performs `physical_to_logical` and `logical_to_physical` image transformations.
- **`ApplyOperation`**: Logic for sampling pixels from an overlay and writing them to the tile data model.
- **`ArrangementConfig`**: The persistence model (v1.2) for saving/restoring layouts via sidecar JSON files.
- **`ROMWorkflowController`**: The entry point that manages the lifecycle of the arrangement within the editor.

---

## 2. Core Workflows: Step-by-Step Timeline

### Workflow A: Opening the Arrangement Dialog
1.  **Entry**: User clicks "Arrange Tiles" in the Sprite Editor.
2.  **Export**: `ROMWorkflowController` saves the current sprite image to a temporary PNG.
3.  **Init**: `GridArrangementDialog` is instantiated with the temp PNG and any existing `ArrangementConfig`.
4.  **Slice**: `GridImageProcessor` slices the image into a physical grid of `self.tiles` (PIL Images).
5.  **Restore**: If a config exists, `_restore_arrangement_state()` populates the `GridArrangementManager`.
6.  **Display**: The dialog shows the Source Grid (physical) and Arrangement Canvas (logical).

### Workflow B: Modifying the Arrangement Grid
1.  **Action**: User drags a tile from the Source Grid to a canvas slot `(r, c)`.
2.  **State Change**: `GridArrangementManager.set_item_at(r, c, TILE, "row,col")` is called.
3.  **Sync**: `_derive_order_from_grid()` re-scans the canvas to update the linear `_arrangement_order`.
4.  **Signal**: `arrangement_changed` is emitted.
5.  **Side Effect**: `_update_displays()` refreshes the QGraphicsScene.

### Workflow C: Applying Overlay Pixels
1.  **Action**: User clicks "Apply Overlay".
2.  **Validation**: `ApplyOperation.validate()` checks for uncovered tiles or unplaced tiles.
3.  **Execution**: `ApplyOperation.execute()`:
    - For each tile at canvas position `(r, c)`, samples a region from `OverlayLayer`.
    - If a palette is active, quantizes colors to palette indices.
    - Produces a `modified_tiles` dictionary mapping `TilePosition` -> `Image.Image`.
4.  **Undo/Redo**: `ApplyOverlayCommand` updates the dialog's `self.tiles` map.
5.  **UI Sync**: Overlay is auto-hidden to reveal the modified pixels.

### Workflow D: Applying Changes to the Editor
1.  **Accept**: User clicks "OK". `get_arrangement_result()` creates an `ArrangementResult`.
2.  **Bridge**: `ArrangementBridge` is built, calculating the `logical_size` (canvas bounds).
3.  **Persistence**: Metadata is saved to a sidecar `.arrangement.json` file.
4.  **Patching**: If overlay was applied, `ROMWorkflowController` encodes PIL images back to 4bpp and patches `current_tile_data` (bytearray).
5.  **Reload**: `open_in_editor()` is called:
    - Renders 4bpp to a physical image array.
    - Calls `ArrangementBridge.physical_to_logical(image_array)`.
    - Loads the resulting array into the editor.

---

## 3. Coordinate Spaces & Conversions

| Space | Unit | Reference Point | Usage |
| :--- | :--- | :--- | :--- |
| **Physical** | Tile Index | `(row, col)` | Identifies a tile in the original ROM layout. |
| **Canvas** | Grid Slot | `(r, c)` | User-defined logical position in the Arrangement Dialog. |
| **Logical** | Pixel | `(x, y)` | Position in the transformed editor canvas. |
| **Overlay** | Pixel | Floating | Position of the reference image relative to the canvas origin. |

**Key Conversion**: `(r, c) * tile_size` maps the canvas grid to the overlay sampling coordinate.

---

## 4. Signal Flow Map

| Emitter | Signal | Receiver | Side Effect |
| :--- | :--- | :--- | :--- |
| `GridArrangementManager` | `arrangement_changed` | `GridArrangementDialog` | Calls `_update_displays()`. |
| `OverlayLayer` | `visibility_changed` | `GridArrangementDialog` | Updates "Apply" button enabled state. |
| `GridGraphicsView` | `tiles_selected` | `GridArrangementDialog` | Updates action button enabled states. |
| `GridArrangementDialog` | `palette_mode_changed`| `GridPreviewGenerator` | Invalidates preview cache; forces re-colorization. |

---

## 5. State Variables & Ownership

| Variable | Type | Owner | Persistence |
| :--- | :--- | :--- | :--- |
| `_grid_mapping` | `dict` | `GridArrangementManager` | `arrangement_config.grid_mapping` (v1.2) |
| `self.tiles` | `dict[TilePosition, Image]` | `GridArrangementDialog` | Transient (applied to `current_tile_data` on accept) |
| `_current_arrangement` | `ArrangementBridge` | `ROMWorkflowController` | Reconstructed from config on load |
| `logical_width` | `int` | `ArrangementBridge` | `arrangement_config.logical_width` |

---

## 6. Diagnosis & Potential Inconsistencies

### 1. Canvas Expansion vs. Shrinking
- **Behavior**: `ArrangementBridge` ensures logical dimensions are `max(physical, arranged_bounds)`.
- **Diagnosis**: This prevents losing unarranged tiles (identity mapping), but prevents the user from "cropping" the canvas via arrangement. The canvas can only grow, never shrink below physical size.

### 2. Identity Mapping Ambiguity
- **Behavior**: Tiles NOT placed in the arrangement are kept at their original positions.
- **Diagnosis**: If a user arranges tiles into a 16x16 grid but leaves holes, the original tiles "behind" those holes remain visible in the editor. There is no "clear canvas" option for the logical view.

### 3. State Redundancy
- **Observation**: `GridArrangementManager` maintains `_arranged_tiles`, `_tile_set`, `_arrangement_order`, and `_grid_mapping`.
- **Risk**: `_derive_order_from_grid` must be called strictly after every `_grid_mapping` change to prevent desync between spatial and linear representations.

### 4. Overlay sampling vs. Tile identity
- **Observation**: `ApplyOperation` samples based on canvas position `(r, c)`.
- **Diagnosis**: If a tile is placed twice on the canvas (possible in some logic paths, though discouraged by UI), the second placement will overwrite the first in the `modified_tiles` dictionary because the key is the physical `TilePosition`.

### 5. Signal Frequency
- **Observation**: `arrangement_changed` is emitted for every tile added, even in bulk (e.g., `add_row`).
- **Impact**: Causes redundant UI refreshes during initialization or restoration.

### 6. Transparency Handling
- **Observation**: `ApplyOperation._quantize_to_palette` treats alpha < 128 as index 0.
- **Diagnosis**: If the overlay has transparent holes, these become index 0 (usually the background/transparent color in SNES). This effectively "erases" tile data where the overlay is transparent.
