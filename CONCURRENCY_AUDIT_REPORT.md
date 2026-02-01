# Concurrency and Threading Audit Report: SpritePal

This audit identified 8 distinct threading hazards, ranging from high-probability data corruption races to UI-blocking violations. The most critical (P0) issue involves a race condition in the singleton `HALProcessPool` that affects parallel thumbnail generation.

---

## 1. Prioritized Hazards

| Priority | Issue | Files | Realistic Failure Mode |
| :--- | :--- | :--- | :--- |
| **P0** | **HAL Pool Result Attribution Race** | `core/hal_compression.py` | **Hang / Corrupt Thumbnails:** Multiple threads waiting on the same `HALProcessPool` singleton results queue can receive each other's data or discard valid results as "stale," leading to UI hangs or thumbnails showing the wrong sprite. |
| **P1** | **Global Extractor State Corruption** | `core/managers/core_operations_manager.py` | **Crash / Data Corruption:** `extract_from_vram` (worker thread) and `generate_preview` (UI thread) concurrently mutate the same `VramSpriteExtractor` instance. One operation will overwrite `self.vram_data` mid-way through the other's execution. |
| **P1** | **Shared Palette Manager Race** | `core/managers/core_operations_manager.py` | **Inconsistent UI:** VRAM and ROM extractions use different operation locks but share a single `PaletteManager`. Concurrent extractions will corrupt the internal `palettes` dictionary, causing one or both to emit incorrect palette data. |
| **P1** | **Main Event Loop Blocking** | `ui/main_window.py` | **UI Freeze:** Synchronous VRAM/ROM processing (including subprocess decompression) occurs directly on the UI thread in `_update_preview_with_offset`. This causes the application to stutter or freeze for 100-500ms when moving the offset slider. |
| **P1** | **Injection Signal Connection Leak** | `ui/services/injection_workflow_coordinator.py` | **Duplicate Signal Delivery:** Every call to `start_injection` reconnects to the manager's signals without disconnecting previous ones. After 10 injections, one progress message will trigger 10 UI updates, degrading performance over time. |
| **P2** | **Worker Reference Overwrite** | `ui/services/extraction_workflow_coordinator.py` | **Resource Leak:** Starting a new extraction before the old one finishes orphans the old `QThread`. The orphaned worker continues to run and emit signals to potentially deleted objects. |
| **P2** | **UI-Thread Violation in Cleanup** | `core/services/worker_lifecycle.py` | **Segfault/Crash:** `WorkerManager.cleanup_all` calls `app.processEvents()` from the calling thread. If called from a test runner or background thread, this violates Qt's thread-affinity rules. |
| **P2** | **Non-Atomic Lazy Initialization** | `core/rom_extractor.py` | **Double Initialization:** Properties like `hal_compressor` use `if self._x is None: self._x = X()` without locks. Concurrent first-time access from `BatchThumbnailWorker` threads can instantiate multiple heavy compressor pools. |

---

## 2. Detailed Findings & Suggested Fixes

### [P0] HAL Pool Result Attribution Race
- **File:** `core/hal_compression.py` (`HALProcessPool.submit_request` and `submit_batch`)
- **Hazard:** The singleton pool uses one `_result_queue` for all threads. `submit_request` performs a simple `get()` on the queue. If Thread A and Thread B both have pending requests, Thread A might "steal" Thread B's result. In `submit_batch`, results with mismatched `batch_id` are simply discarded, meaning results for other threads are lost forever.
- **Smallest Fix:** In `HALProcessPool`, implement a result dispatcher. Use a single background thread to read from `_result_queue` and push results into a thread-safe map of `request_id -> threading.Event/Future`.
- **Better Architecture:** Replace the custom queue-based pool with `concurrent.futures.ProcessPoolExecutor` or `multiprocessing.Pool`, which handle result correlation internally.

### [P1] Extractor/Palette State Corruption
- **File:** `core/managers/core_operations_manager.py`
- **Hazard:** `CoreOperationsManager` holds single instances of `VramSpriteExtractor` and `PaletteManager`. Both classes maintain internal state (buffers, result dicts) during operation. Because the UI thread calls `generate_preview` (via slider) while a background worker may be calling `extract_from_vram`, the internal buffers will be overwritten mid-operation.
- **Smallest Fix:** Use a dedicated `threading.Lock` within `CoreOperationsManager` that wraps all calls to `self._sprite_extractor` and `self._palette_manager`.
- **Better Architecture:** Make extractors stateless (pass the file data into the extraction methods) or instantiate fresh ones per worker.

### [P1] Main Event Loop Blocking
- **File:** `core/services/preview_generator.py`
- **Hazard:** `PreviewGenerator.request_debounced_preview` fires a timer that executes the preview generation synchronously on the main thread. While debouncing reduces frequency, a single generation still involves file I/O and HAL decompression, which blocks UI responsiveness.
- **Smallest Fix:** Move the actual generation logic into a `QThread` (following the `AsyncPreviewService` pattern already used elsewhere in the app).
- **Better Architecture:** Unify the preview stack to use a shared background worker pool for all preview requests (sliders, dialogs, and gallery).

---

## 3. Invariants Checklist

1.  **Thread Affinity:** Never create or access `QPixmap`, `QIcon`, or `QWidget` outside the Main UI thread. Background threads must use `QImage`.
2.  **Manager Atomicity:** All managers in `core/` must be thread-safe for concurrent method calls. Use `threading.RLock` for all public-facing methods that access or mutate internal state.
3.  **Signal Hygiene:** Signal coordinators must ensure only one connection exists per lifetime. Use `disconnect()` before `connect()` or manage connections via `QMetaObject.Connection`.
4.  **Worker Lifecycle:** Only `WorkerManager` should trigger thread destruction. Workers must regularly poll `isInterruptionRequested()` during tight loops (e.g., tile decoding).
5.  **Lazy Property Safety:** Lazy initialization of heavy objects (compressors, caches) must be protected by a lock to prevent multiple instantiations.
