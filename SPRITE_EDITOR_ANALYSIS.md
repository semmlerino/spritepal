# Sprite Editor Analysis & Refactoring Plan

## 1. 10 Highest Impact Problems

1.  **Dual-Path Signal Wiring (Undo/Redo):** The `EditingController` updates the `MainWindow`'s Undo/Redo buttons via *two* conflicting paths: one direct via `MainController` setting widget state, and another via `SpriteEditorWorkspace` re-emitting signals to `MainWindow`.
2.  **Service Locator Anti-Pattern (`AppContext`):** `AppContext` is a global bag of services. While it makes dependencies "explicit" in `launch_spritepal.py`, it effectively hides dependencies deeper in the stack where `get_app_context()` is called (e.g., inside `MainWindow` properties).
3.  **God-Class `UICoordinator`:** This class orchestrates unrelated UI concerns (session, tabs, previews, toolbars), creating high coupling between the extraction and editor views.
4.  **Passthrough Signal Chains:** `SpriteEditorWorkspace` acts largely as a "signal relay," receiving signals from controllers and re-emitting them to `MainWindow` (e.g., `status_message`, `mode_changed`), adding noise without value.
5.  **Circular Dependency Workarounds:** `MainWindow` uses lazy properties for `ExtractionController` and `controller` setters to break circular imports, indicating a flaw in the dependency graph (View depends on Controller, which depends on View).
6.  **Redundant Abstraction Layers:** The hierarchy `MainController` -> `ExtractionController` -> `ExtractionPanel` -> `ExtractionWorkspace` adds 4 layers to perform a simple task (extracting sprites), making the "Find Usages" feature of IDEs useless.
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
5.  **`MainController` (Coordinator)**
    *   Listens to `undoStateChanged`.
    *   **Direct Call:** `MainWindow.action_undo.setEnabled(True)`.
6.  **`SpriteEditorWorkspace` (Passthrough)**
    *   Listens to `undoStateChanged`.
    *   **Signal:** Re-emits `undo_state_changed`.
7.  **`MainWindow` (Root View)**
    *   Listens to `undo_state_changed` (from Workspace).
    *   **Direct Call:** `self.undo_action.setEnabled(True)` (Redundant Step 5).

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
| `undoStateChanged` | `EditingController` | `MainController`, `SpriteEditorWorkspace` | `(bool, bool)` | **Dual Path:** Handled twice (Controller->Window, Workspace->Window). |
| `status_message` | `EditingController` | `MainController` -> `SpriteEditorWorkspace` -> `MainWindow` | `str` | **Bucket Brigade:** Passed through 3 layers just to show text. |
| `extract_requested` | `MainWindow` | `ExtractionController` (presumed) | None | **Ambiguous:** Unclear if this triggers the action or just notifies. |
| `mode_changed` | `SpriteEditorWorkspace` | `MainController` | `str` | **Circular:** Workspace UI -> Controller -> Workspace UI (to switch stack). |
| `files_changed` | `ExtractionPanel` | `MainWindow` | None | **Generic:** Doesn't say *what* file changed. |
| `controller.preview_ready` | `ExtractionController` | `MainWindow` | `QPixmap` | **Wrong Direction:** Controller passing UI assets (Pixmap) to View. |

## 5. Refactor Plan

### Phase 1: Quick Wins (Clarify Flow & Remove Duplicates)

1.  **Kill the Dual Signal Path:**
    *   Remove `SpriteEditorWorkspace.undo_state_changed` signal.
    *   Remove `MainController._update_undo_state` (the direct manipulation one).
    *   **Action:** Expose `EditingController` via `SpriteEditorWorkspace` property.
    *   **Connect:** `MainWindow` connects directly: `self.sprite_editor.controller.undo_state_changed.connect(self.update_buttons)`.
    *   *Verify:* Undo buttons still work, debug prints show only 1 call per event.

2.  **Flatten Status Messages:**
    *   Remove `status_message` signal from `SpriteEditorWorkspace` and `MainController`.
    *   **Action:** Pass `StatusBarManager` (or a `MessageService` interface) to `EditingController` in `__init__`.
    *   *Verify:* Controller calls `self.message_service.show("Saved")` directly.

3.  **Delete `MainController`:**
    *   It's largely a container. Move `EditingController`, `ExtractionController`, `InjectionController` ownership to `SpriteEditorWorkspace`.
    *   *Verify:* Code compiles, one less file to jump through.

### Phase 2: Medium (Collapse Layers)

4.  **Merge `ExtractionWorkspace` into `MainWindow`:**
    *   It's just layout configuration. Move the setup code to `MainWindow._setup_ui`.
    *   Delete `ui/workspaces/extraction_workspace.py`.

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

**Before (Current Spaghettification):**
```python
# EditingController
self.undoStateChanged.emit(can_undo, can_redo)

# MainController
self.editing_controller.undoStateChanged.connect(self._update_undo_state)
def _update_undo_state(self, u, r):
    self._main_window.action_undo.setEnabled(u) # Direct manipulation

# SpriteEditorWorkspace
self._controller.editing_controller.undoStateChanged.connect(self.undo_state_changed.emit)

# MainWindow
self._sprite_editor_workspace.undo_state_changed.connect(self._update_undo_redo_state)
```

**After (Direct Observation):**
```python
# MainWindow
def _setup_ui(self):
    # ... create workspace ...
    # Connect directly to the source of truth
    self.sprite_editor.editing_controller.undo_state_changed.connect(self.update_undo_actions)

def update_undo_actions(self, can_undo, can_redo):
    self.undo_action.setEnabled(can_undo)
    self.redo_action.setEnabled(can_redo)
```
