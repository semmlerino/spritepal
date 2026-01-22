• Highest‑risk desync areas: asset browser + library (refresh, delete, alignment), modified‑indicator ordering when opening a new sprite, and multi‑palette prerequisites not
  syncing from drag/drop.

  UI Reflection Contract Inventory

  - C1 SourceBar (ROM workflow header) — Observables: ROM path, info/modified indicator, checksum status, offset value, compression mode, primary action text/loading/enabled.
    Source of truth: ROMWorkflowController state + EditingController undo state. Signals/events: ROMWorkflowController.rom_info_updated, ROMWorkflowController.offset_changed,
    EditingController.undoStateChanged, SourceBar.offset_changed (user). UI API: ROMWorkflowPage.set_rom_path, ROMWorkflowPage.set_info, ROMWorkflowPage.set_checksum_valid,
    ROMWorkflowPage.set_offset, ROMWorkflowPage.set_compression_type, ROMWorkflowPage.set_action_text, ROMWorkflowPage.set_action_loading, ROMWorkflowPage.set_modified_indicator.
    References: ui/sprite_editor/views/workspaces/rom_workflow_page.py:222, ui/sprite_editor/views/workspaces/rom_workflow_page.py:230, ui/sprite_editor/views/widgets/
    source_bar.py:183.
  - C2 Asset browser (SpriteAssetBrowser) — Observables: category lists, selection, thumbnails, refresh behavior, context‑menu actions. Source of truth: ROMWorkflowController +
    capture sync for ROM/Mesen; LibraryService/SpriteLibrary for library items. Signals/events: sprite_selected, sprite_activated, rename_requested, delete_requested,
    save_to_library_requested, item_offset_changed, refresh_requested. UI API: ROMWorkflowPage.add_rom_sprite, ROMWorkflowPage.add_mesen_capture,
    ROMWorkflowPage.add_library_sprite, ROMWorkflowPage.set_thumbnail, SpriteAssetBrowser.remove_sprite_by_offset, SpriteAssetBrowser.update_sprite_offset. References: ui/
    sprite_editor/views/widgets/sprite_asset_browser.py:822, ui/sprite_editor/views/widgets/sprite_asset_browser.py:706, ui/sprite_editor/views/widgets/
    sprite_asset_browser.py:270, ui/sprite_editor/views/widgets/sprite_asset_browser.py:1011.
  - C3 Workflow mode gating (ROM workflow page) — Observables: left panel/workspace enabled states per “preview/edit/save.” Source of truth: ROMWorkflowController.state. Signal/
    event: state transitions in controller. UI API: ROMWorkflowPage.set_workflow_state. Reference: ui/sprite_editor/views/workspaces/rom_workflow_page.py:162.
  - C4 Edit workspace (canvas + panels) — Observables: tool selection, palette selection, save/export enabled, palette warnings, status bar. Source of truth: EditingController
    models and validation state. Signals/events: toolChanged, colorChanged, paletteChanged, paletteSourceSelected, paletteSourcesCleared, validationChanged, imageChanged,
    undoStateChanged. UI API: EditWorkspace.set_controller wiring, EditWorkspace.set_save_enabled, EditWorkspace._update_palette. Reference: ui/sprite_editor/views/workspaces/
    edit_workspace.py:356.
  - C5 Extract tab (VRAM/ROM extraction) — Observables: file paths, extract/load buttons, output text. Source of truth: ExtractionController (mode/worker) + ExtractTab inputs.
    Signals/events: ExtractionController.progress_updated, ExtractionController.extraction_failed, ExtractTab.extract_requested, ExtractTab.browse_*. UI API:
    ExtractTab.set_vram_file, ExtractTab.set_cgram_file, ExtractTab.set_rom_file, ExtractTab.append_output, ExtractTab.set_extract_enabled. Reference: ui/sprite_editor/views/tabs/
    extract_tab.py:237. Contract gap: DropZone file drops do not update controller state (no explicit controller setter in ExtractTab).
  - C6 Multi‑palette tab — Observables: generate‑preview button enabled, preview grid, output warnings. Source of truth: ExtractionController.vram_file/cgram_file +
    MultiPaletteTab.oam_file_edit. Signals/events: generate_preview_requested, ExtractionController.multi_palette_completed. UI API: MultiPaletteTab.set_palette_images,
    MultiPaletteTab.set_oam_statistics, _validate_prerequisites (internal). Reference: ui/sprite_editor/views/tabs/multi_palette_tab.py:373. Contract gap: prerequisites only read
    controller fields; no sync from drag/drop path.
  - C7 Inject tab — Observables: validation text + color, inject/save enabled, output log. Source of truth: InjectionController validation/worker state. Signals/events:
    validation_completed, progress_updated, injection_failed/completed. UI API: InjectTab.set_validation_text, InjectTab.set_inject_enabled, InjectTab.append_output. Reference:
    ui/sprite_editor/views/tabs/inject_tab.py:170.

  Findings

  1) Library thumbnails are wiped on refresh and never restored (C2)

  - Source of truth: LibraryService/SpriteLibrary saved thumbnails. Signal/event: SpriteAssetBrowser.refresh_requested and thumbnail worker thumbnail_ready. References: core/
    services/library_service.py:92, ui/sprite_editor/views/widgets/sprite_asset_browser.py:822.
  - Expected UI reflection: Refresh should re‑extract ROM/Mesen thumbnails but preserve library thumbnails in the asset browser.
  - Desynchronization classification: stale UI + partial update. Impact: Medium (library entries lose visual identity until reload).
  - Evidence and test coverage:
      - UI clears all thumbnails on refresh ui/sprite_editor/views/widgets/sprite_asset_browser.py:822.
      - Controller re‑queues all offsets for thumbnails ui/sprite_editor/controllers/rom_workflow_controller.py:653.
      - Worker only applies thumbnails to rom/mesen items ui/sprite_editor/controllers/rom_workflow_controller.py:189, leaving library items blank even though persisted thumbnails
        exist.
      - Existing tests only verify refresh clears thumbnails (not library retention): tests/ui/sprite_editor/test_asset_browser_offset_update.py:158.
  - Recommended fix:
      - Code fix: filter refresh to only rom/mesen offsets (add get_offsets_by_source to the browser) or immediately restore library thumbnails from LibraryService after refresh.
        Update _on_asset_browser_refresh accordingly.
      - Test fix: add a test asserting library thumbnails survive refresh without reaching into widget internals.
  - Test specification:
      1. Observable contract: Refreshing thumbnails must not clear library thumbnails.
      2. Why it fails today: refresh clears all thumbnails, and the controller only re‑applies rom/mesen thumbnails.
      3. Minimal setup + action:
          - Create SpriteAssetBrowser, add a library sprite with a known thumbnail.
          - Click the button whose text is “Refresh Thumbnails” to emit refresh_requested.
      4. Assertions:
          - Source‑of‑truth: LibraryService still has a thumbnail path for the sprite.
          - Public UI reflection: SpriteAssetBrowser.has_thumbnail(offset, source_type="library") (new public getter) returns True after refresh.

  2) Library delete can remove the wrong item when offsets collide (C2)

  - Source of truth: LibraryService.delete_sprite (library state). Signal/event: SpriteAssetBrowser.delete_requested. References: core/services/library_service.py:181, ui/
    sprite_editor/controllers/rom_workflow_controller.py:625.
  - Expected UI reflection: Deleting a library item should remove only that library entry; ROM/Mesen entries with the same offset must remain.
  - Desynchronization classification: stale UI / incorrect removal. Impact: Medium (user sees a deleted library sprite still present, or loses a ROM entry instead).
  - Evidence and test coverage:
      - Controller handles delete and calls offset‑only removal ui/sprite_editor/controllers/rom_workflow_controller.py:633.
      - remove_sprite_by_offset stops at first match, ignoring source_type ui/sprite_editor/views/widgets/sprite_asset_browser.py:270.
      - No tests cover delete collisions.
  - Recommended fix:
      - Code fix: add remove_sprite(offset, source_type) (or include unique ID in UserRole) and use it in _on_asset_deleted.
      - Test fix: add collision test using public signals and get_item_count.
  - Test specification:
      1. Observable contract: Deleting a library entry removes only the library entry (not the ROM entry) even when offsets collide.
      2. Why it fails today: remove_sprite_by_offset deletes the first match, which can be the ROM item.
      3. Minimal setup + action:
          - Create ROMWorkflowPage + ROMWorkflowController, add one ROM sprite and one library sprite with the same offset.
          - Emit asset_browser.delete_requested.emit(offset, "library").
      4. Assertions:
          - Source‑of‑truth: LibraryService.sprite_exists(offset, rom_path) is False.
          - Public UI reflection: asset_browser.get_item_count() shows library count decremented while ROM count unchanged.

  3) Offset alignment updates library UI without updating library persistence (C2)

  - Source of truth: LibraryService/SpriteLibrary stored offsets. Signal/event: preview alignment via SmartPreviewCoordinator.preview_ready. References: core/services/
    library_service.py:92, ui/sprite_editor/controllers/rom_workflow_controller.py:2855.
  - Expected UI reflection: If alignment changes the actual sprite offset, library persistence must update to the new offset (or library UI must not change).
  - Desynchronization classification: stale UI / invalid assumption. Impact: Medium (UI shows new offset, persistence still old; reloads revert).
  - Evidence and test coverage:
      - Controller updates UI offset and calls update_sprite_offset on all categories ui/sprite_editor/controllers/rom_workflow_controller.py:2881.
      - update_sprite_offset explicitly updates library entries too ui/sprite_editor/views/widgets/sprite_asset_browser.py:1011.
      - No library service method updates stored offset; persistence remains old.
      - Existing tests only cover UI text update (tests/ui/sprite_editor/test_asset_browser_offset_update.py:7), not persistence.
  - Recommended fix:
      - Code fix: add a LibraryService.update_sprite_offset(old_offset, new_offset, rom_path) and call it when alignment occurs, or skip library items in update_sprite_offset and
        re‑add through the library service.
      - Test fix: add a persistence/selection test for aligned offsets.
  - Test specification:
      1. Observable contract: After alignment, library state and asset browser must agree on the new offset.
      2. Why it fails today: UI updates offsets for library items, persistence does not.
      3. Minimal setup + action:
          - Create SpriteLibrary with a library sprite at old_offset, attach LibraryService, create controller + view, add library sprite to browser.
          - Set controller.current_offset = old_offset, emit controller.preview_coordinator.preview_ready.emit(... actual_offset=new_offset ...).
      4. Assertions:
          - Source‑of‑truth: library_service.sprite_exists(new_offset, rom_path) is True and sprite_exists(old_offset) is False.
          - Public UI reflection: asset_browser.select_sprite_by_offset(new_offset) returns True.

  4) [Modified] indicator can remain stale when a new sprite is opened (C1/C4)

  - Source of truth: EditingController undo history. Signal/event: EditingController.undoStateChanged. References: ui/sprite_editor/controllers/editing_controller.py:232, ui/
    sprite_editor/controllers/rom_workflow_controller.py:3075.
  - Expected UI reflection: Opening a new sprite clears undo history and removes the [Modified] indicator.
  - Desynchronization classification: ordering issue. Impact: Medium (user sees unsaved indicator on a fresh sprite).
  - Timeline:
      - T0: user selects a new sprite.
      - T1: open_in_editor() loads image, clearing undo history (undoStateChanged emitted).
      - T2: _on_undo_state_changed ignores because state is still “preview”.
      - Code fix: set self.state = "edit" before load_image, or store last undo state and apply it on state transitions; alternatively call set_modified_indicator(False)
        explicitly after open_in_editor completes.
      - Test fix: add an ordering regression test around open_in_editor.
  - Test specification:
      1. Observable contract: Opening a new sprite clears [Modified] in the SourceBar.
      2. Why it fails today: undoStateChanged fires while state is “preview,” so the indicator never clears.
      3. Minimal setup + action:
          - Instantiate EditingController, ROMWorkflowController, and ROMWorkflowPage; set view.
          - Force modified indicator via editing_ctrl.undoStateChanged.emit(True, False) while state is “edit.”
          - Set state to “preview,” provide minimal current_tile_data/current_width/current_height/current_offset, call open_in_editor().
      4. Assertions:
          - Source‑of‑truth: editing_ctrl.has_unsaved_changes() is False.
          - Public UI reflection: [Modified] not present in page.source_bar.info_label.text().

      - DropZone handler updates only the view ui/sprite_editor/views/tabs/extract_tab.py:237.
        _validate_prerequisites.
      - Test fix: add drag/drop prerequisite test.
  - Test specification:
      1. Observable contract: Drag‑dropped VRAM + CGRAM files enable multi‑palette preview.
      2. Why it fails today: controller file fields aren’t updated by drag/drop, so prerequisites stay false.
          - Emit extract_tab.vram_drop.file_dropped and extract_tab.cgram_drop.file_dropped with temp file paths.
      4. Assertions:
          - Source‑of‑truth: extraction_controller.vram_file and cgram_file equal the dropped paths.
          - Public UI reflection: multi_palette_tab.generate_multi_btn.isEnabled() is True.
