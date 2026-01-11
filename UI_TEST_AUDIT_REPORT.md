# Audit Report: UI-Test Flakiness & Assumption Violations

## 1. Mouse/Keyboard Simulation on Unexposed Widgets
**Issue:** `qtbot.mouseClick` and `keyClick` are used on widgets that have been `show()`n but not confirmed as `exposed` (rendered and active in the window system). `isVisible()` returns `True` immediately after `show()`, but the window system may not be ready, causing events to be lost or coordinates to be invalid (0,0).

### Findings:
*   **`tests/ui/test_edit_workspace_shortcuts.py:54`**
    *   **Assumption:** `workspace.show()` is enough for `mouseClick` to work.
    *   **Fix Category:** **A** (Wait for exposed).
*   **`tests/ui/integration/test_inject_tab_signals.py:40`** (and multiple other lines in this file)
    *   **Assumption:** Staged widgets in `qtbot.addWidget` are immediately ready for interaction.
    *   **Fix Category:** **A** (Wait for exposed).
*   **`tests/ui/integration/test_extract_tab_signals.py:40`** (and multiple other lines in this file)
    *   **Assumption:** Similar to `InjectTab`, assumes immediate readiness.
    *   **Fix Category:** **A** (Wait for exposed).

---

## 2. Double-Click Assumptions on Views
**Issue:** `qtbot.mouseDClick` is unreliable on `QTreeView`/`QListView` items because it does not account for scrolling, expansion, or the specific visual rect of the item.

### Findings:
*   **`tests/ui/integration/test_sprite_asset_browser_signals.py:115`**
    *   **Assumption:** Double-click simulation is brittle, so it falls back to signal emission.
    *   **Verdict:** Correct use of **Strategy B** (Direct Call) to avoid flake, but confirms the lack of a reliable simulation helper.

---

## 3. Coordinate and Target Errors
**Issue:** No usage of `scrollTo` was found in the codebase. Any test attempting to click a specific item in a list/tree/table via coordinates would be inherently flaky if the item is not in the viewport.

### Findings:
*   **Observation:** Current tests avoid coordinate-based clicking on list items, preferring `setCurrentItem` or signal emission.
*   **Risk:** Future tests attempting `qtbot.mouseClick(view.viewport(), ...)` without `scrollTo` will likely be flaky.

---

## 4. Timing and Focus Hazards
**Issue:** Reliance on `time.sleep` instead of event-driven waits or polling.

### Findings:
*   **`tests/ui/integration/test_gallery_window_integration.py:174`**
    *   **Assumption:** Static sleep is sufficient for background worker completion.
    *   **Fix Category:** **B** (Replace with `qtbot.waitUntil`).

---

## Proposed Helper Functions

Add these to a common test utility file (e.g., `tests/ui/common/test_helpers.py`):

### 1. Reliable Widget Click
```python
def click_widget(qtbot, widget, button=Qt.MouseButton.LeftButton, delay=0):
    """
    Ensures a widget is effectively visible and exposed before clicking.
    """
    if not widget.isVisible():
        widget.show()
    
    # Wait for the widget to be fully rendered in the window system
    qtbot.waitExposed(widget)
    
    qtbot.mouseClick(widget, button, delay=delay)
```

### 2. Reliable Item Click (for Views)
```python
def click_item(qtbot, view, index, button=Qt.MouseButton.LeftButton, double=False):
    """
    Scrolls an item into view and clicks its visual center.
    """
    view.scrollTo(index)
    rect = view.visualRect(index)
    if not rect.isValid():
         raise RuntimeError("Item geometry is invalid even after scrollTo")
    
    # Target the viewport, not the view widget itself
    target = view.viewport()
    center = rect.center()
    
    if double:
        qtbot.mouseDClick(target, button, pos=center)
    else:
        qtbot.mouseClick(target, button, pos=center)
```

## Checklist for UI Input Simulation
Before adding `qtbot.mouseClick` or `qtbot.keyClick`, ensure:
1.  [ ] `widget.isVisible()` is True.
2.  [ ] `qtbot.waitExposed(widget)` has been called for the target or its parent window.
3.  [ ] For `QAbstractItemView` items: `view.scrollTo(index)` is called first.
4.  [ ] Target is the `viewport()` if clicking inside a scroll area.
5.  [ ] Geometry is verified via `view.visualRect(index).isValid()`.
