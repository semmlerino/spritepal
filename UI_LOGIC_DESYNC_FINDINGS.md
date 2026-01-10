# UI-Logic Desynchronization Findings
Date: January 10, 2026

## Summary
The Sprite Editor has significant desynchronization risks in **initialization sequences** (loading state into views that connect late) and **global vs. local state reflection** (shortcuts, undo/redo availability). The "Redesign" introduced a `SpriteEditorMainWindow` that duplicates some responsibilities of the `EditWorkspace` (toolbars, shortcuts) without fully synchronizing them, leading to conflicting user contracts.

## Findings

### 1. Stale Palette Sources on Workspace Load
*   **Source of Truth:** `EditingController._palette_sources` (private dict).
*   **Expected UI Reflection:** `PalettePanel` (dropdown) should list all registered ROM/Mesen palettes.
*   **Desync Risk:** **Stale UI / Ordering Issue**. Signals (`paletteSourceAdded`) are emitted when sources are registered. If the `EditWorkspace` (and its `PalettePanel`) is created or connected *after* registration (common in ROM workflow), it misses these signals. The view has no way to "pull" the current list, and the controller doesn't re-emit on connection.
*   **Evidence:**
    *   `ui/sprite_editor/controllers/editing_controller.py`: `register_palette_source` emits signal immediately. No public getter for sources.
    *   `ui/sprite_editor/views/workspaces/edit_workspace.py`: `set_controller` connects signals but doesn't query existing sources.
*   **Recommended Fix:**
    *   **Code:** Add `get_palette_sources()` to `EditingController`. Update `EditWorkspace.set_controller` to call this and populate `PalettePanel` immediately after connection.
    *   **Test:** Register a source on the controller *before* creating the view, then verify the view has it.
*   **Example Test:**
    ```python
    def test_palette_source_sync_late_connection(qtbot):
        from ui.sprite_editor.controllers.editing_controller import EditingController
        from ui.sprite_editor.views.workspaces.edit_workspace import EditWorkspace
        
        # 1. Setup Controller with pre-existing state
        controller = EditingController()
        # Simulate ROM workflow registering a palette BEFORE view exists
        controller.register_palette_source("rom", 10, [(255,0,0)]*16, "Red Palette")
        
        # 2. Create View and Connect
        workspace = EditWorkspace()
        qtbot.addWidget(workspace)
        workspace.set_controller(controller)
        
        # 3. Assert UI reflects state
        # Access the combo box to verify it has the item
        selector = workspace.palette_panel.palette_source_selector
        combo = selector.findChild(QComboBox) # or selector._combo_box
        
        # Expect "Default" + "Red Palette"
        assert combo.count() == 2
        assert combo.itemText(1) == "Red Palette"
    ```

### 2. Undo/Redo Actions Never Disabled
*   **Source of Truth:** `EditingController.undo_manager.can_undo()` / `can_redo()`.
*   **Expected UI Reflection:** `Action Undo` / `Action Redo` in `SpriteEditorMainWindow` should be disabled when stacks are empty.
*   **Desync Risk:** **Error State not Surfaced**. The Global Toolbar buttons are always enabled. Clicking them does nothing (safe but confusing), giving false affordance.
*   **Evidence:**
    *   `ui/sprite_editor/views/main_window.py`: `wire_controllers` connects `triggered` signals but *never* connects `editing_controller.undoStateChanged` to `action_undo.setEnabled`.
*   **Recommended Fix:**
    *   **Code:** In `SpriteEditorMainWindow.wire_controllers`, connect `editing_controller.undoStateChanged` to a slot that updates `action_undo.setEnabled` and `action_redo.setEnabled`. Initialize state immediately.
*   **Example Test:**
    ```python
    def test_undo_action_enable_state(qtbot):
        # ... setup main_window and controller ...
        main_window.wire_controllers(...)
        
        # Initially empty
        assert not main_window.action_undo.isEnabled()
        
        # Perform action
        controller.handle_pixel_press(0, 0) # ... draw something
        controller.handle_pixel_release(0, 0)
        
        # Should be enabled now
        assert main_window.action_undo.isEnabled()
    ```

### 3. Conflicting Shortcut Contracts ("F" Key)
*   **Source of Truth:** `SpriteEditorMainWindow` menu actions vs. `EditWorkspace` shortcuts.
*   **Expected UI Reflection:** Pressing "F" triggers the "Fill" tool (as advertised in the Menu).
*   **Desync Risk:** **UI reflects internal state instead of public contract**.
    *   Menu says "Fill (F)".
    *   Workspace defines `QShortcut("F", ... zoom_fit)`.
    *   Qt event propagation usually favors the focused child widget. Pressing "F" inside the editor will likely trigger **Zoom Fit**, contradicting the menu.
*   **Evidence:**
    *   `ui/sprite_editor/views/main_window.py`: `self.action_fill.setShortcut("F")`
    *   `ui/sprite_editor/views/workspaces/edit_workspace.py`: `QShortcut(QKeySequence("F"), self, self._on_zoom_fit)`
*   **Recommended Fix:**
    *   **Code:** Remap one of the shortcuts. Standard convention: "F" for Fill, "Ctrl+0" or "Shift+Z" for Fit. Or "B" (Bucket) for Fill to match other software, updating the Menu to match.
*   **Example Test:**
    ```python
    def test_shortcut_conflict_f_key(qtbot):
        # ... setup main_window with workspace ...
        # Focus canvas
        workspace.get_canvas().setFocus()
        
        # Press F
        qtbot.keyClick(workspace.get_canvas(), Qt.Key_F)
        
        # Assert: Did tool change to FILL?
        assert controller.get_current_tool_name() == "fill"
        # (This test currently FAILS; it zooms fit instead)
    ```

### 4. Palette Selector UI State is Manual
*   **Source of Truth:** `PaletteModel` (current colors).
*   **Expected UI Reflection:** `PaletteSourceSelector` (dropdown) selection should match the active palette source.
*   **Desync Risk:** **Missing Connection / Law of Demeter Violation**.
    *   `EditingController.set_palette_source` attempts to update the view manually via `getattr(palette_panel, 'palette_source_selector')`. This is brittle.
    *   If `set_palette` is called directly (loading a file), the dropdown doesn't know it's no longer on "Default" or "ROM". It might show "ROM Palette 1" while displaying loaded file colors.
*   **Evidence:**
    *   `ui/sprite_editor/controllers/editing_controller.py`: `set_palette_source` manually pokes UI. `handle_load_palette` updates colors but *doesn't* update the source selector to a "Custom/File" state.
*   **Recommended Fix:**
    *   **Code:** Add a "Custom" or "File" state to `PaletteSourceSelector`. Emit a signal from `EditingController` when palette is replaced by file, prompting UI to switch dropdown to "Custom".

## Additional Findings (UI Logic Desync Review)

### 1. Manual Offset Preview Alignment Not Reflected
*   **Source of Truth:** `SmartPreviewCoordinator.preview_ready` (actual_offset, hal_succeeded) in `ui/common/smart_preview_coordinator.py`.
*   **Expected UI Reflection:** Manual offset dialog should update the displayed offset when preview aligns to a different offset.
*   **Desync Risk:** **Stale UI / Partial update.** Preview content can come from an adjusted offset, but the offset display and status text continue showing the requested offset.
*   **Evidence:**
    *   `ui/common/smart_preview_coordinator.py`: `preview_ready` emits `actual_offset`.
    *   `ui/common/preview_worker_pool.py`: `PooledPreviewWorker._run_with_cancellation_checks` adjusts `self.offset` and emits `actual_offset`.
    *   `ui/dialogs/manual_offset_dialog.py`: `UnifiedManualOffsetDialog._on_smart_preview_ready` ignores `actual_offset` and uses `get_current_offset()`.
    *   `ui/sprite_editor/controllers/rom_workflow_controller.py`: `_on_preview_ready` updates the UI when `actual_offset` differs (contrasting behavior).
*   **Test Gap or Smell:** `tests/integration/test_integration_manual_offset.py::test_preview_generation_on_offset_change` only checks that a preview exists; it would pass even if the offset display is wrong.
*   **Recommended Fix:**
    *   **Code:** Update `_on_smart_preview_ready` to accept `actual_offset` and sync the browse tab offset/status text when it differs.
    *   **Test:** Trigger a preview that aligns to a nearby offset and assert the displayed offset matches `actual_offset`.
*   **Example Test:**
    ```python
    def test_manual_offset_aligns_displayed_offset(dialog, qtbot):
        dialog.set_rom_data(rom_path, rom_size, extraction_manager)
        dialog.set_offset(0x20000)

        with qtbot.waitSignal(dialog.preview_ready, timeout=2000) as sig:
            pass
        actual_offset = sig.args[6]

        assert dialog.get_current_offset() == actual_offset
        assert f"0x{actual_offset:06X}" in dialog.status_text()
    ```

### 2. ROM Extraction Ready State Not Updated on Sprite Location Errors
*   **Source of Truth:** `ExtractionParamsController.readiness_changed` from `ui/controllers/extraction_params_controller.py`.
*   **Expected UI Reflection:** Extract button should disable (with reason) when sprite locations fail to load.
*   **Desync Risk:** **Stale UI.** UI can remain "ready" while the sprite selector is disabled or cleared.
*   **Evidence:**
    *   `ui/rom_extraction_panel.py`: `_on_sprite_locations_error` clears the selector but does not call `_check_extraction_ready`.
    *   `ui/rom_extraction_panel.py`: `_check_extraction_ready` is the only source of `extraction_ready` updates.
    *   `ui/main_window.py`: `_on_rom_extraction_ready` is the only path that enables/disables the extract action.
*   **Test Gap or Smell:** No test verifies that a sprite location error disables extraction (existing ROM panel tests focus on output name only).
*   **Recommended Fix:**
    *   **Code:** Call `_check_extraction_ready()` in `_on_sprite_locations_error`, and optionally emit a failure reason.
    *   **Test:** Force a sprite locations error and assert the extract action disables.
*   **Example Test:**
    ```python
    def test_rom_panel_disables_extract_on_location_error(panel, main_window, qtbot):
        panel.set_output_name("test")
        panel.select_sprite_by_offset(0x10000)
        with qtbot.waitSignal(panel.extraction_ready, timeout=1000):
            pass
        assert main_window.extract_button.isEnabled()

        panel._on_sprite_locations_error("failed")
        with qtbot.waitSignal(panel.extraction_ready, timeout=1000) as sig:
            pass
        assert sig.args[0] is False
        assert not main_window.extract_button.isEnabled()
    ```

### 3. Sprite Editor Undo/Redo Action Enablement Not Wired
*   **Source of Truth:** `EditingController.undoStateChanged` in `ui/sprite_editor/controllers/editing_controller.py`.
*   **Expected UI Reflection:** Undo/redo actions should enable/disable based on undo stack state.
*   **Desync Risk:** **Missing connection.** Actions remain enabled even when stacks are empty, giving false affordance.
*   **Evidence:**
    *   `ui/sprite_editor/controllers/editing_controller.py`: `_emit_undo_state` emits `undoStateChanged`.
    *   `ui/sprite_editor/views/main_window.py`: `SpriteEditorMainWindow.wire_controllers` connects action triggers but not `undoStateChanged`.
*   **Test Gap or Smell:** No tests assert `action_undo`/`action_redo` enabled state.
*   **Recommended Fix:**
    *   **Code:** Connect `undoStateChanged` to a handler that updates `action_undo`/`action_redo`.
    *   **Test:** Perform a reversible edit, assert undo is enabled, undo it, assert redo is enabled.
*   **Example Test:**
    ```python
    def test_undo_redo_actions_follow_state(window, editing_controller, qtbot):
        window.wire_controllers(extraction_controller, editing_controller, injection_controller)
        assert not window.action_undo.isEnabled()

        editing_controller.apply_brush_stroke(...)
        assert window.action_undo.isEnabled()

        editing_controller.undo()
        assert window.action_redo.isEnabled()
    ```
