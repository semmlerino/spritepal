A) Current-state map (“what it actually does”)
- Entry points: GUI `launch_spritepal.py:main` calling AppContext -> MainWindow; CLI scripts `scripts/extract_rom_sprite.py`, `scripts/inject_rom_sprite.py`, `scripts/extract_sprite_from_capture.py`.
- ROM extraction: `MainWindow.on_extract_clicked` -> `_handle_rom_extraction` -> `ExtractionWorkflowCoordinator.start_rom_extraction` -> `ROMExtractionWorker.perform_operation` -> `CoreOperationsManager.extract_from_rom` -> `ROMExtractor.extract_sprite_from_rom` -> HAL decompression + palette creation -> `ExtractionResult` returned and `extraction_completed` signal consumed by MainWindow for preview/palette updates and by legacy signals for compatibility.
- VRAM extraction: `MainWindow.on_extract_clicked` (VRAM tab) -> `_handle_vram_extraction` -> `ExtractionWorkflowCoordinator.start_vram_extraction` -> `VRAMExtractionWorker.perform_operation` -> `CoreOperationsManager.extract_from_vram` -> `SpriteExtractor.extract_sprites_grayscale` -> palette creation -> `ExtractionResult` signal chain mirroring ROM path.
- Injection flow: `MainWindow._start_injection` -> dialog -> `InjectionWorkflowCoordinator.start_injection` -> `CoreOperationsManager.start_injection` -> `VRAMInjectionWorker`/`ROMInjectionWorker` -> `SpriteInjector`/`ROMInjector` -> injection progress signals -> MainWindow status updates.
- Mesen capture -> sprite editor: `LogWatcher.offset_discovered` -> `Mesen2Module.connect_signals` -> `RecentCapturesWidget.add_capture` -> UI double-click triggers `ROMExtractionPanel.open_in_sprite_editor` -> `MainWindow._on_open_in_sprite_editor` -> `SpriteEditorWorkspace.jump_to_offset` -> `ROMWorkflowController.set_offset` -> `SmartPreviewCoordinator`/worker preview -> `_on_preview_ready` -> `open_in_editor`.
- ROM scan: `ROMWorkerOrchestrator.start_scan` -> `SpriteScanWorker.run` -> `ParallelSpriteFinder.search_parallel` -> results via `sprite_found` signals -> UI updates + cache saves.

B) Diagnosis
- Hidden globals and fragile init: `get_app_context()` abused across UI/core (e.g., `ui/common/file_dialogs.py:7`, `ui/sprite_editor/controllers/injection_controller.py:69`, `core/app_context.py:272`), forcing a strict init order and scattering implicit dependencies.
- Signal/control-flow coupling + duplication: `CoreOperationsManager` emits consolidated and legacy signals (`core/managers/core_operations_manager.py:70`) while `MainWindow` listens both to coordinators and manager signals (`ui/main_window.py:1501`), and preview signals carry 9 positional args (`ui/common/smart_preview_coordinator.py:110`), so orchestration depends on signal timing.
- Manager/controller sprawl: `MainWindow` handles UI, extraction/injection, session persistence, keyboard shortcuts; `ROMWorkflowController` mixes ROM IO, palette selection, library persistence, preview coordination; `CoreOperationsManager` mixes worker lifecycle, cache, preview, injection, scan logic.
- Ad-hoc payloads: dict-based params flow between layers (`ui/main_window.py:1079`, `ui/services/extraction_workflow_coordinator.py:61`, `core/managers/core_operations_manager.py:801`), making typing and law-of-demeter compliance difficult.

C) Target architecture
- Layers: `core/domain` (pure models + algorithms), `core/application` (typed use-case services, e.g., `ExtractionService`, `InjectionService`, `PreviewService`), `core/infrastructure` (ROM IO, cache, HAL, file access); `ui/adapters` for Qt wiring.
- Use explicit wiring in a Bootstrapper module, pass typed request/response dataclasses (e.g., `RomExtractionRequest`, `PreviewResult`), retire globals and dict payloads; signals only notify UI (progress, completion) with typed payloads, no business control.
- Control flow: UI controllers call application services directly; services orchestrate domain + infrastructure via constructor-injected interfaces; events only report state (progress, cache stats) but not orchestrate business decisions.
- Layout/naming: `core/domain/*.py`, `core/application/*.py`, `core/infrastructure/*.py`; `ui/controllers/*`, `ui/views/*`, `ui/adapters/*`; typed dataclasses in `core/application/models.py` and `core/application/interfaces.py` for ports.
- Worker threads run service methods via a shared `TaskRunner` rather than coordinators, enabling explicit callbacks.

D) Verification
- Existing tests covering workflows: `tests/integration/test_core_operations_manager.py`, `tests/integration/test_rom_extraction_regression.py`, `tests/integration/test_rom_injection.py`, `tests/integration/test_smart_preview.py`, `tests/ui/integration/test_rom_workflow_integration.py`, `tests/ui/integration/test_mesen_workflow.py`, `tests/integration/test_parallel_sprite_finder.py`, `tests/ui/integration/test_workflow_signal_order.py`.
- Gap: lack of typed service contract tests; plan to add unit tests for `ExtractionService`, `InjectionService`, `PreviewService` using golden ROM fixtures, plus a headless smoke script (e.g., `scripts/test_runners/smoke_workflows.py`).
- Commands for verification: `uv run pytest -n 0 tests/integration/test_core_operations_manager.py::test_extract_from_rom`, `uv run pytest -n 0 tests/integration/test_rom_injection.py`, `uv run pytest -n 0 tests/ui/integration/test_mesen_workflow.py`, `uv run pytest -n 0 tests/integration/test_parallel_sprite_finder.py`, `uv run pytest -n 0 tests/ui/integration/test_rom_workflow_integration.py`.

E) Completed Refactoring (January 2026)

### Phase 1: Critical Error Handling (✅ Complete)
- `ui/common/file_dialogs.py`: Added try/except around `get_app_context()` in 4 static methods (`browse_directory`, `browse_open_file`, `browse_save_file`, `get_smart_initial_directory`); falls back to `Path.home()` when AppContext unavailable.
- `ui/widgets/sprite_preview_widget.py`: Added try/except in `_start_similarity_search_async` to handle missing AppContext gracefully.

### Phase 2: MesenCaptureSync Service Extraction (✅ Complete)
- Created `core/services/mesen_capture_sync.py` with 9 extracted methods from ROMWorkflowController:
  - `connect()`, `sync_from_log_watcher()`, `normalize_offset()`, `get_capture_name()`
  - `record_offset_adjustment()`, `_on_offset_discovered()`, `_on_offset_rediscovered()`
  - `_validate_capture_rom_match()`, `_add_capture_to_browser()`, `_update_capture_in_browser()`
- Includes `ViewAssetBrowserAdapter` to wrap view's asset browser dynamically
- Includes `AssetBrowserProtocol` and `MessageServiceProtocol` for dependency injection
- ROMWorkflowController now delegates to `MesenCaptureSync` service

### Phase 3: LibraryService Extraction (✅ Complete)
- Created `core/services/library_service.py` with core CRUD operations:
  - `save_sprite()`, `rename_sprite()`, `delete_sprite()`, `get_sprites_for_rom()`
  - `sprite_exists()`, `get_thumbnail_path()`, `update_palette_association()`
- Uses callback-based messaging (`on_message: MessageCallback`) instead of Qt signals
- ROMWorkflowController delegates library operations to `LibraryService`

### Impact
- ROMWorkflowController reduced from ~98 methods to ~79 methods
- Two new focused services with clear responsibilities
- No external API changes - internal refactoring only
- All 2873 tests pass

F) Recommended Next Steps

### High-Value Extractions (Priority Order)
1. **PreviewService extraction** from `ROMWorkflowController` (~10 methods):
   - `_on_preview_ready()`, `_on_preview_error()`, `_generate_preview_thumbnail()`
   - Would further reduce controller to ~69 methods

2. **ThumbnailService extraction** from `ROMWorkflowController` (~8 methods):
   - `_queue_thumbnail()`, `_on_thumbnail_ready()`, `_load_library_thumbnail()`
   - Cohesive subsystem for async thumbnail generation/caching

3. **StateTransitionService extraction** from `ROMWorkflowController`:
   - `_set_state()`, `_transition_to_edit_mode()`, `_transition_to_preview_mode()`
   - Encapsulate workflow state machine

### Medium-Term Goals
- Extract similar services from `MainWindow` (currently ~2500 lines)
- Extract services from `CoreOperationsManager` (currently ~900 lines)
- Replace dict-based payloads with typed dataclasses
- Move toward target architecture (section C)
