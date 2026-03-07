Here’s the end‑to‑end trace and where identity/offset mismatches are introduced, with the exact transformation points and implicit assumptions.

**Flow Trace (Mesen → extraction → editor → asset browser)**
- **Mesen capture ingestion**: `core/mesen_integration/log_watcher.py` parses "FILE OFFSET" and stores it as `CapturedOffset.offset` (FILE offset, immutable identity). `OFFSET_PATTERN` confirms FILE offset parsing.
- **ROM Extraction panel (Recent captures)**: `ui/components/panels/recent_captures_widget.py` converts FILE → ROM offset via `_normalize_offset` using `_smc_offset`. It stores **both** `file_offset` and `rom_offset` in item data; list display text shows FILE offset, selection uses ROM offset. Thumbnails are requested by ROM offset.
- **ROM Extraction panel → editor**: `ui/rom_extraction_panel.py` emits `open_in_sprite_editor` with ROM offset. `ui/main_window.py:_on_open_in_sprite_editor` treats it as ROM offset and looks up a capture by converting ROM→FILE (`log_watcher.get_capture_by_rom_offset()`).
- **Sprite editor**: `ui/workspaces/sprite_editor_workspace.py:jump_to_offset` uses ROM offset, calls `rom_workflow_controller.ensure_and_select_capture` then `set_offset`.
- **Preview/extraction**: `ui/common/preview_worker_pool.py` strips SMC header from ROM data (so **expects ROM offsets**), then does offset hunting via `core/offset_hunting.get_offset_candidates`. It may change the “actual_offset” it emits.
- **Offset adjustment propagation**: `ui/sprite_editor/controllers/rom_workflow_controller.py:_on_preview_ready` updates `current_offset`, updates asset browser items via `update_sprite_offset`, and emits `capture_offset_adjusted` (ROM offsets).
- **Asset browser**: `ui/sprite_editor/views/widgets/sprite_asset_browser.py` stores **only** ROM offsets in item data; updates are by offset only. Thumbnails are keyed by offset (and optional source_type).

**Offset Transformations & Identity Tracking**
- **FILE offset**: canonical identity from Mesen (log watcher). Stored in `CapturedOffset.offset` and in Recent Captures item data (`file_offset`).
- **ROM offset**: computed by subtracting SMC header offset. This is what all preview/extraction/thumbnail paths expect.
  - Recent captures normalization: `ui/components/panels/recent_captures_widget.py:_normalize_offset`.
  - Sprite editor normalization: `ui/sprite_editor/controllers/rom_workflow_controller.py:normalize_mesen_offset`.
- **Alignment adjustment**: preview worker may shift to a nearby offset. When that happens:
  - ROMWorkflowController updates asset browser items (`update_sprite_offset`) and emits `capture_offset_adjusted` to Recent Captures.
  - **FILE offset identity is preserved in Recent Captures, but not stored anywhere in Asset Browser.**

**Where the mismatch is introduced (primary)**
1) **Thumbnail vs preview offset hunting diverge**  
   - Preview worker (editor path) **trusts the primary requested offset** if HAL decompression succeeds, even if content is mostly black. See `ui/common/preview_worker_pool.py` — it accepts primary offset without `has_nonzero_content` filtering.
   - Thumbnail worker (`ui/workers/batch_thumbnail_worker.py`) uses `get_offset_candidates` and accepts the **first offset with nonzero content**, with **no primary‑offset trust logic**. That means thumbnails can render from a *different* nearby offset than the editor preview, especially for mostly‑black sprites.
   - Result: **asset browser or recent capture thumbnail can show a different sprite than the editor preview**, even when the offset is “the same”.

2) **Alignment adjustment + resync causes old offset to reappear**
   - After preview alignment, asset browser items are updated to `actual_offset`, but log watcher still stores the original FILE offset.
   - Later `ROMWorkflowController.sync_captures_from_log_watcher()` re‑normalizes the original FILE offset and calls `_add_capture_to_browser`, which uses the **old ROM offset**.
   - `SpriteAssetBrowser.has_mesen_capture` dedupes by offset+frame. Since the adjusted item now has a different offset, the old offset is treated as a *new* capture. This reintroduces the pre‑alignment offset in the browser and **creates divergent identities for the same capture**.  
   Files: `ui/sprite_editor/controllers/rom_workflow_controller.py`, `ui/sprite_editor/views/widgets/sprite_asset_browser.py`.

3) **Recent Captures thumbnails aren’t re-requested after alignment**
   - `RecentCapturesWidget.update_capture_offset` updates ROM offset fields and display, but does **not** invalidate or requeue thumbnails.
   - If the thumbnail was generated for the old offset, the item now **shows the new offset but retains the old thumbnail**.  
   Files: `ui/components/panels/recent_captures_widget.py`, `ui/rom_extraction_panel.py`.

4) **Frame identity lost when selecting/syncing captures**
   - Asset browser supports multiple frames at the same offset, but:
     - `SpriteEditorWorkspace.jump_to_offset` → `ensure_and_select_capture` uses **offset only**, not frame.
     - `SpriteAssetBrowser.ensure_mesen_capture` ignores frame in its existence check.
     - `SpriteAssetBrowser.select_sprite_by_offset` picks the **first** item matching offset.
   - If multiple frames share the same offset, selection and thumbnails are **ambiguous**, and the UI may show the “wrong” frame’s thumbnail/name relative to the selected capture.  
   Files: `ui/workspaces/sprite_editor_workspace.py`, `ui/sprite_editor/views/widgets/sprite_asset_browser.py`.

**Implicit assumptions / hidden remaps**
- **SMC header offset consistency**  
  Recent Captures uses `rom_extractor.rom_injector.header.header_offset` (`ui/rom_extraction_panel.py`), while editor uses `ROMValidator.validate_rom_header` (`ui/sprite_editor/controllers/rom_workflow_controller.py`). Assumes these are identical; if not, ROM offset mapping diverges.
- **Backward-compat renormalization**  
  `RecentCapturesWidget.set_smc_offset` falls back if `file_offset` missing by “denormalizing” with old SMC offset. This is an approximation and can permanently mis-map legacy captures.
- **Display text vs data**  
  Recent Captures displays FILE offsets but selection uses ROM offsets. Asset browser updates `data["offset"]` but only rewrites display text if it contains the old hex string. If the name was custom, UI text can show an old offset while the underlying offset changed.
- **Thumbnail cache identity**  
  Thumbnails are cached by offset only, not by frame. Multiple captures at the same offset will share thumbnails, even if frames are different.

**Net effect: where the mismatch shows up**
- **Mesen capture list**: offset display shows FILE offset; preview uses ROM offset; after alignment, item offset updates but thumbnail may remain from old offset.
- **Sprite editor preview**: uses ROM offset; may auto‑adjust to actual_offset; trusts primary offset even for mostly‑black sprites.
- **Asset browser**: items can be updated to actual_offset, but resyncing from log watcher reintroduces old offsets; thumbnails may come from nearby offsets due to different hunting logic; frame‑specific identity is not respected in selection or thumbnails.

If you want, I can follow up by mapping the exact signal sequences for a specific repro case (with offsets + frames) to show which branch is taken in each widget.
