# Sprite Arrangement Dialog UX & Interaction Audit

Assumed this refers to the grid-based "Grid-Based Sprite Arrangement" dialog (`ui/grid_arrangement_dialog.py`).

## Controls And Interactions — Dialog Shell
- Window title + status bar; status messages update on selection/operations; always enabled; discoverable via visible status bar. (`ui/grid_arrangement_dialog.py`)
- Left/right splitter handle; drag to resize panels; always enabled; discoverable by standard splitter affordance. (`ui/grid_arrangement_dialog.py`)
- OK/Cancel button box; always enabled; discoverable as standard buttons; OK closes without exporting. (`ui/components/base/dialog_base.py`, `ui/grid_arrangement_dialog.py`)
- Export action is only reachable via Ctrl+E; enabled only when arranged_count>0; button is created but never added to the button box. (`ui/grid_arrangement_dialog.py`, `ui/components/base/dialog_base.py`)

## Controls And Interactions — Left Panel (Selection + Source Grid)
- Selection Mode segmented toggle (Tile/Row/Column/Marquee); intended to change selection mode and update guidance; always enabled; discoverable via labels/tooltips/legend, but not wired to the grid view. (`ui/grid_arrangement_dialog.py`, `ui/widgets/segmented_toggle.py`)
- Sprite Grid (GridGraphicsView) mouse: drag tile(s) to canvas; ctrl+click toggles selection and emits tile_clicked; drag on empty space creates marquee selection; shift-drag adds to selection; middle-mouse pans; wheel zooms without modifiers; hover highlight and drop placeholder during drag; always enabled, mostly undiscoverable except by trial. (`ui/components/visualization/grid_graphics_view.py`, `ui/grid_arrangement_dialog.py`)
- Sprite Grid keyboard: arrows move keyboard focus; shift+arrows extend selection in non-Tile modes; Space/Enter toggles selection in Tile mode; Home/End/PageUp/PageDown jump focus; Escape clears selection; F/Ctrl+0/Ctrl++/Ctrl+- zoom; discoverability partially implied by legend (some of which is incorrect). (`ui/components/visualization/grid_graphics_view.py`, `ui/grid_arrangement_dialog.py`)

## Controls And Interactions — Left Panel (Actions + Zoom)
- Actions buttons: Add Selection, Add All, Magic Wand, Remove Selection, Create Group, Clear All, Reset to 1:1; always enabled; discoverable via labels/tooltips/legend; several no-op silently when no selection. (`ui/grid_arrangement_dialog.py`)
- Target Sheet Width spinbox (1-64); affects canvas grid width + preview layout; always enabled; discoverable via label/tooltip. (`ui/grid_arrangement_dialog.py`)
- Zoom buttons (-, +, Fit, 1:1) + zoom % label; always enabled; discoverable via labels/tooltips. (`ui/grid_arrangement_dialog.py`, `ui/components/visualization/grid_graphics_view.py`)

## Controls And Interactions — Right Panel (Canvas + Overlay + Preview)
- Current Arrangement canvas (GridGraphicsView) mouse: accepts drops from source; drag within canvas to move items; ctrl+click/marquee to select; click without ctrl does not select; wheel zoom; middle-mouse pan; keyboard behavior mirrors source grid when focused. (`ui/components/visualization/grid_graphics_view.py`, `ui/grid_arrangement_dialog.py`)
- Overlay controls: Import, Clear, X/Y spinboxes, opacity slider, visibility checkbox; Clear/X/Y/opacity/visibility disabled until overlay image present; discoverable via group label/tooltips. (`ui/row_arrangement/overlay_controls.py`)
- Overlay nudge: arrow keys move overlay +/-1px (+/-10px with Shift) whenever an overlay is loaded; discoverable via hint label but conflicts with grid navigation. (`ui/row_arrangement/overlay_controls.py`, `ui/grid_arrangement_dialog.py`)
- Apply Overlay button: samples overlay into arranged tiles, shows warnings/confirm, undoable; always enabled but warns if missing overlay or tiles; discoverable via label/tooltip. (`ui/grid_arrangement_dialog.py`)
- Arrangement Preview: scrollable pixmap preview; no direct interactions beyond scroll; discoverable via group title. (`ui/grid_arrangement_dialog.py`)

## Global Shortcuts
- Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z undo/redo; Delete removes selection; Escape clears selection (not arrangement); Ctrl+E export; C toggles palette, P cycles palette; discoverability is mostly implicit. (`ui/grid_arrangement_dialog.py`)
- Mouse wheel zooms without Ctrl even though status text says Ctrl+Wheel. (`ui/components/visualization/grid_graphics_view.py`, `ui/grid_arrangement_dialog.py`)

## Common Flows
- Drag-and-drop arrangement: ctrl+click or marquee select -> drag from Sprite Grid -> drop on canvas -> adjust Target Sheet Width -> Export (Ctrl+E). (`ui/components/visualization/grid_graphics_view.py`, `ui/grid_arrangement_dialog.py`)
- Add Selection flow: marquee select on Sprite Grid -> Add Selection button -> auto-placed row-major (width_hint=16) -> preview updates -> Export. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/grid_arrangement_manager.py`)
- Add All / Magic Wand: click button -> preview updates and source grid dims -> Export; canvas may remain empty. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/undo_redo.py`)
- Remove flow: select on canvas (ctrl+click/marquee) -> Delete/Remove Selection -> items removed; drag on canvas to reposition. (`ui/grid_arrangement_dialog.py`)
- Overlay flow: Import overlay -> adjust position/opacity -> Apply Overlay -> Export. (`ui/row_arrangement/overlay_controls.py`, `ui/grid_arrangement_dialog.py`)

## Edge Cases
- No sprite loaded: error status shown; UI still present but data empty. (`ui/grid_arrangement_dialog.py`)
- Export with no tiles: status "No tiles arranged for export"; no confirmation. (`ui/grid_arrangement_dialog.py`)
- Add/Remove Selection with no selection: silent no-op. (`ui/grid_arrangement_dialog.py`)
- Reset to 1:1 when Target Sheet Width < source cols: mapping may place tiles outside canvas width. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/grid_arrangement_manager.py`)
- Overlay loaded: arrow keys nudge overlay instead of moving grid focus. (`ui/grid_arrangement_dialog.py`)

## Cold-Start Usability
- Clarity of intent: "Sprite Grid" vs "Current Arrangement" helps, but drag-and-drop isn't stated and Selection Mode doesn't change behavior. (`ui/grid_arrangement_dialog.py`)
- Feedback/affordances: arranged tiles dim, preview updates, but canvas can stay empty for some actions; status text doesn't match actual shortcuts. (`ui/components/visualization/grid_graphics_view.py`, `ui/grid_arrangement_dialog.py`)
- Cognitive load/mode confusion: multiple add/remove paths with different results and undo coverage; overlay keys hijack navigation. (`ui/grid_arrangement_dialog.py`)
- Error-proneness/recoverability: OK closes without export; Export hidden; some operations bypass undo. (`ui/grid_arrangement_dialog.py`, `ui/components/base/dialog_base.py`, `ui/row_arrangement/undo_redo.py`)

## Hidden Or Non-Discoverable
- Ctrl+click selection, marquee on empty space only, middle-mouse pan, wheel-zoom without modifier, palette toggles (C/P), and drag-to-canvas aren't surfaced. (`ui/components/visualization/grid_graphics_view.py`, `ui/grid_arrangement_dialog.py`)
- Export is hidden behind Ctrl+E only. (`ui/grid_arrangement_dialog.py`, `ui/components/base/dialog_base.py`)
- Selection Mode buttons imply behavior but don't connect to the grid view. (`ui/grid_arrangement_dialog.py`, `ui/widgets/segmented_toggle.py`)

## Redundant / Overlapping
- Tile-mode click/ctrl+click auto add/remove overlaps with Add/Remove Selection but behaves differently. (`ui/grid_arrangement_dialog.py`)
- Add All/Magic Wand operate on linear order while canvas drag/drop operates on grid mapping, creating two mental models. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/undo_redo.py`)

## Inconsistent Input Handling
- Shortcut legend/tooltips advertise [T/R/C/M], [Enter], [Esc] but handlers don't match. (`ui/grid_arrangement_dialog.py`, `ui/components/visualization/grid_graphics_view.py`)
- Undo only for some actions (drag/drop, Add All, Magic Wand, Apply Overlay) but not Add Selection/Remove Selection/click-add. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/undo_redo.py`)
- Arrow keys are grid navigation unless overlay is loaded, then they always nudge overlay. (`ui/grid_arrangement_dialog.py`)

## Implicit Knowledge
- "Target Sheet Width" role in export vs canvas placement is not explained and auto-placement ignores it. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/grid_arrangement_manager.py`)
- Create Group has no visible effect on the canvas, requiring knowledge of arrangement order semantics. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/grid_arrangement_manager.py`)

## Concrete Improvements — Core
- Make Export visible and primary: add it to the button box (or replace OK with Export) and keep Ctrl+E as a shortcut. (`ui/grid_arrangement_dialog.py`, `ui/components/base/dialog_base.py`)
- Wire Selection Mode: connect `mode_toggle.selection_changed` to `_on_mode_changed` and implement row/column/marquee click behavior in `GridGraphicsView`. (`ui/grid_arrangement_dialog.py`, `ui/components/visualization/grid_graphics_view.py`)
- Align shortcuts/tooltips with behavior (or implement the advertised keys). (`ui/grid_arrangement_dialog.py`, `ui/components/visualization/grid_graphics_view.py`)
- Normalize undo coverage: wrap Add Selection, Remove Selection, and click-add/remove in undoable commands. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/undo_redo.py`)

## Concrete Improvements — UX Polish
- Unify arrangement models: either place Add All/Magic Wand results onto the canvas or label them as "Linear order only"; keep tile_set/mapping in sync. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/grid_arrangement_manager.py`, `ui/row_arrangement/undo_redo.py`)
- Make selection obvious: allow single-click selection, add explicit drag-and-drop guidance, and show which grid has focus. (`ui/components/visualization/grid_graphics_view.py`, `ui/grid_arrangement_dialog.py`)
- Resolve arrow-key conflict: reserve arrows for grid navigation and use Alt+Arrows (or overlay-controls focus) for nudging. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/overlay_controls.py`)
- Use Target Sheet Width consistently for auto-placement and reset; or auto-sync width to source cols on reset. (`ui/grid_arrangement_dialog.py`, `ui/row_arrangement/grid_arrangement_manager.py`)
