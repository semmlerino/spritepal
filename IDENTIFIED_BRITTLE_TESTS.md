# Identified Brittle Tests Report

This report identifies tests in the `spritepal` codebase that are considered "brittle" because they assert internal implementation details, encode flawed behavior, or are too tightly coupled to the system's internal structure.

## Summary of Findings

| Test File | Category | Description of Brittleness |
| :--- | :--- | :--- |
| `tests/integration/test_gallery_window_integration.py` | **Internal Implementation / Private Access** | Drives the entire test workflow by calling private methods (e.g., `_set_rom_file`, `_start_scan`, `_on_sprite_found`, `_on_scan_finished`) instead of using public APIs or simulating UI interactions. |
| `tests/ui/frame_mapping/views/test_workbench_canvas_auto_align_bug.py` | **Bug Encoding / Private Access** | Specifically encodes fixed bug behaviors and relies heavily on private widget attributes (e.g., `_auto_align_btn`, `_ai_image`, `_status_label`) to verify the fix. |
| `tests/ui/frame_mapping/test_workflow_fixes.py` | **Implementation Coupling / Over-Mocking** | Monkeypatches internal methods (e.g., `panel.refresh`) to count calls and directly accesses private state objects (e.g., `controller._project`, `workspace._state.selected_game_id`). |
| `tests/ui/components/test_paged_tile_view_dialog.py` | **Internal State / Coupling** | Employs "test-only" public methods in the implementation (e.g., `is_cache_cleared`, `simulate_tile_selection`) that exist solely to allow tests to probe private internal state like `self._tile_view._cache`. |
| `tests/integration/test_base_manager.py` | **Internal Implementation** | Directly invokes and asserts results from private lifecycle and error handling methods (e.g., `_handle_error`, `_handle_warning`, `_update_progress`). |
| `tests/ui/frame_mapping/views/test_workbench_canvas_preview.py` | **Implementation Coupling** | Asserts the existence and active state of private UI controls and timers (e.g., `_preview_checkbox`, `_preview_timer`) rather than verifying the resulting visual output. |

## Detailed Analysis and Criteria

### 1. Private Member Access (`._`)
Many tests reach into objects and widgets to assert private state or trigger internal handlers.
- **Example:** `tests/integration/test_gallery_window_integration.py` calls `window._start_scan()` directly instead of simulating a button click or using a public method.
- **Impact:** Renaming private variables or refactoring internal methods will break these tests even if the external behavior remains correct.

### 2. Bug Encoding
Tests that are written to verify a specific bug fix often encode the implementation detail of that fix.
- **Example:** `tests/ui/frame_mapping/views/test_workbench_canvas_auto_align_bug.py` checks if a specific internal button is disabled.
- **Impact:** If the UI is redesigned (e.g., the button is replaced by a menu item or an automatic process), the test will fail.

### 3. Implementation Coupling & Over-Mocking
Tests that verify *how* a result is achieved rather than *what* the result is.
- **Example:** `tests/ui/frame_mapping/test_workflow_fixes.py` monkeypatches `panel.refresh` to assert it is called exactly once.
- **Impact:** Optimizing the code to refresh more or less frequently (while still maintaining correctness) will cause false positives in the test suite.

### 4. "Test-Only" Public Methods
The codebase contains methods specifically added to classes to support testing of internal state.
- **Example:** `PagedTileViewDialog.is_cache_cleared()` and `simulate_tile_selection()`.
- **Impact:** This creates a maintenance burden where production code is "polluted" with testing hooks, and tests become dependent on these hooks rather than observable behavior.

## Recommendations for Improvement

1. **Interact via Public API:** Use `qtbot` to simulate user actions (clicks, key presses) or use public methods and properties.
2. **Assert Observable Outcomes:** Instead of checking `_is_timer_active`, wait for the expected signal or visual change in the UI.
3. **Use Fakes instead of Complex Mocks:** For internal managers, use lightweight "fake" implementations that exhibit real behavior rather than mocking specific method call counts.
4. **Remove Test Hooks from Production Code:** Refactor classes to expose necessary state through properties or signals, and remove methods like `simulate_...`.
