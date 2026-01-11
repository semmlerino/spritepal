# Codebase Audit: Public Contracts & Boundaries

## 1. MainWindow (App Context Root)
**File:** `ui/main_window.py`

### Responsibility & Boundary
*   **Responsibility:** Application bootstrapping, dependency injection, global session management, and high-level workflow orchestration (switching between Extraction and Editor modes).
*   **Boundary:** Acts as the composition root. Should *not* contain extraction logic or direct worker management.

### Public Surface (Current)
*   **Methods:** `new_extraction()`, `show_settings()`, `switch_to_workspace(index)`, `set_workspace(name)`.
*   **Signals:** `extract_requested`, `open_in_editor_requested`, `extraction_completed`.
*   **State:** `rom_cache`, `settings_manager` (injected).

### Hidden Internals Used Externally
*   *None found directly accessed by other modules, but it orchestrates logic that belongs elsewhere.*

### Recommended Seams
*   **P1:** Move `_start_vram_extraction` and `_start_rom_extraction` (and their worker connections) into a `WorkflowManager` or `ExtractionService`. The Window should only trigger these and react to completion.
*   **P2:** Standardize `switch_to_workspace` to use an Enum rather than magic integers.

### Contract Statement
"When initialized, it guarantees the UI is composed with injected dependencies. It manages the global application lifecycle and high-level navigation."

---

## 2. SpriteEditorWorkspace (Domain Root)
**File:** `ui/workspaces/sprite_editor_workspace.py`

### Responsibility & Boundary
*   **Responsibility:** Container for the sprite editing domain. Manages the transition between `VRAMEditorPage` and `ROMWorkflowPage`.
*   **Boundary:** Owns the `EditingController` and `ROMWorkflowController`.

### Public Surface (Current)
*   **Methods:** `set_mode(mode)`, `load_rom(path)`, `jump_to_offset(offset)`.
*   **Properties:** `current_mode`, `extraction_controller`, `editing_controller`.
*   **Signals:** `mode_changed(str)`.

### Hidden Internals Used Externally
*   `_rom_workflow_controller` is exposed via property `rom_workflow_controller` but acts as a private child.
*   `_editing_controller` is exposed via property `editing_controller`.

### Recommended Seams
*   **P1:** Formalize the mode switch. `set_mode` uses string literals ("vram", "rom"). Use an Enum.
*   **P2:** Hide controllers if possible. External callers (like `MainWindow`) shouldn't need to touch `editing_controller` directly. Expose specific capabilities via the workspace if needed (e.g., `workspace.undo()`).

### Contract Statement
"When given a mode (VRAM/ROM), it guarantees the correct tools and views are displayed. It coordinates the shared editing session between different workflows."

---

## 3. ROMWorkflowController
**File:** `ui/sprite_editor/controllers/rom_workflow_controller.py`

### Responsibility & Boundary
*   **Responsibility:** Orchestrates the ROM modification flow: Browse -> Preview -> Edit -> Inject.
*   **Boundary:** Should coordinate data flow between `ROMExtractor` and `EditingController`.

### Public Surface (Current)
*   **Methods:** `load_rom(path)`, `set_offset(offset)`, `open_in_editor()`, `save_to_rom()`.
*   **Signals:** `rom_info_updated`, `workflow_state_changed`.

### Hidden Internals Used Externally
*   **Violation:** `_editing_controller` is passed in `__init__` and used directly (`self._editing_controller.load_image(...)`). This is tight coupling.
*   **Violation:** `_view` is accessed extensively.

### Recommended Seams
*   **P0:** Decouple `EditingController`. Define a protocol or signal bus for "Load Image Request" that `EditingController` listens to, rather than direct method calls.
*   **P0:** Abstract UI interactions. `QMessageBox` and `QFileDialog` are used inside business logic methods (`save_to_rom`, `prepare_injection`). Move these to a `DialogService` or `ViewDelegate`.

### Contract Statement
"When a ROM is loaded, it guarantees safe navigation and preview of offsets. It manages the transaction of extracting data to the editor and injecting it back."

---

## 4. EditingController
**File:** `ui/sprite_editor/controllers/editing_controller.py`

### Responsibility & Boundary
*   **Responsibility:** Manages pixel editing state, tools, and undo/redo history.
*   **Boundary:** Should only manipulate the `ImageModel` and `PaletteModel`.

### Public Surface (Current)
*   **Methods:** `load_image(data)`, `get_image_data()`, `set_tool(name)`, `set_palette(colors)`.
*   **Signals:** `imageChanged`, `paletteChanged`, `toolChanged`.

### Hidden Internals Used Externally
*   **Violation:** `handle_load_palette`, `save_image_as` contain direct UI calls (`QFileDialog`).

### Recommended Seams
*   **P1:** Remove UI dependencies. `handle_load_palette` should receive a file path, not open a dialog. The View should handle the dialog and call the Controller with the path.
*   **P2:** Promote `_palette_sources` to a proper `PaletteSourceManager` if it grows.

### Contract Statement
"When pixel operations are requested, it guarantees the `ImageModel` is updated and undo history is preserved. It emits signals for all state changes."

---

## 5. ROMExtractor (Core Service)
**File:** `core/rom_extractor.py`

### Responsibility & Boundary
*   **Responsibility:** Extracts sprite data, metadata, and palettes from ROMs using HAL compression.
*   **Boundary:** Pure logic. No UI dependencies.

### Public Surface (Current)
*   **Methods:** `extract_sprite_data`, `scan_for_sprites`, `get_known_sprite_locations`.
*   **Properties:** `rom_injector`, `hal_compressor` (Public attributes).

### Hidden Internals Used Externally
*   **Violation:** `ROMWorkflowController` accesses `rom_extractor.rom_injector` directly to call `read_rom_header`.
*   **Violation:** `ROMWorkflowController` accesses `rom_extractor.rom_injector.find_compressed_sprite`.

### Recommended Seams
*   **P0:** Encapsulate `rom_injector`. `ROMExtractor` should expose `read_header` and `find_sprite` methods that delegate internally, or `ROMInjector` should be a separate public dependency for `ROMWorkflowController`. The current "reach-through" (`extractor.injector.method`) violates Law of Demeter.

### Contract Statement
"When given a ROM path and offset, it guarantees extraction of decompressed sprite data and associated metadata. It manages caching of scan results."

---

## Prioritized Seams to Promote

1.  **[P0] Decouple UI from Logic in Controllers**
    *   **Context:** `ROMWorkflowController` and `EditingController` call `QMessageBox` and `QFileDialog` directly.
    *   **Fix:** Introduce a `DialogService` or event interface. Pass paths/confirmations *into* the controller methods.

2.  **[P0] Fix ROMEschextractor/ROMInjector Reach-through**
    *   **Context:** `ROMWorkflowController` calls `self.rom_extractor.rom_injector.read_rom_header`.
    *   **Fix:** Add `get_header(rom_path)` to `ROMExtractor` or inject `ROMInjector` directly into the controller.

3.  **[P1] Isolate Workflow Logic from MainWindow**
    *   **Context:** `MainWindow` creates and connects workers for extraction.
    *   **Fix:** Move this logic to a `WorkflowManager` that emits "extraction_started" and "extraction_finished".

## "Stop Touching These Internals" List

| Caller | Internal Member | Replacement |
| :--- | :--- | :--- |
| `ROMWorkflowController` | `rom_extractor.rom_injector.*` | Call `rom_extractor.method` (add wrapper) or inject `ROMInjector` directly. |
| `SpriteEditorWorkspace` | `_editing_controller` | Use public methods on Workspace or formalize access. |
| `MainWindow` | `_vram_worker` (direct manipulation) | Use a `WorkflowManager` to handle async tasks. |
| `EditingController` | `_view` (for dialog parenting) | Use a decoupled `DialogService`. |

