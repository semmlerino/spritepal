# Audit Report: Overlay-Application Workflow Mapping (January 15, 2026)

## 1. Tile Lifecycle & Identity Map
- **Origin**: Tiles are extracted from ROM as a linear byte stream, then sliced into 8x8 blocks.
- **Identity (Authoritative)**: `TilePosition(row, col)` represents the tile's coordinates in the *original* extracted grid. This is the immutable "ID" used for ROM re-injection.
- **Internal Representation**:
    - `GridArrangementDialog.tiles`: `dict[TilePosition, Image.Image]` stores the current pixel data.
    - `GridArrangementManager._grid_mapping`: `(canvas_row, canvas_col) -> (Type, Key)` stores visual placement.
- **Transformation**: The "logical" layout (editing view) is derived from `_grid_mapping`. `ArrangementBridge` uses this to provide a `physical_to_logical` pixel transformation for the main editor.
- **Persistence**: `ArrangementConfig` (sidecar JSON) saves the `grid_mapping`, enabling the reconstruction of the bridge and dialog state across sessions.

## 2. Arrangement Dialog Behavior
- **Authoritative Data**: `grid_mapping` is the source of truth for the canvas. The linear `_arrangement_order` is a derived property updated via `_derive_order_from_grid()` whenever the mapping changes.
- **Selection & Targeting**: Overlay application targets all tiles currently present in the `grid_mapping`. However, it only processes items explicitly of type `ArrangementType.TILE`.

## 3. Overlay Application Path
1.  **Sampling**: `ApplyOperation` calculates canvas coordinates `(x, y)` for a tile at `(canvas_row, canvas_col)`.
2.  **Resolution**: It calls `OverlayLayer.sample_region(x, y, ...)` which maps these to `OverlayLayer`'s local space (accounting for `x, y, scale`).
3.  **Identity Resolution**: The sampled pixels are written into `GridArrangementDialog.tiles[TilePosition(original_row, original_col)]`.
4.  **Patching**: Upon dialog acceptance, `ROMWorkflowController` iterates through the `modified_tiles` and patches the original ROM byte array using the `TilePosition` to calculate the correct linear offset.

## 4. Signal / Event Flow Audit
| Signal | Source | Purpose | Risk/Note |
| :--- | :--- | :--- | :--- |
| `arrangement_changed` | `GridArrangementManager` | Triggers UI refresh & clears `apply_result`. | Fires frequently during drags. |
| `image_changed` | `OverlayLayer` | UI update on import. | Triggers redundant `_update_arrangement_canvas`. |
| `position_changed` | `OverlayLayer` | UI update on nudge/drag. | Redundant when paired with `scale_changed`. |
| `scale_changed` | `OverlayLayer` | UI update on scale. | Triggers `position_changed` (fix center logic). |
| `tiles_dropped` | `GridGraphicsView` | Initiates move/place commands. | Reliable. |

## 5. Identified Risks & Inconsistencies
- **[Critical] Multi-Tile Item Exclusion**: `ApplyOperation.execute()` strictly checks for `ArrangementType.TILE`. Tiles placed on the canvas as part of a `GROUP`, `ROW`, or `COLUMN` are silently ignored during overlay application. This is a significant functional gap.
- **[Redundancy] Multiple Redraws**: `OverlayLayer.import_image` emits three signals (`image_changed`, `scale_changed`, `position_changed`), each triggering a full canvas redraw in `GridArrangementDialog`.
- **[Fragility] Apply State Guard**: `_apply_overlay` uses a boolean guard `_is_applying_overlay` to prevent the clearing of the `apply_result` when the overlay is auto-hidden.
- **[Dependency] Tiles-per-row Synchronicity**: The patching logic in `ROMWorkflowController` relies on the `tiles_per_row` value remaining identical to the one used to initialize the `GridArrangementDialog`.

## 6. Core Invariant Validation
- **Tile Identities**: **Validated**. Tile IDs remain tied to original ROM positions.
- **ROM Ordering**: **Validated**. Re-injection uses physical IDs, ignoring arrangement order.
- **Placement Influence**: **Risk Identified**. While placement doesn't affect *where* tiles are written in ROM, it currently affects *if* they are modified (due to the `GROUP/ROW` exclusion) and *what* pixels they receive (correctly derived from canvas position).
