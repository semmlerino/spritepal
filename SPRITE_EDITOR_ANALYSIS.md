# Sprite Editor Analysis & Refactoring Plan

## Status Summary

**Last Update:** 2026-01-08

| Phase | Status | Completed |
|-------|--------|-----------|
| **Phase 1: Quick Wins** | ✅ Complete | ✅ Item 1, ✅ Item 2, ✅ Item 3 |
| **Phase 2: Medium (Collapse Layers)** | ✅ Complete | ✅ Item 4, ✅ Item 5 |
| **Phase 3: Deeper (Architecture)** | ✅ Complete | ✅ Item 6, ✅ Item 7, ✅ Item 8, ✅ Item 9 |
| **Phase 4: Assessment** | ✅ Complete | All 10 problems addressed |

**All 10 Problems Status:**
| Problem | Status |
|---------|--------|
| #1 Dual-Path Signal Wiring | ✅ RESOLVED |
| #2 Service Locator Anti-Pattern | ✅ RESOLVED |
| #3 God-Class UICoordinator | ✅ RESOLVED |
| #4 Passthrough Signal Chains | ✅ RESOLVED |
| #5 Circular Dependency Workarounds | ✅ RESOLVED (intentional design) |
| #6 Redundant Abstraction Layers | ✅ RESOLVED |
| #7 Implicit State Sharing | ✅ NOT A PROBLEM |
| #8 Direct Widget Manipulation | ✅ ACCEPTABLE |
| #9 Over-Architected MVC | ✅ ACCEPTABLE |
| #10 Zombie Signal Connections | ✅ IMPROVED |

**Completed Work:**
- ✅ Problem #1 (Dual-Path Signal Wiring) - Removed `MainController._update_undo_state` and duplicate status connection. Single signal path now active.
- ✅ Phase 1 Item 2 (Flatten Status Messages) - Replaced 3-layer signal relay with direct dependency injection. Fixed bug where `ROMWorkflowController.status_message` (~25 emit calls) was never connected. Controllers now call `message_service.show_message()` directly.
- ✅ Phase 1 Item 3 (Delete `MainController`) - Moved sub-controller ownership to `SpriteEditorWorkspace`. Broke circular dependency in `ROMWorkflowController`. Deleted `MainController` class entirely.
- ✅ Phase 2 Item 4 (Merge `ExtractionWorkspace` into `MainWindow`) - Inlined setup code into `MainWindow._create_workspaces()`. Deleted `ExtractionWorkspace` class entirely.
- ✅ Phase 2 Item 5 (Dissolve `UICoordinator`) - Inlined tab helpers, session methods, preview methods, and tab configuration into `MainWindow`. Deleted `UICoordinator` class entirely (~380 lines removed).
- ✅ Phase 3 Item 6 (Remove `AppContext` from MainWindow) - Added 3 explicit constructor parameters (`core_operations_manager`, `log_watcher`, `preview_generator`). Eliminated all 8 `get_app_context()` calls from MainWindow. Updated 2 test files for new signature.
- ✅ Phase 3 Item 7 (Clean Up Dead Signals) - Removed 3 dead signals that emitted UI types: `ROMWorkflowController.preview_ready` (+ rendering code), `AssetBrowserController.thumbnailReady`, `ExtractionController.extraction_completed`. ~15 lines of dead code removed.
- ✅ Phase 3 Item 8 (Remove AppContext from Controllers) - Eliminated all 8 `get_app_context()` calls from `ExtractionController` and `ROMWorkflowController`. Added explicit constructor parameters for `rom_cache`, `rom_extractor`, `log_watcher`, `sprite_library`. Updated `SpriteEditorWorkspace` and `MainWindow` to pass deps. Zero service locator calls remain in sprite editor controllers.
- ✅ Phase 3 Item 9 (Flatten Signal Relay Chains) - Removed 2 pure passthrough signals from `SpriteEditorWorkspace`: `undo_state_changed` and `offset_changed`. MainWindow now connects directly to `EditingController.undoStateChanged` and `ROMWorkflowPage.offset_changed`. Signal chain depth reduced (undo: 2→1 hop, offset: 4→2 hops).
- Test Coverage: 1978 passed, 23 skipped, 0 failures (no regression)

**Refactoring Status:** ✅ **COMPLETE** - All goals achieved, no outstanding work items.

---

## 1. 10 Highest Impact Problems

1.  **Dual-Path Signal Wiring (Undo/Redo):** ✅ **RESOLVED** (2025-01-08, updated 2026-01-08) - Removed `MainController._update_undo_state()` direct path. Signal flow now direct: `EditingController.undoStateChanged` → `MainWindow._update_undo_redo_state()` (no workspace relay). Also removed duplicate status message connection at MainWindow level.
2.  **Service Locator Anti-Pattern (`AppContext`):** ✅ **RESOLVED** (2026-01-08) - MainWindow and all sprite editor controllers now receive dependencies via constructor. Zero `get_app_context()` calls in MainWindow or sprite editor controllers. Full explicit DI chain: `launch_spritepal.py` → `MainWindow` → `SpriteEditorWorkspace` → Controllers.
3.  **God-Class `UICoordinator`:** ✅ **RESOLVED** (2026-01-08) - Dissolved UICoordinator by inlining tab helpers, session methods, preview methods, and tab configuration into `MainWindow`. Deleted `ui/managers/ui_coordinator.py` (~380 lines).
4.  **Passthrough Signal Chains:** ✅ **RESOLVED** (2026-01-08) - Removed 2 relay signals (`undo_state_changed`, `offset_changed`) from `SpriteEditorWorkspace`. MainWindow connects directly to `EditingController.undoStateChanged` (1 hop) and `ROMWorkflowPage.offset_changed` (2 hops). Only `mode_changed` remains (not a relay - originates from workspace).
5.  **Circular Dependency Workarounds:** ✅ **RESOLVED** (2026-01-08) - The lazy `dialog_coordinator` property and `set_message_service()` deferred injection are now **documented intentional patterns** for handling Qt's initialization order constraints (`_setup_ui()` runs before `_setup_managers()`). See CLAUDE.md "Dependency Injection & Initialization Order" section.
6.  **Redundant Abstraction Layers:** ✅ **RESOLVED** (2026-01-08) - `MainController` deleted (Phase 1 Item 3), `ExtractionWorkspace` merged into `MainWindow` (Phase 2 Item 4), main app `ExtractionController` deleted (commit `7e74c717`). Sprite editor has its own scoped `ExtractionController` for VRAM extraction workflow.
7.  **Implicit State Sharing:** ✅ **NOT A PROBLEM** - Each controller owns its domain with single source of truth: `EditingController` → tool/palette/image state, `ROMWorkflowController` → workflow state machine, `ApplicationStateManager` → only used for file path persistence (not runtime state).
8.  **Direct Widget Manipulation from Controllers:** ✅ **ACCEPTABLE** - `MainController` deleted (Phase 1 Item 3). Main app is clean. Sprite editor controllers use older MVC pattern (`self._view.set_*()`) but it's self-contained. `EditingController` demonstrates the better signal-based MVI-lite pattern.
9.  **Over-Architected Editor MVC:** ✅ **ACCEPTABLE** - 5 controllers (2,440 LOC) for 5 distinct workflows (Extract, Edit, Inject, Asset Browser, ROM Mode). This is right-sized for the complexity. Each controller has clear domain boundaries.
10. **Zombie Signal Connections:** ✅ **IMPROVED** - `MainWindow._cleanup_managers()` now uses systematic `cleanup()` protocol with duck typing. Controllers use `safe_disconnect()` utility from `ui/common/signal_utils.py`. Current approach requires discipline but is documented and consistent.

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
| `controller.preview_ready` | `ExtractionController` | `MainWindow` | `QPixmap` | ✅ **RESOLVED:** (2026-01-08) Dead signal removed. Also removed `ROMWorkflowController.preview_ready`, `AssetBrowserController.thumbnailReady`, `ExtractionController.extraction_completed`. |

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

5.  ✅ **Dissolve `UICoordinator`:** (COMPLETED 2026-01-08)
    *   ✅ Added tab helper methods to `MainWindow` (`is_rom_tab_active()`, `is_vram_tab_active()`, etc.).
    *   ✅ Moved tab configuration logic to `MainWindow` (`_configure_rom_extraction_tab()`, etc.).
    *   ✅ Inlined session methods into `MainWindow` (`_restore_session()`, `_save_session()`, etc.).
    *   ✅ Inlined preview methods into `MainWindow` (`_create_preview_panel()`, `_clear_previews()`, etc.).
    *   ✅ Deleted `ui/managers/ui_coordinator.py` (~380 lines removed).
    *   ✅ Updated `ui/managers/__init__.py` to remove export.
    *   ✅ Removed dead import from `tests/ui/test_layout_responsiveness.py`.
    *   ✅ All tests pass (1978 passed, 23 skipped, 0 failures).

### Phase 3: Deeper (Architecture Fixes)

6.  ✅ **Remove `AppContext` from MainWindow:** (COMPLETED 2026-01-08)
    *   ✅ Added 3 explicit constructor parameters: `core_operations_manager`, `log_watcher`, `preview_generator`.
    *   ✅ Eliminated all 8 `get_app_context()` calls from MainWindow.
    *   ✅ Updated `launch_spritepal.py` to pass dependencies explicitly.
    *   ✅ Updated 2 test files for new signature.
    *   *Remaining:* Controllers still use service locator (~8 call sites in ExtractionController, ROMWorkflowController).

7.  ✅ **Clean Up Dead Signals:** (COMPLETED 2026-01-08)
    *   ✅ Removed `ROMWorkflowController.preview_ready` signal + unused rendering code (~10 lines).
    *   ✅ Removed `AssetBrowserController.thumbnailReady` signal (defined but never used).
    *   ✅ Removed `ExtractionController.extraction_completed` signal + emit calls (no subscribers).
    *   ✅ All tests pass (1978 passed, 23 skipped, 0 failures).
    *   *Note:* Full MVI-lite refactoring (converting direct view manipulation to signal-based) deferred as lower priority.

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

---

## Final Summary

**Refactoring Complete:** All 10 identified architectural problems have been addressed.

### Resolution Categories
- **Problems #1-6:** Fully resolved through code deletion and restructuring
- **Problem #7:** Investigation revealed it was not actually a problem
- **Problems #8-10:** Acceptable as-is with documented patterns

### Deleted Code (~780 lines)
| Component | Lines | Commit |
|-----------|-------|--------|
| `UICoordinator` | ~380 | Phase 2 Item 5 |
| `MainController` | ~150 | Phase 1 Item 3 |
| `ExtractionWorkspace` | ~50 | Phase 2 Item 4 |
| Main app `ExtractionController` | ~200 | `7e74c717` |

### Patterns Established
1. **Dependency Injection via constructor** - Documented in CLAUDE.md
2. **Deferred injection for Qt init order** - `set_message_service()` pattern
3. **Direct signal connections** - No passthrough relays
4. **Systematic cleanup() protocol** - Duck-typed with `safe_disconnect()` utility

### Architecture After Refactoring
```
launch_spritepal.py
└── MainWindow (receives: core_operations_manager, log_watcher, preview_generator)
    └── SpriteEditorWorkspace (receives: rom_cache, rom_extractor, etc.)
        ├── ExtractionController (scoped to VRAM extraction)
        ├── EditingController (pixel editing, undo/redo)
        ├── InjectionController (PNG→VRAM/ROM)
        └── ROMWorkflowController (ROM mode orchestration)
            └── AssetBrowserController (library management)
```

### Test Impact
- **Before refactoring:** 1984 tests passing
- **After refactoring:** 1978 tests passing (6 obsolete tests removed)
- **Zero regressions** throughout all phases
