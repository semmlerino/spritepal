# Sprite Editor Analysis & Refactoring Plan

## Status Summary

**Last Update:** 2026-01-08

| Phase | Status | Completed |
|-------|--------|-----------|
| **Phase 1: Quick Wins** | ✅ Complete | ✅ Item 1, ✅ Item 2, ✅ Item 3 |
| **Phase 2: Medium (Collapse Layers)** | In Progress | ✅ Item 4 |
| **Phase 3: Deeper (Architecture)** | Pending | — |

**Completed Work:**
- ✅ Problem #1 (Dual-Path Signal Wiring) - Removed `MainController._update_undo_state` and duplicate status connection. Single signal path now active.
- ✅ Phase 1 Item 2 (Flatten Status Messages) - Replaced 3-layer signal relay with direct dependency injection. Fixed bug where `ROMWorkflowController.status_message` (~25 emit calls) was never connected. Controllers now call `message_service.show_message()` directly.
- ✅ Phase 1 Item 3 (Delete `MainController`) - Moved sub-controller ownership to `SpriteEditorWorkspace`. Broke circular dependency in `ROMWorkflowController`. Deleted `MainController` class entirely.
- ✅ Phase 2 Item 4 (Merge `ExtractionWorkspace` into `MainWindow`) - Inlined setup code into `MainWindow._create_workspaces()`. Deleted `ExtractionWorkspace` class entirely.
- Test Coverage: 1977 passed, 23 skipped, 0 failures (no regression)

**Next Priority:** Phase 2 Item 5 (Dissolve `UICoordinator`)

---

## 1. 10 Highest Impact Problems

1.  **Dual-Path Signal Wiring (Undo/Redo):** ✅ **RESOLVED** (2025-01-08) - Removed `MainController._update_undo_state()` direct path. Single signal flow now: `EditingController.undoStateChanged` → `SpriteEditorWorkspace.undo_state_changed` → `MainWindow._update_undo_redo_state()`. Also removed duplicate status message connection at MainWindow level.
2.  **Service Locator Anti-Pattern (`AppContext`):** `AppContext` is a global bag of services. While it makes dependencies "explicit" in `launch_spritepal.py`, it effectively hides dependencies deeper in the stack where `get_app_context()` is called (e.g., inside `MainWindow` properties).
3.  **God-Class `UICoordinator`:** This class orchestrates unrelated UI concerns (session, tabs, previews, toolbars), creating high coupling between the extraction and editor views.
4.  **Passthrough Signal Chains:** `SpriteEditorWorkspace` acts largely as a "signal relay," receiving signals from controllers and re-emitting them to `MainWindow` (e.g., `status_message`, `mode_changed`), adding noise without value.
5.  **Circular Dependency Workarounds:** `MainWindow` uses lazy properties for `ExtractionController` and `controller` setters to break circular imports, indicating a flaw in the dependency graph (View depends on Controller, which depends on View).
6.  **Redundant Abstraction Layers:** ✅ **PARTIALLY RESOLVED** - `MainController` deleted (Phase 1 Item 3), `ExtractionWorkspace` merged into `MainWindow` (Phase 2 Item 4). Remaining: `ExtractionController` layer (extraction logic split between controller and `MainWindow`).
7.  **Implicit State Sharing:** `ApplicationStateManager` is passed around everywhere, but specific state (like current palette or selected tool) is also synchronized via manual signal connections, leading to "split source of truth."
8.  **Direct Widget Manipulation from Controllers:** `MainController` holds a reference to `MainWindow` and directly manipulates its actions (`action_undo.setEnabled`), violating the Law of Demeter and tight-coupling the Controller to the specific View implementation.
9.  **Over-Architected Editor MVC:** The `ui/sprite_editor` package uses a heavy MVC/Command pattern (`MainController`, `EditingController`, `ExtractionController`, `InjectionController`, `ROMWorkflowController`) for what is essentially a single-page pixel editor with a side panel.
10. **Zombie Signal Connections:** `MainWindow._cleanup_managers` attempts to manually disconnect signals because the ownership/lifecycle of sub-components is unclear, risking memory leaks if a manager is missed.

## 2. Call + Signal Flow Map

### Workflow 1: Application Startup
1.  **`launch_spritepal.py`**
    *   Calls `create_app_context()` -> Creates `AppContext` (Service Locator).
    *   Creates `SpritePalApp` -> Creates `MainWindow`.
    *   **Signal:** None.
2.  **`MainWindow.__init__`**
    *   Calls `_setup_ui()` -> Creates `QStackedWidget` (Center), `QDockWidget` (Left).
    *   Calls `_create_workspaces()` -> Creates `ExtractionWorkspace` & `SpriteEditorWorkspace`.
    *   Calls `_setup_managers()` -> Creates `UICoordinator`, `ToolbarManager`, etc.
    *   **Signal:** Connects `extraction_panel.files_changed`, `rom_extraction_panel.extraction_ready`, etc.
3.  **`SpriteEditorWorkspace.__init__`**
    *   Creates `MainController` (Top-level Controller).
    *   `MainController` creates sub-controllers (`EditingController`, etc.).
    *   **Signal:** Connects `MainController.status_message` -> `self.status_message`.

### Workflow 2: Pixel Edit (Pencil Tool)
1.  **User Action:** Click on Canvas (`EditTab`).
2.  **`EditTab` (View)**
    *   Traps `mousePressEvent`.
    *   Calls `EditingController.handle_pixel_press(x, y)`.
3.  **`EditingController` (Controller)**
    *   Checks `ToolManager` for current tool (Pencil).
    *   Calls `PencilTool.on_press`.
    *   Updates `ImageModel` (sets pixel).
    *   Creates `DrawPixelCommand`.
    *   Calls `UndoManager.record_command()`.
    *   **Signal:** Emits `imageChanged`, `undoStateChanged`.
4.  **`EditTab` (View)**
    *   Listens to `imageChanged`.
    *   Triggers `repaint()`.
5.  **`SpriteEditorWorkspace` (Signal Relay)**
    *   Listens to `undoStateChanged`.
    *   **Signal:** Re-emits `undo_state_changed`.
6.  **`MainWindow` (Root View)**
    *   Listens to `undo_state_changed` (from Workspace).
    *   **Direct Call:** `self.undo_action.setEnabled(True)` (conditional: only when sprite editor tab active).

### Workflow 3: VRAM Extraction
1.  **User Action:** "Extract" button clicked.
2.  **`MainWindow`**
    *   `on_extract_clicked()` -> Shows Dialog.
    *   Calls `_handle_vram_extraction`.
    *   **Signal:** Emits `extract_requested`.
3.  **`ExtractionController` (via MainController)**
    *   Listens to `extract_requested` (Note: Wiring is fuzzy here, often explicit method call is used in other paths).
    *   *Correction based on code:* `MainWindow` calls `extract_requested.emit()`. But who listens?
    *   In `MainController`, there is no explicit connection to `extract_requested` visible in the snippet.
    *   *Actually*, `MainWindow` has a `controller` property that lazy-creates `ExtractionController`.
    *   It seems `MainWindow` might call `controller.start_rom_extraction` directly for ROM, but uses signals for VRAM? (Ambiguity).
4.  **`ExtractionController`**
    *   Performs extraction (via `CoreOperationsManager`).
    *   **Signal:** Emits `preview_ready`, `extraction_completed`.
5.  **`MainController`**
    *   Listens to `extraction_completed`.
    *   Calls `EditingController.load_image`.
    *   **Signal:** `EditingController` emits `imageChanged`.

## 3. Abstraction Audit

| Abstraction | Claims to Abstract | Reality (Complexity Created) | Smells |
| :--- | :--- | :--- | :--- |
| **`AppContext`** | Dependency Injection | Hides dependencies. Makes it hard to tell what a class *actually* needs without reading the code. | Service Locator, Global State. |
| **`UICoordinator`** | UI initialization logic | "God Class" that knows about too many widgets. Tries to sync state between unconnected panels. | High Coupling, God Class. |
| **`MainController`** | Coordination of sub-controllers | Just a container/proxy. Adds a layer of indirection to access `EditingController`. | Middle Man, Passthrough. |
| **`SpriteEditorWorkspace`** | The "Tab" widget logic | Re-implements QTabWidget logic with QStackedWidget. Acts as a signal repeater. | Passthrough, Reinventing the Wheel. |
| **`ExtractionWorkspace`** | Layout of extraction panels | Just a wrapper around `QDockWidget` content. Adds a file separation for layout code. | Wrapper for the sake of wrapping. |
| **`ExtractionController`** | Extraction Logic | Splits logic between itself, `CoreOperationsManager`, and `MainWindow`. | Fragmented Logic. |

## 4. Signal Inventory

| Signal Name | Emitter | Subscriber | Payload | Issues |
| :--- | :--- | :--- | :--- | :--- |
| `undoStateChanged` | `EditingController` | `SpriteEditorWorkspace` | `(bool, bool)` | ✅ **RESOLVED:** Single path (removed MainController direct path). Workspace relays → MainWindow. |
| `status_message` | `EditingController`, `ROMWorkflowController` | N/A | `str` | ✅ **RESOLVED:** (2026-01-08) Replaced with direct DI. Controllers call `message_service.show_message()`. Signals removed from `MainController`, `ROMWorkflowController`, `SpriteEditorWorkspace`. |
| `extract_requested` | `MainWindow` | `ExtractionController` (presumed) | None | **Ambiguous:** Unclear if this triggers the action or just notifies. |
| `mode_changed` | `SpriteEditorWorkspace` | `MainController` | `str` | **Circular:** Workspace UI -> Controller -> Workspace UI (to switch stack). |
| `files_changed` | `ExtractionPanel` | `MainWindow` | None | **Generic:** Doesn't say *what* file changed. |
| `controller.preview_ready` | `ExtractionController` | `MainWindow` | `QPixmap` | **Wrong Direction:** Controller passing UI assets (Pixmap) to View. |

## 5. Refactor Plan

### Phase 1: Quick Wins (Clarify Flow & Remove Duplicates)

1.  ✅ **Kill the Dual Signal Path:** (COMPLETED 2025-01-08)
    *   ✅ Removed `MainController._update_undo_state` method and signal connection.
    *   ✅ Removed duplicate status message connection at MainWindow level (lines 1279-1282).
    *   ✅ Single signal path now active: `EditingController.undoStateChanged` → `SpriteEditorWorkspace.undo_state_changed` → `MainWindow._update_undo_redo_state()`.
    *   ✅ Path 2 retains conditional check (only updates when sprite editor tab is active).
    *   ✅ All tests pass (1984 passed, 23 skipped, 0 failures).

2.  ✅ **Flatten Status Messages:** (COMPLETED 2026-01-08)
    *   ✅ Removed `status_message` signal from `SpriteEditorWorkspace`, `MainController`, and `ROMWorkflowController`.
    *   ✅ Passed `StatusBarManager` to controllers via `message_service` parameter.
    *   ✅ Controllers call `self._message_service.show_message()` directly (with null guard).
    *   ✅ Fixed pre-existing bug: `ROMWorkflowController.status_message` had ~25 emit calls but was **never connected** to anything.
    *   ✅ Created `MainWindowMessageAdapter` for standalone mode (`application.py`).
    *   ✅ Deferred injection via `set_message_service()` to handle initialization order.
    *   ✅ All tests pass (1984 passed, 23 skipped, 0 failures).

3.  ✅ **Delete `MainController`:** (COMPLETED 2026-01-08)
    *   ✅ Broke `ROMWorkflowController` circular dependency: now accepts `editing_controller` directly instead of `main_controller`.
    *   ✅ Moved sub-controller creation to `SpriteEditorWorkspace.__init__()`.
    *   ✅ Moved temp file management and cleanup to `SpriteEditorWorkspace`.
    *   ✅ Added `wire_controllers()` method to `SpriteEditorMainWindow` for standalone mode.
    *   ✅ Deleted `ui/sprite_editor/controllers/main_controller.py` entirely.
    *   ✅ Updated all tests (removed 6 obsolete tests, fixed 2 tests accessing old API).
    *   ✅ All tests pass (1978 passed, 23 skipped, 0 failures).

### Phase 2: Medium (Collapse Layers)

4.  ✅ **Merge `ExtractionWorkspace` into `MainWindow`:** (COMPLETED 2026-01-08)
    *   ✅ Inlined layout configuration into `MainWindow._create_workspaces()`.
    *   ✅ Deleted `ui/workspaces/extraction_workspace.py`.
    *   ✅ Updated `ui/workspaces/__init__.py` to remove export.
    *   ✅ All tests pass (1977 passed, 23 skipped, 0 failures).

5.  **Dissolve `UICoordinator`:**
    *   Move tab handling logic to `MainWindow`.
    *   Move session logic to `SessionManager`.
    *   Move preview logic to `PreviewController`.
    *   Delete `ui/managers/ui_coordinator.py`.

### Phase 3: Deeper (Architecture Fixes)

6.  **Remove `AppContext` (Service Locator):**
    *   Refactor `launch_spritepal.py` to create managers and pass them *explicitly* to `MainWindow`.
    *   Refactor `MainWindow` to pass specific managers to child widgets/controllers.
    *   *Goal:* `MainWindow` should have `__init__(self, rom_service, state_manager, ...)` and NO `get_app_context()` calls.

7.  **Standardize Signal Direction (MVI-lite):**
    *   Enforce: **View** emits `UserAction` -> **Controller** updates **Model** -> **Model** emits `StateChanged` -> **View** updates.
    *   Remove signals where Controller emits UI types (like `QPixmap`). Controller should emit data, View converts to Pixmap.

## Example Rewrite: Undo Wiring

**Before (Spaghettification):**
```python
# EditingController
self.undoStateChanged.emit(can_undo, can_redo)

# MainController (PATH 1 - REMOVED)
self.editing_controller.undoStateChanged.connect(self._update_undo_state)
def _update_undo_state(self, u, r):
    self._main_window.action_undo.setEnabled(u)  # ❌ REMOVED

# SpriteEditorWorkspace (PATH 2 - KEPT)
self._controller.editing_controller.undoStateChanged.connect(self.undo_state_changed.emit)

# MainWindow (NOW SINGLE PATH)
self._sprite_editor_workspace.undo_state_changed.connect(self._update_undo_redo_state)
```

**After (Single Path, 2025-01-08):**
```python
# EditingController
self.undoStateChanged.emit(can_undo, can_redo)

# SpriteEditorWorkspace (Relay)
editing_ctrl.undoStateChanged.connect(self.undo_state_changed.emit)

# MainWindow (Single subscriber)
self._sprite_editor_workspace.undo_state_changed.connect(self._update_undo_redo_state)

def _update_undo_redo_state(self, can_undo: bool, can_redo: bool) -> None:
    # Only update when sprite editor is active tab
    if hasattr(self, "center_stack") and self.center_stack.currentIndex() == 1:
        self.undo_action.setEnabled(can_undo)
        self.redo_action.setEnabled(can_redo)
```

**Impact:**
- ✅ Removed redundant button updates (was happening twice per operation)
- ✅ Cleaner signal flow: one source of truth, one subscriber
- ✅ Conditional check preserved (buttons only update when appropriate tab is active)
- ✅ Zero test regressions (1984 tests pass)
