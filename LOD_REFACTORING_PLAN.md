# Law of Demeter (LoD) Audit & Refactoring Plan

This document identifies Law of Demeter (LoD) violations in the SpritePal codebase and outlines a plan to reduce coupling by enforcing "Tell, Don't Ask" principles and providing appropriate façades.

## 1. Confirmed LoD Violations

### [High Severity] `ROMWorkflowController` → `ROMExtractor` Internals
- **File:** `ui/sprite_editor/controllers/rom_workflow_controller.py`
- **Call Chain:** `self.rom_extractor.rom_palette_extractor.get_palette_config_from_sprite_config(...)`
- **Violation:** Reaches through `ROMExtractor` to its internal `rom_palette_extractor`.
- **Impact:** Any change to how `ROMExtractor` organizes its sub-services breaks the controller.

### [High Severity] `CoreOperationsManager` → `ROMExtractor` Internals
- **File:** `core/managers/core_operations_manager.py`
- **Call Chain:** `self._rom_extractor.rom_injector.read_rom_header(rom_path)`
- **Violation:** Reaches through `ROMExtractor` into `rom_injector`.
- **Impact:** Leaks internal implementation details of the core extraction service.

### [High Severity] Controller → View Widget Internal Composition
- **File:** `ui/sprite_editor/controllers/rom_workflow_controller.py`
- **Call Chain:** `self._view.source_bar.set_offset(offset)` / `self._view.asset_browser.add_mesen_capture(...)`
- **Violation:** Controller depends on the specific widget naming and hierarchy within the View.
- **Impact:** UI layout changes (e.g., renaming a sub-widget) break the logic.

### [Medium Severity] View Widgets → Sub-Managers via Controller
- **File:** `ui/sprite_editor/views/widgets/pixel_canvas.py`
- **Call Chain:** `self.controller.tool_manager.get_brush_size()`
- **Violation:** The canvas widget knows that the controller uses a `ToolManager`.
- **Impact:** Tight coupling between the drawing UI and the tool logic implementation.

### [Medium Severity] Inter-Controller Internal Access
- **File:** `ui/sprite_editor/controllers/rom_workflow_controller.py`
- **Call Chain:** `self._editing_controller.undo_manager.can_undo()`
- **Violation:** One controller reaches into the private state manager (`undo_manager`) of another.
- **Impact:** Changes to undo/redo implementation require updates in multiple controllers.

---

## 2. Refactoring Plan

### Phase 1: Core Service Façades
**Goal:** Encapsulate nested services in `ROMExtractor`.

- **Action:** Add delegation methods to `ROMExtractor` for all common sub-service calls.
- **Example:**
  ```python
  # Before
  palette_cfg = self.rom_extractor.rom_palette_extractor.get_palette_config_from_sprite_config(...)
  
  # After
  palette_cfg = self.rom_extractor.get_palette_config(...)
  ```

### Phase 2: View Interface Flattening
**Goal:** Encapsulate widget hierarchy within View classes.

- **Action:** Add high-level methods to `ROMWorkflowPage` and `EditWorkspace` that delegate to internal widgets.
- **Example:**
  ```python
  # Before (in Controller)
  self._view.source_bar.set_offset(offset)
  
  # After (in Controller)
  self._view.update_offset_display(offset)
  ```

### Phase 3: Controller Delegation
**Goal:** Prevent "Reaching Through" controllers to models/managers.

- **Action:** Add delegation methods to `EditingController` for tool state, model data, and undo state.
- **Example:**
  ```python
  # Before (in PixelCanvas)
  brush_size = self.controller.tool_manager.get_brush_size()
  
  # After (in PixelCanvas)
  brush_size = self.controller.get_brush_size()
  ```

---

## 3. Safe Exclusions (Not Violations)

- **Fluent APIs:** Standard filesystem navigation (`Path.parent.parent`).
- **Data Structures:** Direct attribute access on simple Dataclasses or Namespaces (e.g., `header.title`).
- **Qt Standard Patterns:** Connecting to signals on public sub-widgets (e.g., `self.button.clicked.connect(...)`).
- **Composition Root:** Dependency wiring in `AppContext` or `main_window.py`.
