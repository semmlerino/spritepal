# Forensic Investigation Report: Subsystem Desynchronization

## Executive Summary
Multiple confirmable desynchronization mechanisms exist where the application relies on stale, cached data (`current_tile_data` from ROM) instead of the active editing state (`image_model` from Editor). This causes data loss in specific workflows like **Arrangement** and **Library Saving**.

## 1. Data Flow & Ownership Map

| Subsystem | Source of Truth | Identifiers | Invalidated By |
| :--- | :--- | :--- | :--- |
| **Asset Browser** | `AssetBrowserController._assets` (Metadata only) | `(offset, source_type)` | User adds/removes/renames. **Does not track edits.** |
| **ROM Workflow** | `ROMWorkflowController.current_tile_data` (Raw ROM bytes) | `current_offset` | `set_offset()` (Navigation). |
| **Sprite Editor** | `EditingController.image_model.data` (NumPy Array) | None (Implicit active state) | `load_image()`, `import_image()`, Tools (Draw/Fill). |
| **Canvas** | `EditingController.image_model.data` (via `PixelCanvas`) | None | `imageChanged` signal. |
| **Preview** | `SmartPreviewCoordinator._cache` (LRU) | `(rom_path, offset)` | `rom_path` change (save), or explicit invalidate. |

## 2. Confirmed Desync Mechanisms

### A. The "Ghost Edit" Bug (Arrangement Workflow)
**Severity:** Critical (Data Loss)
**Mechanism:** The Arrangement Dialog logic fetches data from the *stale* ROM cache, ignoring active edits.
**Code Path:**
1. User loads sprite, draws pixels (modifies `EditingController`).
2. User clicks "Arrange Tiles".
3. `ROMWorkflowController.show_arrangement_dialog` executes:
   ```python
   # BUG: Reads stale ROM bytes, ignores Editor pixels
   renderer.render_4bpp(self.current_tile_data, ...)
   ```
4. Dialog opens showing the *original* sprite (edits missing).
5. User applies arrangement.
6. Editor reloads with arranged tiles, **permanently overwriting** previous pixel edits with the original ROM data.

### B. The "Split Personality" Bug (Save to Library)
**Severity:** High (Data Corruption/Inconsistency)
**Mechanism:** Saving to Library mixes the *current* palette with *stale* pixels.
**Code Path:**
1. User loads sprite, draws pixels (modifies `EditingController`).
2. User clicks "Save to Library".
3. `ROMWorkflowController._on_save_to_library` executes:
   ```python
   # Fetches active palette (Correct)
   palette_colors = self._editing_controller.get_current_colors()
   
   # BUG: Fetches stale ROM bytes for thumbnail/storage
   pil_thumbnail = self._generate_library_thumbnail(offset) 
   # ... uses self.current_tile_data
   ```
4. Library entry is created with the new palette but the old image.

### C. Palette Source Amnesia
**Severity:** Medium (UI State Desync)
**Mechanism:** Loading a sprite clears the palette source memory, creating a race condition for restoration.
**Code Path:**
1. `ROMWorkflowController.open_in_editor` calls `load_image(data, palette)`.
2. `EditingController.load_image` calls `set_palette(...)` without source info, effectively setting `_current_palette_source = None`.
3. `ROMWorkflowController` attempts to restore the source *after* loading.
4. **Desync:** If the restoration logic (e.g., matching a ROM palette) fails or defaults, the `EditingController` remains in a state where it has colors but "doesn't know where they came from." The UI Palette Selector becomes blank or falls back to generic "Custom".

## 3. Danger Zones

1.  **`ROMWorkflowController.current_tile_data`**: This variable is **ReadOnly** regarding the editor. It represents "What is on disk", not "What is on screen". Any feature using this to process the "current sprite" (except for Revert/Reset functions) is buggy by definition.
2.  **`AssetBrowser` Selection vs. Editor State**: The Asset Browser has no concept of "Unsaved Changes". If a user navigates away, `ROMWorkflowController` checks for unsaved changes, but the Asset Browser's *selection highlight* might update before the navigation is confirmed/cancelled, leading to a visual desync where the list shows Item B selected but Item A is still in the editor.
3.  **Preview Latency**: The `SmartPreviewCoordinator` handles race conditions well via `_pending_open_in_editor`, but relies on `actual_offset` matching. Rapid-fire selection changes rely on the event loop ordering to prevent the wrong sprite from loading.

## 4. Recommendations for Fixes

1.  **Arrangement Fix**: Update `show_arrangement_dialog` to request `self._editing_controller.get_image_data()` instead of using `self.current_tile_data`.
2.  **Library Fix**: Update `_generate_library_thumbnail` (or the save method) to use `self._editing_controller.get_image_data()` when `offset == current_offset`.
3.  **Palette Fix**: Refactor `load_image` to accept an optional `source_info` tuple, or ensure `set_palette_source` is strictly called *immediately* after load with atomic certainty.
