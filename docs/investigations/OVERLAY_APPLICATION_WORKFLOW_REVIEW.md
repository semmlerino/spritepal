**1. Tile lifecycle and data flow**

- Source → dialog: `ROMWorkflowController.open_tile_arrangement_dialog` renders `current_tile_data` into a temp PNG via `SpriteRenderer.render_4bpp`, then `GridArrangementDialog` loads it (`ui/sprite_editor/controllers/rom_workflow_controller.py:1166`, `ui/grid_arrangement_dialog.py:35`, `ui/row_arrangement/grid_image_processor.py:21`).
- Tile identity: `GridImageProcessor.extract_tiles_as_grid` slices the PNG into `tiles: dict[TilePosition, Image]` keyed by physical `(row, col)` in the original grid (`ui/row_arrangement/grid_image_processor.py:70`). These positions are the canonical identity for the tile pixels.
- Arrangement workspace: `GridArrangementManager` stores **canvas positions** in `_grid_mapping[(canvas_row, canvas_col)] = (ArrangementType, key)` where `key` encodes the physical tile `"row,col"` (`ui/row_arrangement/grid_arrangement_manager.py:70`). Canvas moves replace entries in `_grid_mapping`; `arrangement_order` is derived row-major from the mapping.
- Overlay modifies pixels, not identity: `ApplyOperation.execute` iterates `_grid_mapping` entries and, for `TILE` entries only, maps overlay samples back onto `tiles[TilePosition(row, col)]` (`core/apply_operation.py:140`). Tile identity stays as the original `(row, col)` key.
- Back to ROM data: `GridArrangementDialog.get_arrangement_result` returns `modified_tiles` (currently the full `tiles` dict if any apply happened) to `ROMWorkflowController._update_tile_data_from_modified_tiles`, which patches bytes by `tile_idx = row * tiles_per_row + col` (`ui/grid_arrangement_dialog.py:1629`, `ui/sprite_editor/controllers/rom_workflow_controller.py:1246`).
- Editor/injection: `open_in_editor` applies `ArrangementBridge.physical_to_logical` for display, and `save_to_rom` applies `logical_to_physical` before injection, preserving physical ordering for ROM writes (`ui/sprite_editor/controllers/rom_workflow_controller.py:892`, `ui/sprite_editor/controllers/rom_workflow_controller.py:1766`, `ui/sprite_editor/services/arrangement_bridge.py:239`).

Potential risks / inconsistencies:
- If the user applies overlay and then changes arrangement, `_on_arrangement_changed` clears `_apply_result`, and `get_arrangement_result` will not pass any `modified_tiles`, even though the `tiles` dict retains the changes (`ui/grid_arrangement_dialog.py:994`, `ui/grid_arrangement_dialog.py:1629`). This can silently drop overlay pixel changes on close.
- `GridArrangementManager` allows placing the same tile key multiple times on the canvas. `ApplyOperation` will overwrite `modified_tiles[tile_pos]` for duplicate keys based on `_grid_mapping` insertion order, so which canvas position “wins” is ambiguous (`core/apply_operation.py:140`, `ui/row_arrangement/grid_arrangement_manager.py:86`).
- If an arrangement is restored from a config with empty `grid_mapping` (older formats), the dialog keeps `arrangement_order` but has no canvas mapping. Overlay application sees zero tiles and does nothing; no UI error is shown (`ui/grid_arrangement_dialog.py:1374`, `core/apply_operation.py:110`).

---

**2. Overlay application behavior**

- Overlay layer state is owned by `OverlayLayer` (image, x/y, scale, opacity, visibility) (`ui/row_arrangement/overlay_layer.py:14`).
- UI inputs: `OverlayControls` manipulate `OverlayLayer` and update from its signals; drag moves are handled by `OverlayGraphicsItem.itemChange → OverlayLayer.set_position` (`ui/row_arrangement/overlay_controls.py:63`, `ui/row_arrangement/overlay_item.py:45`).
- Apply flow: `Apply Overlay to Arranged Tiles` → `GridArrangementDialog._apply_overlay` → `ApplyOperation.validate` (coverage + unplaced warnings) → `ApplyOperation.execute` → `ApplyOverlayCommand` mutates `tiles` (`ui/grid_arrangement_dialog.py:849`, `core/apply_operation.py:98`, `ui/row_arrangement/undo_redo.py:614`).
- Mapping logic: Overlay sampling uses **canvas coordinates** (`tile_x = canvas_col * tile_width`) and ignores the physical tile position for sampling (`core/apply_operation.py:116`, `ui/row_arrangement/overlay_layer.py:282`).
- Affected tiles: only `ArrangementType.TILE` entries in `_grid_mapping` are processed; rows/columns/groups are ignored by overlay application (`core/apply_operation.py:140`).
- Data written back: `modified_tiles[TilePosition] = sampled_region`, then `ApplyOverlayCommand` updates `tiles`, and the dialog returns `modified_tiles` (currently the full tiles dict) for ROM patching (`core/apply_operation.py:162`, `ui/row_arrangement/undo_redo.py:614`, `ui/grid_arrangement_dialog.py:1629`).

Potential risks / inconsistencies:
- `ArrangementType.ROW/COLUMN/GROUP` entries are ignored by overlay apply; if such entries exist in `_grid_mapping`, they are silently skipped, so tiles represented by those logical groupings may not get overlay pixels (`core/apply_operation.py:140`).
- Overlay position is stored as floats, but UI spinboxes round to ints; fractional positions can be lost in UI state updates, potentially changing sampling if the user re-enters values (`ui/row_arrangement/overlay_layer.py:46`, `ui/row_arrangement/overlay_controls.py:209`).

---

**3. Post-overlay expectations**

- Tile identities unchanged: overlay modifies `tiles[TilePosition]` keyed by the original `(row, col)`; the keys are preserved through `_update_tile_data_from_modified_tiles` (byte offsets use row/col) (`core/apply_operation.py:140`, `ui/sprite_editor/controllers/rom_workflow_controller.py:1246`).
- ROM ordering unchanged: If arrangement is kept, the editor shows a logical layout, but `save_to_rom` applies `logical_to_physical` before injection, restoring physical layout (`ui/sprite_editor/controllers/rom_workflow_controller.py:1766`, `ui/sprite_editor/services/arrangement_bridge.py:306`).
- Pixel editor reflects final data: `open_in_editor` loads `current_tile_data` (post-apply patch) and then applies the arrangement transform if present (`ui/sprite_editor/controllers/rom_workflow_controller.py:892`).
- In-game layout unchanged: injection uses physical tile data order; arrangement only affects editor view and overlay targeting.

Potential risks / inconsistencies:
- If overlay is applied and then the arrangement changes (even just moving tiles), `_apply_result` is cleared, and the patched tile bytes are not propagated back to `current_tile_data` on close, despite tiles being visually changed in the dialog (`ui/grid_arrangement_dialog.py:994`, `ui/grid_arrangement_dialog.py:1629`).
- Source grid preview uses `original_image` (never updated after overlay), so the left panel can display pre-overlay pixels while the right canvas shows modified tiles (`ui/grid_arrangement_dialog.py:1045`, `ui/grid_arrangement_dialog.py:1249`). This is a UI vs data mismatch, not a data loss.

---

**4. UI consistency**

- Overlay application UI:
  - Apply button enabled only if overlay is visible + loaded (`ui/grid_arrangement_dialog.py:256`, `ui/grid_arrangement_dialog.py:1010`).
  - `GridArrangementDialog._apply_overlay` contains a “hidden overlay” confirmation, but the button is disabled when hidden, so that branch is effectively unreachable from UI (`ui/grid_arrangement_dialog.py:849`, `ui/grid_arrangement_dialog.py:1010`).
  - Overlay auto-hides after apply and disables the button until the user re-shows the overlay (`ui/grid_arrangement_dialog.py:939`).

- Arrangement width:
  - `Target Sheet Width` drives canvas width and `ArrangementBridge.logical_width` (`ui/grid_arrangement_dialog.py:530`, `ui/grid_arrangement_dialog.py:1637`).
  - `ArrangementBridge` clamps logical width to at least physical width, so a small width in UI may not be honored in the editor (`ui/sprite_editor/services/arrangement_bridge.py:97`).

- Overlay position feedback:
  - Dragging the overlay updates `OverlayLayer` with float positions, but position spinboxes display ints, which can hide sub-pixel adjustments (`ui/row_arrangement/overlay_item.py:45`, `ui/row_arrangement/overlay_controls.py:209`).

---

**5. Signal and event flow**

Tile rearrangement:
- `GridGraphicsView.tiles_dropped` → `GridArrangementDialog._on_tiles_dropped_on_canvas` → `CanvasPlaceItemsCommand` / `CanvasMoveItemsCommand` → `GridArrangementManager.set_item_at/move_grid_item` → `arrangement_changed` emitted → `GridArrangementDialog._on_arrangement_changed` → `_update_displays` → `_update_arrangement_canvas` (`ui/components/visualization/grid_graphics_view.py:29`, `ui/grid_arrangement_dialog.py:1119`, `ui/row_arrangement/undo_redo.py:520`, `ui/row_arrangement/grid_arrangement_manager.py:84`, `ui/grid_arrangement_dialog.py:994`, `ui/grid_arrangement_dialog.py:1249`).

Overlay application:
- `QPushButton.clicked` → `GridArrangementDialog._apply_overlay` → `ApplyOperation.validate/execute` → `ApplyOverlayCommand.execute` → `_update_displays` → `OverlayLayer.set_visible(False)` → `OverlayLayer.visibility_changed` → `GridArrangementDialog._on_overlay_changed` → `_update_arrangement_canvas` (`ui/grid_arrangement_dialog.py:849`, `core/apply_operation.py:98`, `ui/row_arrangement/undo_redo.py:614`, `ui/row_arrangement/overlay_layer.py:211`, `ui/grid_arrangement_dialog.py:1010`).

Overlay movement / state changes:
- Overlay drag → `OverlayGraphicsItem.itemChange` → `OverlayLayer.set_position` → `position_changed` → `OverlayControls._update_position_spinboxes` and `GridArrangementDialog._on_overlay_changed` → redraw (`ui/row_arrangement/overlay_item.py:45`, `ui/row_arrangement/overlay_controls.py:209`, `ui/grid_arrangement_dialog.py:1010`).
- `OverlayLayer.import_image` emits `image_changed`, `scale_changed`, and `position_changed` in sequence, causing multiple redraws (`ui/row_arrangement/overlay_layer.py:86`).

ROM reinjection (no signals, direct call chain):
- `save_to_rom` → `ArrangementBridge.logical_to_physical` → `rom_extractor.inject_sprite_to_rom` → `ROMInjector.inject_sprite_to_rom` (`ui/sprite_editor/controllers/rom_workflow_controller.py:1766`, `core/rom_injector.py:499`).

Signals with no listeners in this dialog context:
- `GridArrangementManager.tile_added/tile_removed/group_added/group_removed/arrangement_cleared` are emitted but not connected in `GridArrangementDialog` (`ui/row_arrangement/grid_arrangement_manager.py:36`, `ui/grid_arrangement_dialog.py:156`).

Signals emitted multiple times for one user action:
- `OverlayLayer.import_image` emits multiple signals (`image_changed`, `scale_changed`, `position_changed`), all feeding `_on_overlay_changed` and causing repeated redraws (`ui/row_arrangement/overlay_layer.py:86`, `ui/grid_arrangement_dialog.py:1010`).

Missing signal-based propagation:
- `ApplyOverlayCommand` updates the `tiles` dict via a callback, not a signal; no external listeners can observe tile pixel changes unless they’re wired into that callback (`ui/row_arrangement/undo_redo.py:614`).
