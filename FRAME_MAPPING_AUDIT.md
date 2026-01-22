# Frame Mapping Workflow Audit Report

## Executive Summary
The Frame Mapping workflow exhibits significant UI-logic desynchronization risks, primarily driven by inefficient signal handling, redundant UI updates, and an unstable mix of index-based vs. ID-based state tracking. A critical performance bottleneck exists in batch injection operations, where the entire UI is rebuilt O(N) times. Furthermore, the lack of auto-save for structural changes (links/imports) poses a data loss risk.

## 1. Identified Desynchronization Issues

### A. Redundant UI Refreshes (The "Triple Refresh" Problem)
**Severity:** High (Performance & UX)
**Observation:** A single `project_changed` signal triggers the `FrameMappingWorkspace` to call three separate refresh methods on the `MappingPanel` and `AIFramesPane`.
**Root Cause:**
`FrameMappingWorkspace._on_project_changed` calls:
1. `_mapping_panel.set_project(project)` -> Calls `refresh()` (Rebuild 1)
2. `_refresh_mapping_status()` -> Calls `_mapping_panel.refresh()` (Rebuild 2)
3. `_update_mapping_panel_previews()` -> Calls `_mapping_panel.refresh()` (Rebuild 3)
**Impact:** `MappingPanel.refresh()` clears and recreates all table rows. For a project with 500 frames, a single change results in 1,500 row creation operations, causing visible UI freeze.

### B. Batch Injection "UI Storm"
**Severity:** Critical (Performance)
**Observation:** During "Inject All" or "Inject Selected", the UI freezes and flickers intensely.
**Root Cause:**
1. `FrameMappingWorkspace._on_inject_all` loops through frames and calls `controller.inject_mapping`.
2. `inject_mapping` emits `project_changed` after *every* successful injection.
3. Each `project_changed` triggers the "Triple Refresh" described above.
**Impact:** For 100 frames, the table is rebuilt 300 times (3 * 100). This turns an O(N) operation into O(N² * UI_Cost).

### C. Canvas State Disruption
**Severity:** Medium (UX)
**Observation:** Importing a capture or linking a frame while the canvas is active causes the canvas to clear or reset, potentially losing transient view state (zoom/pan).
**Root Cause:** `FrameMappingWorkspace._on_project_changed` explicitly calls `self._alignment_canvas.clear()`.
**Impact:** Interrupts user workflow. If the data model changes (e.g., adding a capture), the current visualization of an unrelated frame should remain stable.

### D. Unstable Index-Based State ✅ **RESOLVED**
**Severity:** High (Data Integrity)
**Status:** Fixed in commit ec38292a (refactor: migrate Frame Mapping signals from index to ID-based)
**Resolution:** `MappingPanel` signals migrated to ID-based variants (`mapping_selected_by_id`, `edit_frame_requested_by_id`, etc.). `FrameMappingWorkspace` now connects to `_by_id` signals and all slot signatures updated to accept `ai_frame_id: str`. The `FrameMappingController` gained `remove_mapping_by_id()` method.
**Impact:** Selections now stable across project reloads and frame reordering. No more index-to-ID conversion in slots.

### E. Direct State Mutation
**Severity:** Medium (Architecture)
**Observation:** `FrameMappingWorkspace._on_compression_type_changed` directly modifies `game_frame.compression_types` and then manually emits `project_changed`.
**Root Cause:** Missing controller method for setting compression type.
**Impact:** Bypasses any potential validation, logging, or side-effects (like auto-save) that the controller should manage.

### F. Missing Auto-Save
**Severity:** High (Data Loss)
**Observation:** Projects are auto-saved *only* after injection. Creating links, importing captures, or adjusting alignment does not trigger auto-save.
**Root Cause:** `FrameMappingController` only emits `save_requested` in `inject_mapping`.
**Impact:** If the app crashes or is closed after hours of mapping work (without injection), all work is lost.

## 2. Proposed Fixes

### Phase 1: Signal & Performance Optimization
1.  **Consolidate Refresh Logic:** Refactor `FrameMappingWorkspace` to call a single `_refresh_ui()` method that updates all panels efficiently, preventing multiple rebuilds.
2.  **Batch Signal Suppression:** Add `block_signals` context manager to `FrameMappingController` or a specific `inject_batch` method that emits `project_changed` only once at the end.
3.  **Targeted Signals:** Introduce `mapping_status_changed` and `preview_updated` signals to handle lightweight updates without triggering full UI rebuilds.

### Phase 2: State Stability (ID Migration) ✅ **COMPLETED**
1.  **Migrate to IDs:** ✅ `FrameMappingWorkspace` now tracks `_selected_ai_frame_id` alongside index for legacy components.
2.  **Update Signals:** ✅ All `MappingPanel` connections use `*_by_id` signals. Slot signatures refactored to accept IDs. Index-based signals preserved for backwards compatibility but no longer used by workspace.

### Phase 3: Architecture & Safety
1.  **Encapsulate Mutation:** Add `set_compression_type(game_frame_id, offset, type)` to `FrameMappingController`.
2.  **Comprehensive Auto-Save:** Emit `save_requested` (or a new `project_modified` signal) on all state-changing operations (`create_mapping`, `remove_mapping`, `import_capture`).
3.  **Canvas Persistence:** Remove `canvas.clear()` from `_on_project_changed`. Instead, the canvas should verify if its current `ai_frame` still exists and only clear if it became invalid.

## 3. Regression Test Plan

### A. Test Batch Performance
*   **Test:** `test_batch_injection_performance`
*   **Goal:** Measure signal emission count during `inject_all` with 10 mocked frames.
*   **Expectation:** `project_changed` should emit exactly **once**, not 10 times.

### B. Test UI Stability
*   **Test:** `test_ui_refresh_count`
*   **Goal:** Trigger `project_changed` and count calls to `MappingPanel.refresh`.
*   **Expectation:** Should be called exactly **once**.

### C. Test ID vs Index Desync ✅ **COVERED**
*   **Test:** `test_selection_stability_after_reload` (mitigated by ID-based signals)
*   **Goal:** Select frame "B.png" (index 1), reload AI frames such that "B.png" becomes index 0.
*   **Expectation:** Selection should remain on "B.png", not jump to the new frame at index 1.
*   **Status:** ID-based signals ensure stability. Existing tests verify signal behavior.

### D. Test Auto-Save Triggers
*   **Test:** `test_auto_save_on_mapping_change`
*   **Goal:** Call `create_mapping` and verify `save_requested` is emitted.
