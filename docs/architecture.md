# SpritePal Architecture Guidelines

## Module Boundaries and Import Rules

SpritePal follows a layered architecture to maintain clean dependencies and prevent circular imports.

### Layer Structure

```
┌─────────────────────────────────────┐
│         UI Layer (ui/)              │  ← User Interface
├─────────────────────────────────────┤
│     Manager Layer (core/managers/)  │  ← Business Logic
├─────────────────────────────────────┤
│    Services Layer (core/services/)  │  ← Stateless Operations
├─────────────────────────────────────┤
│       Core Layer (core/)            │  ← Domain Logic
├─────────────────────────────────────┤
│       Utils Layer (utils/)          │  ← Shared Utilities
└─────────────────────────────────────┘
```

**For detailed data flow diagrams**, see [application_flows.md](./application_flows.md).

### Import Rules

1. **UI Layer (`ui/`)**
   - ✅ CAN import from: `core/`, `core/managers/`, `utils/`
   - ❌ CANNOT import from: other UI modules (except submodules)
   - Purpose: Presentation layer only, no business logic

2. **Manager Layer (`core/managers/`)**
   - ✅ CAN import from: `core/`, `core/services/`, `utils/`, `PySide6`
   - ❌ CANNOT import from: `ui/`
   - Purpose: Business logic, workflow coordination, state ownership
   - Note: Managers inherit from QObject for signal-based communication

3. **Services Layer (`core/services/`)**
   - ✅ CAN import from: `core/`, `utils/`, `PySide6`
   - ❌ CANNOT import from: `ui/`, `core/managers/` (except via protocols)
   - Purpose: Stateless operations, data transformations
   - Files:
     - `dump_file_detection_service.py` - Auto-detection of VRAM/CGRAM/OAM dump files
     - `extraction_readiness_service.py` - Validation for extraction readiness
     - `image_utils.py` - Image format conversions
     - `lru_cache.py` - LRU cache implementation
     - `palette_utils.py` - Palette handling utilities
     - `path_suggestion_service.py` - File path suggestions
     - `preview_generator.py` - Thumbnail/preview generation (singleton)
     - `rom_cache.py` - ROM file caching with async support
     - `rom_service.py` - ROM file operations
     - `vram_service.py` - VRAM extraction operations
     - `worker_lifecycle.py` - Background worker management

4. **Core Layer (`core/`)**
   - ✅ CAN import from: `utils/`, `PySide6` (for Qt event infrastructure)
   - ❌ CANNOT import from: `ui/`, `core/managers/` (except via protocols)
   - Purpose: Domain logic, data structures, algorithms.
   - **Utility Modules**: Recently extracted logic for improved testability:
     - `hal_parser.py`: HAL compression format parsing and validation.
     - `tile_utils.py`: SNES tile bitplane decoding/encoding and manipulation.
     - `analysis_utils.py`: ROM space analysis, slack detection, and empty region detection.
   - Note: Core uses PySide6 for QObject-based managers/workers (signals, threading).
     This is intentional architecture for event-driven patterns, not a layer violation.
     Core services may reference manager protocols for DI but should not import managers directly.

### Law of Demeter (LoD) and Facades

SpritePal strictly enforces the Law of Demeter to prevent tight coupling. Components should only talk to their immediate neighbors and use **facade methods** to interact with deeper child components.

- **Bad**: `workspace.editing_controller.image_model.set_pixel(...)`
- **Good**: `workspace.set_pixel(...)` (where `workspace` delegates to `editing_controller`)

All major controllers and views should expose high-level facade methods (`get_*`, `set_*`, `clear_*`, `perform_*`) rather than exposing internal children.

5. **Utils Layer (`utils/`)**
   - ✅ CAN import from: Python standard library only
   - ❌ CANNOT import from: ANY SpritePal modules
   - Purpose: Shared utilities, constants, helpers

### UI Services Layer (`ui/services/`)

The UI services layer contains **workflow coordinators** that orchestrate UI operations without being tied to specific widgets. These coordinators bridge the gap between MainWindow and Core managers.

```
┌─────────────────────────────────────────────────────────────┐
│                     MainWindow                               │
│  - UI construction, signal connections, user action handlers │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   UI Services (`ui/services/`)               │
│  ExtractionWorkflowCoordinator:                              │
│    - Manages extraction worker lifecycle                     │
│    - Validates extraction parameters                         │
│    - Emits signals: extraction_started, extraction_failed,   │
│      vram_extraction_finished, rom_extraction_finished       │
│    - Delegates to CoreOperationsManager for business logic   │
│                                                              │
│  DialogCoordinator:                                          │
│    - Manages dialog lifecycle and modality                   │
│    - Handles dialog result callbacks                         │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   Core Managers (`core/managers/`)           │
│  - Business logic, state ownership, service coordination    │
└─────────────────────────────────────────────────────────────┘
```

**Import Rules for UI Services:**
- ✅ CAN import from: `core/`, `core/managers/`, `core/services/`, `utils/`
- ❌ CANNOT import from: `ui/` widgets directly (use signals)
- Purpose: Workflow orchestration, worker lifecycle management

**ExtractionWorkflowCoordinator Example:**
```python
from core.app_context import get_app_context
from ui.services import ExtractionWorkflowCoordinator

# Create coordinator (typically done in MainWindow._setup_managers)
coordinator = ExtractionWorkflowCoordinator(get_app_context())

# Connect signals for UI updates
coordinator.extraction_started.connect(self._on_extraction_started)
coordinator.extraction_failed.connect(self._on_extraction_failed)
coordinator.vram_extraction_finished.connect(self._on_vram_finished)

# For preview/palette updates, connect to CoreOperationsManager directly
# (ExtractionResult contains PIL.Image which can't be serialized)
coordinator.core_operations_manager.extraction_completed.connect(
    self._on_extraction_completed
)

# Start extraction
coordinator.start_vram_extraction(params)
```

### Naming Conventions: Manager vs Coordinator

SpritePal uses two naming patterns for orchestration classes. Choose based on **where the class lives and what it owns**:

| Pattern | Layer | State Ownership | Example |
|---------|-------|-----------------|---------|
| **Manager** | Core (`core/managers/`) | Owns business state | `CoreOperationsManager`, `ApplicationStateManager` |
| **Coordinator** | UI (`ui/services/`, `ui/managers/`) | Coordinates workflows, no business state | `ExtractionWorkflowCoordinator`, `DialogCoordinator` |

**When to use each:**

- **Manager**: Use when the class:
  - Lives in `core/managers/`
  - Owns business logic and state
  - Emits signals that cross component boundaries
  - Example: `ExtractionManager` owns extraction state and emits `extraction_complete`

- **Coordinator**: Use when the class:
  - Lives in `ui/managers/` or `ui/common/`
  - Coordinates UI widgets without owning business logic
  - Delegates business operations to Managers via DI
  - Example: `PreviewCoordinator` coordinates preview widgets but delegates generation to `PreviewGenerator`

**Adding a new orchestration class:**

1. Business logic needed? → `core/managers/*_manager.py`
2. UI coordination only? → `ui/managers/*_coordinator.py`
3. Hybrid (UI + some logic)? → Create Manager in core, Coordinator in UI that uses it

### Layer Boundary Design

The Core layer (`core/`) has **zero runtime imports from UI** (`ui/`). This clean separation is maintained through:

1. **Protocol-Based DI**
   - Core defines protocols in `core/protocols/`
   - UI implements these protocols
   - DI container maps protocols to implementations at runtime

**Entry Point Responsibilities:**
```python
# In launch_spritepal.py or test fixtures:
initialize_managers("AppName", settings_path=...)
```

### Common Patterns

#### Avoiding Circular Imports

1. **Use Type Checking Imports**
   ```python
   from typing import TYPE_CHECKING

   if TYPE_CHECKING:
       from spritepal.core.controller import Controller
   ```

2. **Pure Dependency Injection (Preferred)**
   Pass managers as constructor parameters:
   ```python
   # Required: Pass manager explicitly
   def __init__(self, core_manager: CoreOperationsManager):
       self.core_manager = core_manager
   ```

3. **AppContext for Manager Access**
   Use `get_app_context()` to access managers:
   ```python
   from core.app_context import get_app_context
   from core.managers.core_operations_manager import CoreOperationsManager

   # At application entry point or factory
   context = get_app_context()
   core_manager = context.core_operations_manager
   panel = ROMExtractionPanel(core_manager=core_manager)
   ```

   **Note:** The legacy `ManagerRegistry.get_*_manager()` methods have been removed.
   Module-level `get_*_manager()` convenience functions have been removed.

### Special Cases

#### Conditional Imports

Some modules support standalone operation and use conditional imports:

```python
# utils/rom_cache.py - Supports standalone usage
try:
    from spritepal.utils.logging_config import get_logger
except ImportError:
    # Fallback for standalone usage
    import logging
    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)
```

This pattern is acceptable ONLY in `utils/` modules that need to work independently.

### Anti-Patterns to Avoid

1. **Import Inside Functions** (except for circular import resolution)
   ```python
   # Bad
   def my_function():
       from spritepal.utils.settings import get_settings  # Avoid!
   ```

2. **Wildcard Imports**
   ```python
   # Bad
   from spritepal.core import *

   # Good
   from spritepal.core import SpriteExtractor, PaletteManager
   ```

3. **Cross-UI Module Imports**
   ```python
   # Bad - ui/dialogs importing from ui/panels
   from spritepal.ui.panels import SomePanel

   # Good - use signals or callbacks instead
   ```

4. **Service Locator Pattern** (Removed)
   ```python
   # Bad - Service locator functions have been removed
   from spritepal.core.managers import get_extraction_manager  # REMOVED
   manager = ManagerRegistry.get_extraction_manager()  # REMOVED

   # Good - Use get_app_context() or constructor injection
   from core.app_context import get_app_context
   manager = get_app_context().core_operations_manager
   ```

### Testing Imports

Test files have more flexibility but should follow these guidelines:

1. Tests can import from any layer
2. Use test fixtures to avoid production dependencies
3. Mock external dependencies at module boundaries

### Enforcement

1. **Static Analysis**: Run `python scripts/analyze_imports.py` to check for violations
2. **Code Review**: Check imports follow these rules
3. **CI/CD**: Automated checks for import violations

### Dialog Patterns

#### Initialization Pattern

All dialogs should follow the initialization pattern enforced by `DialogBase`:

```python
class MyDialog(DialogBase):
    def __init__(self, parent: QWidget | None = None):
        # Step 1: Declare ALL instance variables BEFORE super()
        self.my_widget: QWidget | None = None
        self.my_data: list[str] = []

        # Step 2: Call super().__init__()
        super().__init__(parent)  # This calls _setup_ui()

    def _setup_ui(self):
        # Step 3: Create widgets (variables already declared)
        self.my_widget = QPushButton("Click me")
```

#### Dialog Lifecycle Types

| Type | Parent | WA_DeleteOnClose | closeEvent | Use For |
|------|--------|------------------|------------|---------|
| One-time | Required | True (default) | Default | File dialogs, message boxes |
| Singleton | **None** | False | Hide, ignore | Persistent tool windows |
| Reusable | Optional | False | Hide, ignore | Frequently used dialogs |

#### Singleton Dialog Pattern

**Critical**: Singleton dialogs must be parentless to survive parent deletion.

```python
class SingletonDialog(BaseDialog):
    _instance: ClassVar["SingletonDialog | None"] = None

    @classmethod
    def get_instance(cls, parent: QWidget | None = None) -> "SingletonDialog":
        if cls._instance is None:
            cls._instance = cls(parent=None)  # ALWAYS None
        return cls._instance

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=None, title="Singleton")  # ALWAYS None
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

    def closeEvent(self, event: QCloseEvent):
        event.ignore()
        self.hide()  # Hide instead of close
```

#### Red Flags in Code Review

- Singleton with parent parameter used
- No WA_DeleteOnClose=False for singletons/reusables
- No closeEvent override for singletons
- Only mock-based dialog tests (no real Qt lifecycle tests)

#### Signal Disconnection Pattern

Dialogs and panels that connect to signals should disconnect them in `closeEvent()` to prevent memory leaks and stale callbacks. Use `safe_disconnect()` from `ui/common/signal_utils.py`:

```python
from ui.common.signal_utils import safe_disconnect

class MyDialog(DialogBase):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.manager.data_changed.connect(self._on_data_changed)

    def closeEvent(self, event: QCloseEvent | None) -> None:
        # Disconnect signals to prevent memory leaks
        safe_disconnect(self.manager.data_changed)
        if event:
            super().closeEvent(event)
```

**Why `safe_disconnect()`?**
- Suppresses `RuntimeWarning` from PySide6 when signal has no connections
- Handles `RuntimeError` and `TypeError` if already disconnected
- Single line instead of try/except boilerplate

**Available utilities in `ui/common/signal_utils.py`:**

| Function | Purpose |
|----------|---------|
| `safe_disconnect(signal)` | Disconnect all slots from a signal safely |
| `is_valid_qt(obj)` | Check if Qt object is still valid (not deleted) |
| `is_valid_pixmap(pixmap)` | Check if QPixmap is valid and not null |
| `blocked_signals(widget)` | Context manager to temporarily block signals |

**Example - blocking signals during programmatic updates:**
```python
from ui.common.signal_utils import blocked_signals

def _sync_slider_to_spinbox(self, value: int) -> None:
    with blocked_signals(self.spinbox):
        self.spinbox.setValue(value)  # Won't trigger valueChanged
```

---

## Singletons and Cleanup

### Active Singletons

SpritePal uses multiple singleton patterns for resource management:

| Singleton | Location | Purpose | Thread-Safe | Reset Method |
|-----------|----------|---------|-------------|--------------|
| `AppContext` | `core/app_context.py` | Manager access | N/A | `reset_app_context()` |
| `HALProcessPool` | `core/hal_compression.py` | Compression workers | Yes (Lock) | `shutdown()` |
| `PreviewGenerator` | `core/services/preview_generator.py` | Thumbnail generation | Yes (QMutex) | `cleanup()` |

### Cleanup Order

At application shutdown, singletons **must** be cleaned up in this order:

```
Application Exit (QApplication.aboutToQuit signal)
         ↓
    1. UI Components
       - MainWindow and dialogs closed by Qt automatically
         ↓
    2. Worker Pools
       - HALProcessPool.shutdown()
       - PreviewGenerator.cleanup()
         ↓
    3. Managers
       - cleanup_managers()
         ↓
    4. AppContext
       - reset_app_context()
```

#### Implementation

The cleanup is orchestrated by `QApplication.aboutToQuit`:

```python
# In main.py or application entry point
app = QApplication(sys.argv)

def cleanup():
    """Clean up all resources in correct order."""
    # 1. Close UI (done automatically by Qt)

    # 2. Stop worker pools
    from core.services.worker_lifecycle import WorkerLifecycleService
    WorkerLifecycleService.cleanup_all()

    # 3. Clean up managers
    from core.managers import cleanup_managers
    cleanup_managers()

    # 4. Reset AppContext
    from core.app_context import reset_app_context
    reset_app_context()

app.aboutToQuit.connect(cleanup)
```

#### Why Order Matters

1. **UI First**: Qt widgets may hold references to managers; closing UI first prevents access to cleaned-up managers.
2. **Workers Second**: Worker threads may reference managers; stopping workers prevents race conditions.
3. **Managers Third**: Managers may hold resources (files, caches); cleaning them releases resources.
4. **AppContext Last**: Context holds manager references; resetting it ensures no dangling references.

### Threading Constraints

**Main Thread Only** - These singletons must be accessed/reset from the main (GUI) thread:

| Singleton | Reason |
|-----------|--------|
| `PreviewGenerator` | Uses QTimer for debouncing |
| `AppContext` | Returns QObject-based managers |

**Signal Connection Rules** - When connecting signals from managers, use `Qt.QueuedConnection` unless you're certain both sender and receiver are on the same thread:

```python
# Safe cross-thread signal connection
manager.operation_complete.connect(
    self.on_operation_complete,
    Qt.ConnectionType.QueuedConnection
)
```

### Test Cleanup

The `app_context` fixture handles all singleton cleanup automatically:

```python
def test_something(app_context):
    # AppContext provides fresh managers
    manager = app_context.core_operations_manager
    # ... test ...
    # Cleanup happens automatically after test
```

---

## Manager Access

SpritePal uses **AppContext** (`core/app_context.py`) to provide access to managers.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│      AppContext (get_app_context())                          │
│  .core_operations_manager → CoreOperationsManager            │
│  .application_state_manager → ApplicationStateManager        │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               Consolidated Managers                          │
│  CoreOperationsManager:                                      │
│    - Owns ROMService, VRAMService, ROMExtractor             │
│    - Owns all extraction/injection business logic            │
│                                                              │
│  ApplicationStateManager:                                    │
│    - Owns session, settings, state, history                  │
└─────────────────────────────────────────────────────────────┘
```

### Quick Reference

| Need | Use |
|------|-----|
| Get a manager | `get_app_context().core_operations_manager` |
| Pass to a class | Constructor: `def __init__(self, manager: CoreOperationsManager)` |
| Initialize (app startup) | `initialize_managers()` |
| Clean up (shutdown) | `cleanup_managers()` |
| Reset (tests) | Use `app_context` fixture |

### Key Rules

1. **Always use `get_app_context()`** — never instantiate managers directly
2. **Dependency order matters** — ApplicationStateManager must exist before CoreOperationsManager (ROMExtractor → ROMCache → ApplicationStateManager)
3. **Services are shared** — ROMService, VRAMService, etc. are created once and reused

### Example

```python
from core.app_context import get_app_context

manager = get_app_context().core_operations_manager
manager.extraction_complete.connect(self._on_complete)
result = manager.extract_from_rom(params)
```

---

## Mesen Integration Subsystem

The `core/mesen_integration/` package provides tools for live sprite capture from the Mesen 2 emulator and automated ROM offset discovery.

**Full documentation:** [docs/mesen2/architecture.md](mesen2/architecture.md)

**Related:** [mesen2_integration/README.md](../mesen2_integration/README.md) (Lua scripts), [00_STABLE_SNES_FACTS.md](mesen2/00_STABLE_SNES_FACTS.md) (SNES hardware)

---

## Frame Mapping Subsystem

The `ui/frame_mapping/` package provides tools for **mapping AI-generated sprite frames to game animation frames**. This is used to replace game sprites with AI-upscaled or custom versions while maintaining proper alignment.

### Purpose

The Frame Mapping workspace enables:

1. **AI Frame Import** - Load PNG frames generated by AI tools (e.g., upscaled sprites)
2. **Game Frame Capture** - Import animation frames captured from Mesen 2 emulator
3. **Frame Pairing** - Link AI frames to corresponding game frames
4. **Alignment** - Position sprites precisely using the Workbench Canvas
5. **Direct Injection** - Write paired sprites back to ROM at correct offsets

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FrameMappingWorkspace                                     │
│                    (ui/workspaces/frame_mapping_workspace.py)                │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                 FrameMappingController                               │    │
│  │                 (ui/frame_mapping/controllers/)                      │    │
│  │                                                                      │    │
│  │  • new_project(), load_project(), save_project()                    │    │
│  │  • load_ai_frames(), import_capture()                                │    │
│  │  • create_mapping(), inject_mapping()                                │    │
│  │                                                                      │    │
│  │  Signals: project_changed, ai_frames_loaded, game_frame_added,      │    │
│  │           mapping_created, mapping_removed, mapping_injected         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│       ┌───────────────────────┼───────────────────────┐                     │
│       ▼                       ▼                       ▼                     │
│  ┌───────────────┐    ┌─────────────────┐    ┌────────────────────┐        │
│  │ AIFramesPane  │    │ WorkbenchCanvas │    │ CapturesLibraryPane │        │
│  │ (Left Pane)   │    │ (Center Top)    │    │ (Right Pane)        │        │
│  │               │    │                 │    │                     │        │
│  │ • Frame list  │    │ • Sprite align  │    │ • Capture list      │        │
│  │ • Thumbnails  │    │ • Zoom/pan      │    │ • ROM offsets       │        │
│  │ • Selection   │    │ • In-game view  │    │ • Import dialog     │        │
│  └───────────────┘    └─────────────────┘    └────────────────────┘        │
│                               │                                              │
│                               ▼                                              │
│                       ┌─────────────────┐                                   │
│                       │  MappingPanel   │                                   │
│                       │ (Center Bottom) │                                   │
│                       │                 │                                   │
│                       │ • Paired frames │                                   │
│                       │ • Inject button │                                   │
│                       │ • Status info   │                                   │
│                       └─────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Core Support Classes                                      │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ FrameMappingProject (core/frame_mapping_project.py)                    │ │
│  │ • AIFrame, GameFrame, FrameMapping data classes                        │ │
│  │ • Project serialization (JSON)                                         │ │
│  │ • Alignment metadata (x_offset, y_offset)                              │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ CaptureRenderer (core/mesen_integration/capture_renderer.py)           │ │
│  │ • Renders Mesen 2 capture JSON to preview images                       │ │
│  │ • Handles OAM entries and tile data                                    │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ROMInjector (core/rom_injector.py)                                     │ │
│  │ • Injects aligned sprite data back into ROM                            │ │
│  │ • Uses tile-aware injection for multi-tile sprites                     │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Module Responsibilities

| Module | Location | Purpose |
|--------|----------|---------|
| `FrameMappingWorkspace` | `ui/workspaces/frame_mapping_workspace.py` | Main workspace widget, toolbar, layout |
| `FrameMappingController` | `ui/frame_mapping/controllers/` | Business logic, signal coordination |
| `AIFramesPane` | `ui/frame_mapping/views/ai_frames_pane.py` | Left pane showing AI sprite frames |
| `CapturesLibraryPane` | `ui/frame_mapping/views/captures_library_pane.py` | Right pane showing Mesen 2 captures |
| `WorkbenchCanvas` | `ui/frame_mapping/views/workbench_canvas.py` | Center canvas with zoom/pan/alignment |
| `MappingPanel` | `ui/frame_mapping/views/mapping_panel.py` | Paired frames table and injection |
| `FrameMappingProject` | `core/frame_mapping_project.py` | Project data model and serialization |
| `SpriteSelectionDialog` | `ui/frame_mapping/dialogs/` | Sprite selection with tile grouping |
| `SpriteCompositor` | `core/services/sprite_compositor.py` | Applies alignment/preview transforms for composite rendering |
| `ROMVerificationService` | `core/services/rom_verification_service.py` | Verifies ROM offsets before injection |

### Key Features

**Workbench Canvas:**
- Interactive zoom (Ctrl+scroll, button controls)
- Pan by dragging canvas
- In-game preview toggle (shows composite sprite appearance)
- Sprite alignment with offset persistence

**Contiguous Tile Grouping:**
- Groups adjacent OAM entries for multi-tile sprites
- Ensures complete sprite capture for replacement

**ROM Tracking:**
- Tracks ROM path from Sprite Editor (synced via signals)
- Maintains modified ROM path after injection
- Supports direct injection from Frame Mapping

### Import Rules

The Frame Mapping package follows UI layer rules:

- ✅ **CAN import from**: `core/`, `core/mesen_integration/`, `utils/`
- ❌ **CANNOT import from**: other `ui/` packages (except common utilities)

### Data Flow

**Frame Pairing Flow:**
```
1. User loads AI frames (PNG files from directory)
                    ↓
2. User imports Mesen 2 captures (JSON with OAM/tile data)
                    ↓
3. User selects AI frame (left pane) → AIFramesPane.selection_changed
                    ↓
4. User selects game frame (right pane) → CapturesLibraryPane.frame_selected
                    ↓
5. FrameMappingController.create_mapping() links frames
                    ↓
6. WorkbenchCanvas displays both sprites for alignment
                    ↓
7. User adjusts alignment (drag or offset controls)
                    ↓
8. User clicks Inject → mapping written to ROM
```

### Related Documentation

- **UI Overview**: See [README.md → Frame Mapping Workspace](../README.md#frame-mapping-workspace)
- **Workflow Details**: See [application_flows.md → Section 8](application_flows.md#8-frame-mapping-workflow)
- **Mesen 2 Captures**: See [mesen2_integration/README.md](../mesen2_integration/README.md)

---

*Last updated: January 22, 2026 (Extracted Mesen subsystem to mesen2/architecture.md; consolidated Manager sections)*
