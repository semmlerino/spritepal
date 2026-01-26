# Brittle Tests Report

This report identifies tests in the `spritepal` codebase that are considered "brittle"—meaning they are likely to fail due to internal implementation changes rather than actual regressions in behavior.

## Summary of Findings

| Category | Description | Impact |
| :--- | :--- | :--- |
| **Private Member Access** | Tests access `_private_attributes` directly. | Renaming variables or changing internal structures breaks tests. |
| **Implementation Coupling** | Tests verify internal state (e.g., "is timer active?") rather than external behavior. | Refactoring logic (e.g., removing a timer) causes false positives. |
| **Over-Mocking** | Tests mock deep internal dependencies, assuming specific call chains. | Structural changes to dependencies break tests even if the feature works. |

## Detailed Analysis

### 1. `tests/ui/sprite_editor/test_widget_signal_integration.py`
**Issue:** Private Member Access & Mock Call Assertions

This file tests the integration of UI signals but frequently reaches into widgets to assert private state or trigger private sub-components.

*   **Example 1 (`TestPaletteSourceIntegration`):**
    ```python
    # Brittle: accessing private _combo_box to trigger a change
    selector._combo_box.setCurrentIndex(1)
    ```
    *Correction:* Should use the public API `selector.set_source(...)` or simulate a user action on the exposed widget handle if absolutely necessary.

*   **Example 2 (`TestContextualPreviewIntegration`):**
    ```python
    # Brittle: asserting private internal state
    assert preview._current_image is not None
    assert preview._current_image.width() == 16
    ```
    *Correction:* Should test the public side-effect, such as checking if the widget's `pixmap()` property matches expectations or if a paint event draws the correct image.

### 2. `tests/ui/components/test_paged_tile_view_dialog.py`
**Issue:** Deep Implementation Coupling

This test suite treats the `PagedTileViewDialog` as a white-box, inspecting its private children and their private attributes.

*   **Example (`test_go_to_offset`):**
    ```python
    # Brittle: Calculating internal page logic and checking private attributes
    bytes_per_page = dialog._tile_view._cols * dialog._tile_view._rows * 32
    # ...
    assert dialog._tile_view._current_page == 1
    ```
    *Correction:* Verify the *behavior*: Does calling `go_to_offset` make the expected tiles visible? Does `get_current_offset()` return the correct value? The concept of "pages" is an implementation detail of the view.

*   **Example (`test_tile_click_updates_button`):**
    ```python
    # Brittle: Calling private event handlers directly
    dialog._on_tile_clicked(0x1234)
    assert dialog._go_to_btn.isEnabled()
    ```
    *Correction:* Simulate a mouse click on the view or use a public method like `select_offset()`. Check `dialog.accept_button.isEnabled()` (if exposed) or similar public state.

### 3. `tests/ui/frame_mapping/views/test_workbench_canvas_preview.py`
**Issue:** UI Implementation Coupling & Over-Mocking

The tests dictate exactly *how* the preview feature is implemented (via a checkbox, a specific timer, and a hidden scene item).

*   **Example (`TestPreviewToggle`):**
    ```python
    # Brittle: Asserting existence and state of private UI controls
    assert hasattr(canvas, "_preview_checkbox")
    canvas._preview_checkbox.setChecked(True)
    assert canvas._preview_enabled
    ```
    *Correction:* Use public methods to toggle preview mode (e.g., `canvas.set_preview_mode(True)`). Verify the result by checking if the scene renders the preview item, not by checking a boolean flag.

*   **Example (`TestPreviewGeneration`):**
    ```python
    # Brittle: Checking if a private timer is active
    assert canvas._preview_timer.isActive()
    ```
    *Correction:* Use `qtbot.waitSignal` or simply `qtbot.wait(timeout)` to allow the debounce to settle, then verify the final state (preview updated). The presence of a timer is an implementation detail for debouncing.

## Recommendations

1.  **Test Public Contracts:** rewrite tests to interact with objects only through their `def public_method(self):` or public properties. Use `qtbot` to interact with widgets (clicks, keypresses) rather than calling `_on_clicked` handlers directly.
2.  **Avoid `hasattr` Checks:** Do not assert that an object has a private attribute (e.g., `assert hasattr(tab, "_icon_toolbar")`). This locks the code to a specific naming convention.
3.  **Refactor Test Helpers:** Create test-specific helper methods on the classes (or in fixtures) if deep state inspection is truly needed for debugging, but keep the main test logic agnostic of internals.
4.  **Use Fakes over Mocks:** Instead of mocking `CaptureRenderer` with specific method returns, use a fake implementation or a real instance with test data if it's lightweight enough. This avoids "mocking the implementation."
