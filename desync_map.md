Mapped the end-to-end flow and the concrete desync points without changing code. Below is the data flow map first, then each mismatch with origin/transform/inconsistency/belief-vs-rendered, and finally risky coupling/gaps.

**Data Flow Map**
- Asset browser population: ROM and library items are added by `ROMWorkflowController` via `_load_known_sprite_locations` and `_load_library_sprites`; Mesen captures arrive from `LogWatcher` and get normalized by SMC header in `_add_capture_to_browser`. Each browser item stores a `UserRole` dict with `name/offset/source_type/thumbnail`. `ui/sprite_editor/controllers/rom_workflow_controller.py`, `ui/sprite_editor/views/widgets/sprite_asset_browser.py`
- Selection -> preview: `SpriteAssetBrowser.sprite_selected(offset, source_type)` -> `ROMWorkflowPage` forwards -> `ROMWorkflowController._on_sprite_selected` -> `set_offset` clears `current_tile_data` and requests preview via `SmartPreviewCoordinator`. `ROMWorkflowPage.set_offset` reselects by offset. `ui/sprite_editor/views/widgets/sprite_asset_browser.py`, `ui/sprite_editor/views/workspaces/rom_workflow_page.py`, `ui/sprite_editor/controllers/rom_workflow_controller.py`, `ui/common/smart_preview_coordinator.py`
- Preview -> editor: `PreviewWorkerPool` decompresses, may align offset, emits `actual_offset`; `SmartPreviewCoordinator` forwards; `ROMWorkflowController._on_preview_ready` updates `current_tile_data/current_tile_offset/current_offset` and calls `asset_browser.update_sprite_offset(old, actual)` if needed. `ui/common/preview_worker_pool.py`, `ui/common/smart_preview_coordinator.py`, `ui/sprite_editor/controllers/rom_workflow_controller.py`, `ui/sprite_editor/views/widgets/sprite_asset_browser.py`
- Editor -> canvas/preview: `open_in_editor` renders `current_tile_data` to indexed image via `SpriteRenderer.render_4bpp`, then `EditingController.load_image` updates `ImageModel`; `PixelCanvas` and `PreviewPanel` render off `image_model` + palette. `ui/sprite_editor/controllers/rom_workflow_controller.py`, `ui/sprite_editor/services/sprite_renderer.py`, `ui/sprite_editor/controllers/editing_controller.py`, `ui/sprite_editor/views/widgets/pixel_canvas.py`, `ui/sprite_editor/views/panels/preview_panel.py`
- Thumbnail flow: `ThumbnailWorkerController` drives `BatchThumbnailWorker` (offset hunting + alignment), emits `thumbnail_ready(offset)`; `ROMWorkflowController._on_thumbnail_ready` calls `SpriteAssetBrowser.set_thumbnail`, which updates all items matching that offset. `ui/workers/batch_thumbnail_worker.py`, `ui/sprite_editor/controllers/rom_workflow_controller.py`, `ui/sprite_editor/views/widgets/sprite_asset_browser.py`

**Desync Points (Origin -> Transform/Cache -> Inconsistency -> Belief vs Rendered)**
- Source type is dropped after selection.
  - Origin: `SpriteAssetBrowser` emits `(offset, source_type)`. `ui/sprite_editor/views/widgets/sprite_asset_browser.py`
  - Transform: `ROMWorkflowController._on_sprite_selected` ignores `source_type`, calls `set_offset`. `ui/sprite_editor/controllers/rom_workflow_controller.py`
  - Inconsistency: `ROMWorkflowPage.set_offset` reselects by offset only, so if ROM/Mesen/Library share the offset, selection can flip to the first match (ROM category). `ui/sprite_editor/views/workspaces/rom_workflow_page.py`
  - Belief vs rendered: UI can show a different item than the user chose (category mismatch), while preview/canvas always render ROM data for the offset, not capture/library-specific identity.

- Offset-only identity causes selection and thumbnails to collapse across categories.
  - Origin: Browser items store `offset` and `source_type` but `select_sprite_by_offset` and `set_thumbnail` use only `offset`. `ui/sprite_editor/views/widgets/sprite_asset_browser.py`
  - Transform: `set_thumbnail` updates *all* items with that offset; `select_sprite_by_offset` picks the first match in tree order.
  - Inconsistency: ROM/Mesen/Library entries overwrite each other’s thumbnails and selection state.
  - Belief vs rendered: The asset browser suggests per-category identity, but the system treats offset as the single identity and renders one shared thumbnail/pixel source.

- Thumbnail offset hunting silently changes identity without updating the browser.
  - Origin: `BatchThumbnailWorker._generate_thumbnail` tries `get_offset_candidates` and mutates `request.offset` when alignment succeeds. `ui/workers/batch_thumbnail_worker.py`
  - Transform/cache: Worker emits `thumbnail_ready(adjusted_offset)`. Cache key is `offset:size`. `ui/workers/batch_thumbnail_worker.py`, `ui/common/thumbnail_cache.py`
  - Inconsistency: Asset browser items stay at the original offset unless a preview alignment occurs (only `ROMWorkflowController._on_preview_ready` updates offsets). Thumbnails emitted for the *adjusted* offset may not match any item or may attach to a different item.
  - Belief vs rendered: Browser assumes thumbnails map to the item’s offset; actual thumbnails can reflect a different aligned offset.

- Library thumbnails are overwritten by ROM thumbnails.
  - Origin: `_load_library_sprites` loads stored thumbnails, then queues worker thumbnails for the same offsets. `ui/sprite_editor/controllers/rom_workflow_controller.py`
  - Transform: `SpriteAssetBrowser.set_thumbnail` applies the new pixmap to *all* items with that offset. `ui/sprite_editor/views/widgets/sprite_asset_browser.py`
  - Inconsistency: Library entries lose their saved preview and show ROM/worker output instead.
  - Belief vs rendered: Library items imply “saved sprite preview,” but what is rendered is ROM-derived grayscale.

- Edited canvas vs “current tile data” diverge; library thumbnails/projects can be stale.
  - Origin: `open_in_editor` loads `current_tile_data` (ROM-decompressed) into the editor; edits only update `EditingController.image_model`. `ui/sprite_editor/controllers/rom_workflow_controller.py`, `ui/sprite_editor/controllers/editing_controller.py`
  - Transform/cache: `_generate_library_thumbnail` uses `current_tile_data` if offsets match; `save_sprite_project` writes `current_tile_data`, not `image_model`. `ui/sprite_editor/controllers/rom_workflow_controller.py`
  - Inconsistency: Canvas shows edited pixels, while library thumbnails and saved project tile data can still be the original ROM data.
  - Belief vs rendered: UI implies “save/thumbnail reflects what I see,” but the saved/thumbnail image can be pre-edit ROM pixels.

- Offset normalization and alignment are not propagated to capture sources.
  - Origin: Captures from `LogWatcher` are file offsets; asset browser stores normalized ROM offsets (`normalize_mesen_offset`). `ui/sprite_editor/controllers/rom_workflow_controller.py`
  - Transform: Alignment can further adjust offsets during preview (`update_sprite_offset`), but the log watcher capture list and other UI surfaces keep original offsets.
  - Inconsistency: Asset browser shows normalized/aligned offsets, while capture lists keep file offsets; selecting from other panels can reintroduce the pre-normalized/pre-aligned offset.
  - Belief vs rendered: Browser implies the capture’s offset is authoritative; actual preview/canvas may be driven by a different aligned ROM offset.

- Local file items exist in the browser but have no editor integration.
  - Origin: `SpriteAssetBrowser.add_local_file` stores `path` without `offset`. `ui/sprite_editor/views/widgets/sprite_asset_browser.py`
  - Transform: `_on_selection_changed` only emits when `offset` exists.
  - Inconsistency: Local files can be listed but never drive preview/editor/canvas.
  - Belief vs rendered: UI suggests selectable assets, but the editor/canvas never updates.

**Risky Patterns / Hidden Coupling / Ambiguous Ownership**
- Offset-only identity is global across ROM/Mesen/Library categories; any thumbnail or selection action implicitly affects all items with the same offset. `ui/sprite_editor/views/widgets/sprite_asset_browser.py`
- Offset alignment is handled in preview flow, but thumbnail alignment is handled in a separate worker without a synchronization path back to the browser offset map. `ui/common/preview_worker_pool.py`, `ui/workers/batch_thumbnail_worker.py`
- There are two asset-browser “models”: `SpriteAssetBrowser` stores the live state in item `UserRole`, while `AssetBrowserController` maintains its own `_assets` map and persistence, but it is not wired into `ROMWorkflowController`. This is an ambiguous source of truth if both are ever used. `ui/sprite_editor/views/widgets/sprite_asset_browser.py`, `ui/sprite_editor/controllers/asset_browser_controller.py`, `ui/sprite_editor/controllers/rom_workflow_controller.py`
