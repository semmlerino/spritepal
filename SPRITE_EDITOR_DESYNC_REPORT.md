# Sprite Editor Desynchronization Diagnostic Report
Date: Friday, January 16, 2026

## **Overview**
This report details the investigation into desynchronization issues between the thumbnail previews, editor rendering, and underlying ROM offsets in SpritePal. The desync arises from a combination of stale state management, incomplete propagation of offset alignment adjustments, and inconsistencies in rendering logic across components.

---

## **Component and Signal Map**

### **1. Data Flow Sequence**
1.  **Selection**: User selects an offset (e.g., `0x1234`) in the `SpriteAssetBrowser`.
2.  **Request**: `ROMWorkflowController` calls `set_offset(0x1234)`, clearing its `current_tile_data` and triggering:
    *   `SmartPreviewCoordinator` (for real-time editor preview).
    *   `ThumbnailWorkerController` (for asset browser thumbnails).
3.  **Extraction & Alignment**: 
    *   `PooledPreviewWorker` (coordinator side) and `BatchThumbnailWorker` (thumbnail side) both use `get_offset_candidates` to find valid HAL headers.
    *   They may align `0x1234` to an actual header offset like `0x1230`.
4.  **Signal Propagation**:
    *   **Coordinator**: Emits `preview_ready` with `actual_offset = 0x1230`.
    *   **Controller**: Updates its `current_offset` to `0x1230` and calls `asset_browser.update_sprite_offset(0x1234, 0x1230)`.
    *   **Thumbnail Worker**: Emits `thumbnail_ready` for the *requested* offset `0x1234`.
5.  **Rendering**: `ROMWorkflowController.open_in_editor()` uses the aligned `current_tile_data` and a fixed 16-tile-wide grid.

---

## **Failure Modes and Root Causes**

### **1. Stale Thumbnail after Save (Deterministic)**
*   **Component**: `BatchThumbnailWorker` / `ThumbnailWorkerController`
*   **Root Cause**: The worker is initialized with a `rom_path` at startup. When `ROMWorkflowController` saves a modified ROM and updates its own `rom_path` to the new filename (e.g., `game_modified.sfc`), the thumbnail worker is never updated. It continues reading from the original file, while the editor shows the modified data.

### **2. Identity/Data Mismatch (State-Dependent)**
*   **Component**: `ThumbnailCache`
*   **Root Cause**: The cache key is generated as `offset:size`. This key lacks ROM identity (filename, size, or mtime). If a user switches ROMs or modifies a ROM, the cache returns thumbnails from previous states/sessions for matching offsets.

### **3. Browser UI Partial Update (Deterministic)**
*   **Component**: `SpriteAssetBrowser.update_sprite_offset`
*   **Root Cause**: This method returns `True` and exits after finding the first matching item. If a sprite exists in multiple categories (e.g., "ROM Sprites" and "Mesen2 Captures"), only one item is updated to the aligned offset. The other item remains at the old offset, and selecting it causes the editor to "jump" back or fail to find data.

### **4. Missing Thumbnails (Alignment-Induced)**
*   **Component**: `BatchThumbnailWorker`
*   **Root Cause**: The worker emits signals using the *requested* offset. If the `SpriteAssetBrowser` has already processed an alignment correction from the `SmartPreviewCoordinator`, the item's offset has changed to the *aligned* value. The thumbnail signal for the *requested* offset finds no match in the UI tree, leaving the item with a placeholder.

### **5. Truncation Identity Mismatch (Deterministic)**
*   **Component**: `SmartPreviewCoordinator`
*   **Root Cause**: Manual browsing previews are capped at 4KB (128 tiles) for performance. `BatchThumbnailWorker` generates full thumbnails. For sprites larger than 4KB, the thumbnail and the editor preview represent different portions of the data until the user explicitly "Opens in Editor" (which triggers a full decompression).

### **6. Visual Layout Desync (Deterministic)**
*   **Component**: `BatchThumbnailWorker` vs `SpriteRenderer`
*   **Root Cause**: 
    *   `BatchThumbnailWorker` calculates width as `min(16, tile_count)`.
    *   `SpriteRenderer` (used by editor/preview) uses a fixed 16-tile width.
    *   Small sprites (e.g., 4 tiles) appear as a 2x2 grid in the thumbnail but a 4x1 row in the editor.

### **7. Identity Gap (Mesen Integration)**
*   **Component**: `ROMWorkflowController._validate_capture_rom_match`
*   **Root Cause**: The logic explicitly allows captures without checksums (legacy format) to be added to any ROM. This allows stale captures from different games to persist and appear in the asset browser of the current session.

### **8. Non-Functional Preloading (Optimization)**
*   **Component**: `SmartPreviewCoordinator`
*   **Root Cause**: Background preloads use negative `request_id`s. However, `_on_worker_preview_ready` ignores any request where `request_id < self._request_counter`. Since `_request_counter` is non-negative and increments, all background preloads are ignored by the result handler and never cached.

---

## **Conclusion**
The **`BatchThumbnailWorker`** is the primary source of truth divergence. It operates in an isolated state that is not synchronized when the main application state (ROM path) changes. This is compounded by the **`SpriteAssetBrowser`**'s failure to handle multiple instances of the same offset during alignment updates, leading to a fragmented UI state where different items representing the same sprite have different data bindings.
