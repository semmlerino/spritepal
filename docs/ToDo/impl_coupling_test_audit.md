Reviewed the tests for private state access, private-method calls, strict mock call counts, and introspection. The following are high-risk for failing after a correct refactor because they lock in internal details or call sequences instead of externally observable behavior.

Private State / Private API Assertions
- tests/integration/test_manager_performance_benchmarks_tdd.py:70 asserts _sprite_extractor/_rom_extractor (private internals).
- tests/integration/test_extraction_manager.py:102 asserts _sprite_extractor/_rom_extractor/_palette_manager.
- tests/integration/test_core_operations_manager.py:682 asserts _current_worker cleanup state.
- tests/integration/test_hal_compression.py:520 asserts _pool and _pool_failed.
- tests/integration/test_main_window_state_integration_real.py:592 asserts _output_path.
- tests/integration/test_integration_manual_offset.py:371 reads _manual_offset_dialog and _params_controller.
- tests/integration/test_thread_safety_comprehensive.py:271 asserts _pending_count and _stop_requested, touches _cache.
- tests/integration/test_batch_thumbnail_worker_integration.py:229 asserts _pending_count/_completed_count.
- tests/integration/test_worker_manager.py:138 asserts _interrupted/_work_cycles.
- tests/integration/test_parallel_sprite_finder.py:297 asserts executor._shutdown.
- tests/ui/repro_overlay_visible.py:31 asserts _overlay_image/_overlay_visible/_overlay_scale.
- tests/ui/integration/test_pixel_canvas_signals.py:279 asserts _qcolor_cache and _last_hover_rect.
- tests/ui/integration/test_sprite_project_workflow.py:86 reaches _save_export_panel.
- tests/ui/test_grid_arrangement_ux_fixes.py:89 checks _target_width, _legend_content, _legend_toggle_btn.
- tests/ui/test_tile_identity_end_to_end.py:153 asserts _apply_result.
- tests/ui/test_overlay_apply_bugs.py:75 asserts _apply_result and uses _apply_overlay.
- tests/unit/test_color_quantization.py:245 asserts _dither.
- tests/unit/test_region_analyzer.py:449 checks _cache length.
- tests/unit/mesen_integration/test_rom_tile_matcher.py:456 asserts _blocks/_hash_to_locations/_total_tiles/_unique_hashes.
- tests/unit/test_rom_extractor.py:31 calls _has_4bpp_characteristics.
- tests/unit/test_configuration_service.py:89 asserts _settings_manager.
- tests/unit/test_search_worker_simple.py:76 asserts _cancelled on a mock worker (no real SUT).

Private Methods / LoD Violations
- tests/integration/test_integration_manual_offset.py:98 patches _search_coordinator.scan_for_sprites and calls _on_smart_preview_ready.
- tests/ui/test_overlay_scaling_editor.py:12 calls _merge_overlay_to_indexed, _on_overlay_import_requested, and reaches _view.workspace.overlay_panel._scale_slider.
- tests/ui/test_save_button_sync.py:8 calls _on_validation_changed.
- tests/ui/test_palette_association.py:9 calls _on_save_to_library and _on_palette_changed with deep mocks.
- tests/ui/rom_extraction/test_rom_workflow_controller.py:55 calls _on_preview_ready and sets _thumbnail_controller.
- tests/ui/test_rom_panel_output_name.py:8 uses _worker_orchestrator directly.

Strict Call Counts / Implementation Sequencing
- tests/integration/test_worker_manager.py:499 asserts exact wait() call counts and order.
- tests/integration/test_preview_generator.py:360 asserts QPixmap.scaled called once and exact manager call count.
- tests/ui/test_palette_integration.py:9 asserts mocked handler call counts for wiring.
- tests/ui/test_rom_palette_workflow.py:6 asserts exact calls to extractor/registrations.
- tests/ui/test_rom_panel_output_name.py:27 asserts provider call_count == 2.

If you want, I can go deeper and produce a full inventory with a proposed behavior-focused rewrite for each.
