# Frame Mapping UI–Logic Desynchronization Audit Report

**Date:** Monday, January 26, 2026
**Status:** Findings Identified & Fixes Recommended
**Target:** Frame Mapping Workflow (UI-Logic Synchronization)

## Executive Summary
The Frame Mapping workflow distributes state between the `FrameMappingWorkspace` (controller-like UI container) and its sub-panes (`AIFramesPane`, `CapturesLibraryPane`). A critical desynchronization occurs when **filtering** (e.g., "Unmapped Only" or search) hides the currently selected item. The view correctly clears its visual selection, but fails to notify the workspace. Consequently, the workspace retains a **stale selection ID**, allowing users to execute actions (like "Map Selected" or "Inject") on a hidden, unintended frame.

---

## UI Reflection Contract Inventory

| UI Surface | State (Source of Truth) | Owning Component | Public Signal/Getter | Expected UI Reflection |
| :--- | :--- | :--- | :--- | :--- |
| **AI Frames List** | `_ai_frames` + Selection | `AIFramesPane` | `ai_frame_selected` | Highlight row, enable/disable "Map" button |
| **Captures List** | `_game_frames` + Selection | `CapturesLibraryPane` | `game_frame_selected` | Highlight row, enable/disable "Map" button |
| **Mappings Drawer** | `_project.mappings` | `MappingPanel` | `mapping_selected` | Highlight row, show alignment values |
| **Workbench Canvas** | `_state.selected_ai_frame_id` (Stale) | `FrameMappingWorkspace` | N/A (Internal Update) | Render frame, show alignment handles |
| **Map Button** | `_state.selected_*_id` (Stale) | `FrameMappingWorkspace` | N/A (Internal Update) | Enabled/Disabled state |

---

## Findings

### 1. Stale Selection State on Filtering (Critical)

**1) Source of Truth**
*   **Owner**: `AIFramesPane` (View)
*   **State**: The currently selected row index/ID.
*   **Signal**: `ai_frame_selected(str)`

**2) Expected UI Reflection**
*   When a filter (e.g., "Unmapped") hides the selected frame, the selection should be cleared.
*   The `FrameMappingWorkspace` should receive `ai_frame_selected("")`.
*   The Canvas should clear.
*   The "Map Selected" button should be disabled.

**3) Desynchronization Classification**
*   **Failure Mode**: Missing Connection / Stale UI
*   **Impact**: **High**. Users can accidentally modify or map a hidden frame.
*   **Timeline**:
    1.  T0: User selects Frame A (Mapped).
    2.  T1: User enables "Unmapped" filter.
    3.  T2: `AIFramesPane` rebuilds list, Frame A is excluded. Selection is visually cleared.
    4.  T3: **FAILURE**: `AIFramesPane` does *not* emit `ai_frame_selected("")`.
    5.  T4: `FrameMappingWorkspace` retains Frame A as `selected_ai_frame_id`.
    6.  T5: "Map Selected" button remains ENABLED. Canvas still shows Frame A.

**4) Evidence and Test Coverage**
*   **File**: `ui/frame_mapping/views/ai_frames_pane.py`
*   **Method**: `_refresh_list`
*   **Code Path**: Selection is cleared visually via `self._list.setCurrentRow(-1)` but no signal is emitted to the workspace.
*   **Existing Tests**: Logic-only tests cover unmapped selection, but UI-integration tests for filtering are missing.

**5) Recommended Fix**
Modify `ui/frame_mapping/views/ai_frames_pane.py` in `_refresh_list` to emit an empty string when the previously selected ID is no longer visible in the filtered list.

**6) Test Specification**
*   **Observable Contract**: When the selected AI frame is hidden by a filter, the workspace selection state must be cleared.
*   **Reproduction**: 
    1. Select a mapped frame.
    2. Toggle "Unmapped Only" filter.
    3. Assert `workspace._state.selected_ai_frame_id` is `None` and `workspace._map_button.isEnabled()` is `False`.

---

### 2. WorkspaceStateManager Ambiguity (Architectural)

**1) Source of Truth**
*   **Owner**: `WorkspaceStateManager` claims to be a cache.
*   **Reality**: `FrameMappingWorkspace` treats it as the authoritative source without verifying against views.

**2) Expected UI Reflection**
*   Workspace should treat the View selection as the Source of Truth, or the Manager must be strictly kept in sync via fixed signals (see Finding #1).

**3) Desynchronization Classification**
*   **Failure Mode**: UI reflects internal state instead of public contract.
*   **Impact**: **Medium**. Causes "split-brain" where the UI looks correct but internal state is stale.

**4) Recommended Fix**
Update `FrameMappingWorkspace._get_selected_ai_frame_id` to query `self._ai_frames_pane.get_selected_id()` first, treating `_state` as a fallback.

---

## Remediation Plan

1.  **Fix AIFramesPane**: Implement signal emission for lost selection in `_refresh_list`.
2.  **Verify CapturesLibraryPane**: Perform a similar check on the captures pane to ensure consistency.
3.  **Unified State Access**: Refactor `FrameMappingWorkspace` helper methods to prioritize Pane state over cached `_state`.
4.  **Add Regression Test**: Implement the filtering test specification in `tests/ui/frame_mapping/test_workspace_selection.py`.
