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
   - Purpose: Domain logic, data structures, algorithms
   - Note: Core uses PySide6 for QObject-based managers/workers (signals, threading).
     This is intentional architecture for event-driven patterns, not a layer violation.
     Core services may reference manager protocols for DI but should not import managers directly.

5. **Utils Layer (`utils/`)**
   - ✅ CAN import from: Python standard library only
   - ❌ CANNOT import from: ANY SpritePal modules
   - Purpose: Shared utilities, constants, helpers

### Naming Conventions: Manager vs Coordinator

SpritePal uses two naming patterns for orchestration classes. Choose based on **where the class lives and what it owns**:

| Pattern | Layer | State Ownership | Example |
|---------|-------|-----------------|---------|
| **Manager** | Core (`core/managers/`) | Owns business state | `ExtractionManager`, `SessionManager` |
| **Coordinator** | UI (`ui/managers/`) | Coordinates widgets, no business state | `PreviewCoordinator`, `TabCoordinator` |

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

---

## Singletons and Cleanup

### Active Singletons

SpritePal uses multiple singleton patterns for resource management:

| Singleton | Location | Purpose | Thread-Safe | Reset Method |
|-----------|----------|---------|-------------|--------------|
| `AppContext` | `core/app_context.py` | Manager access | N/A | `reset_app_context()` |
| `ManagerRegistry` | `core/managers/registry.py` | Manager lifecycle | Yes (QMutex) | `reset_for_tests()` |
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
    3. Manager Registry
       - ManagerRegistry().cleanup_managers()
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
| `ManagerRegistry` | Managers are QObjects with Qt parents |
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

SpritePal uses **AppContext** to provide access to managers:

### AppContext (`core/app_context.py`)

The AppContext is the central access point for all managers:

```python
from core.app_context import get_app_context

# Get a manager instance
context = get_app_context()
manager = context.core_operations_manager
```

**Key functions:**
- `get_app_context()` - Get the global AppContext (raises if not initialized)
- `create_app_context(...)` - Initialize AppContext with managers (done at startup)
- `reset_app_context()` - Clear context (for tests)

### ManagerRegistry (`core/managers/registry.py`) - Lifecycle Management

The ManagerRegistry is a **singleton** that:
1. Creates all manager instances at startup
2. Registers them with AppContext
3. Handles cleanup at shutdown

**Initialization Flow:**
```
Application Start
       ↓
initialize_managers()
       ↓
1. Create ApplicationStateManager
   ↓
2. Create CoreOperationsManager
   ↓
3. create_app_context(...)         → Registers both managers
   ↓
Application Code: get_app_context().core_operations_manager
       ↓
AppContext returns the registered manager
```

**Why this order matters:** CoreOperationsManager creates ROMExtractor, which needs
ROMCache, which needs ApplicationStateManager. Managers must be created in dependency order.

### Quick Reference

| Need | Use |
|------|-----|
| Get a manager in application code | `get_app_context().core_operations_manager` |
| Pass manager to a class | Constructor parameter: `def __init__(self, manager: CoreOperationsManager)` |
| Initialize all managers | `initialize_managers()` (done at app startup) |
| Clean up at shutdown | `cleanup_managers()` |
| Reset for tests | Use `app_context` fixture |

### Available Protocols

SpritePal uses concrete classes directly via DI. The `core/protocols/` directory is reserved for future protocol definitions.

**Use concrete classes directly** (no protocol wrappers needed):
- `CoreOperationsManager` - Extraction and injection operations
- `ApplicationStateManager` - Session, state, settings
- `ConfigurationService` - App configuration
- `ROMCache` - ROM file caching
- `ROMExtractor` - Low-level ROM extraction

### What NOT to Do

```python
# REMOVED - ManagerRegistry getter methods no longer exist
# from core.managers.registry import ManagerRegistry
# manager = ManagerRegistry().get_extraction_manager()  # Method removed

# CORRECT - use get_app_context()
from core.app_context import get_app_context
manager = get_app_context().core_operations_manager
```

```python
# BAD - direct instantiation
from core.managers.core_operations_manager import CoreOperationsManager
manager = CoreOperationsManager()  # Missing required dependencies

# GOOD - use get_app_context() for proper initialization
from core.app_context import get_app_context
manager = get_app_context().core_operations_manager
```

---

## Manager Architecture

SpritePal uses consolidated managers for all business logic. The adapter pattern
that was previously used for backward compatibility has been fully removed.

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
│    - Access via get_app_context().core_operations_manager    │
│                                                              │
│  ApplicationStateManager:                                    │
│    - Owns session, settings, state, history                  │
│    - Access via get_app_context().application_state_manager  │
└─────────────────────────────────────────────────────────────┘
```

### Key Rules

1. **Use get_app_context() for access**: Always get managers via `get_app_context()`,
   never instantiate directly.

2. **Single source of truth**: All business logic lives in consolidated managers.
   No adapters or wrappers needed.

3. **Services are shared**: ROMService, VRAMService, etc. are created once
   by CoreOperationsManager and reused.

### Example: Using CoreOperationsManager

```python
from core.app_context import get_app_context

# Get manager via AppContext
manager = get_app_context().core_operations_manager

# Connect to signals
manager.extraction_progress.connect(self._on_progress)
manager.extraction_complete.connect(self._on_complete)

# Call extraction methods
result = manager.extract_from_rom(params)
```

### Benefits of Consolidation

- **Simpler code**: No adapter layers to maintain
- **Single source of truth**: All business logic in one place
- **Better discoverability**: Clear method locations
- **Reduced duplication**: Services created once

---

*Last updated: December 26, 2025 (Replaced inject() with get_app_context() pattern)*
