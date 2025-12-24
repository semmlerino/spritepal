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
     - `image_utils.py` - Image format conversions
     - `preview_generator.py` - Thumbnail/preview generation (singleton)
     - `rom_service.py` - ROM file operations
     - `rom_cache.py` - ROM file caching with async support
     - `vram_service.py` - VRAM extraction operations
     - `settings_manager.py` - Settings persistence
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

1. **Self-Registration Pattern** for UI Factories
   - UI factories (dialogs, workers) are registered by application entry points
   - Entry points call `register_ui_factories()` from `ui/__init__.py` AFTER `initialize_managers()`
   - Core code accesses factories via DI protocols, never importing UI directly

2. **Protocol-Based DI**
   - Core defines protocols in `core/protocols/`
   - UI implements these protocols
   - DI container maps protocols to implementations at runtime

**Entry Point Responsibilities:**
```python
# In launch_spritepal.py or test fixtures:
initialize_managers("AppName", settings_path=...)
from ui import register_ui_factories
register_ui_factories()  # Must be called AFTER initialize_managers()
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

3. **Protocol-Based Injection**
   Use `inject()` for resolving managers when constructing objects:
   ```python
   from core.di_container import inject
   from core.managers.core_operations_manager import CoreOperationsManager

   # At application entry point or factory
   core_manager = inject(CoreOperationsManager)
   panel = ROMExtractionPanel(core_manager=core_manager)
   ```

   **Note:** The legacy `ManagerRegistry.get_*_manager()` methods are deprecated.
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
   manager = ManagerRegistry.get_extraction_manager()  # DEPRECATED

   # Good - Use inject() or constructor injection
   from core.di_container import inject
   manager = inject(CoreOperationsManager)
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
| `ManagerRegistry` | `core/managers/registry.py` | Manager lifecycle | Yes (QMutex) | `reset_for_tests()` |
| `DIContainer` | `core/di_container.py` | Protocol bindings | No | `reset_container()` |
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
    4. DI Container
       - reset_container()
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

    # 4. Reset DI container
    from core.di_container import reset_container
    reset_container()

app.aboutToQuit.connect(cleanup)
```

#### Why Order Matters

1. **UI First**: Qt widgets may hold references to managers; closing UI first prevents access to cleaned-up managers.
2. **Workers Second**: Worker threads may reference managers; stopping workers prevents race conditions.
3. **Managers Third**: Managers may hold resources (files, caches); cleaning them releases resources.
4. **DI Container Last**: Container holds singleton references; resetting it ensures no dangling protocol implementations.

### Threading Constraints

**Main Thread Only** - These singletons must be accessed/reset from the main (GUI) thread:

| Singleton | Reason |
|-----------|--------|
| `ManagerRegistry` | Managers are QObjects with Qt parents |
| `PreviewGenerator` | Uses QTimer for debouncing |
| `DIContainer` | May return QObject-based implementations |

**Signal Connection Rules** - When connecting signals from managers, use `Qt.QueuedConnection` unless you're certain both sender and receiver are on the same thread:

```python
# Safe cross-thread signal connection
manager.operation_complete.connect(
    self.on_operation_complete,
    Qt.ConnectionType.QueuedConnection
)
```

### Test Cleanup

The `isolated_managers` fixture handles all singleton cleanup automatically:

```python
def test_something(isolated_managers):
    # Managers and DI container are fresh
    manager = inject(CoreOperationsManager)
    # ... test ...
    # Cleanup happens automatically after test
```

---

## Dependency Injection

SpritePal has two DI mechanisms that work **together**:

### The Two Systems

#### DIContainer (`core/di_container.py`) - Preferred

The DIContainer maps protocol types to implementations. Use it to obtain dependencies:

```python
from core.di_container import inject
from core.managers.core_operations_manager import CoreOperationsManager

# Get a manager instance
manager = inject(CoreOperationsManager)
```

**Key functions:**
- `inject(ProtocolType)` - Get an instance for a protocol
- `register_singleton(protocol, instance)` - Register a singleton
- `register_factory(protocol, factory_fn)` - Register a factory function
- `reset_container()` - Clear all bindings (for tests)

#### ManagerRegistry (`core/managers/registry.py`) - Lifecycle Management

The ManagerRegistry is a **singleton** that:
1. Creates all manager instances at startup
2. Configures the DIContainer (registers services and managers)
3. Handles cleanup at shutdown

**Initialization Flow:**
```
Application Start
       ↓
ManagerRegistry.initialize_managers()
       ↓
1. configure_container()           → Registers services (ConfigurationService,
   │                                  SettingsManager, ROMCache, etc.)
   ↓
2. Create ApplicationStateManager  → Registers ApplicationStateManagerProtocol
   │
   ↓
3. Create CoreOperationsManager    → Can now use inject(ApplicationStateManager)
   │                                  via ROMCache → SettingsManager chain
   ↓
4. register_managers()             → Registers CoreOperationsManager
   │                                  as concrete class (no protocol wrapper)
   ↓
Application Code: inject(CoreOperationsManager)
       ↓
DIContainer returns the registered implementation
```

**Why this order matters:** CoreOperationsManager creates ROMExtractor, which needs
ROMCache, which needs SettingsManager, which needs ApplicationStateManager. If
ApplicationStateManager isn't registered before CoreOperationsManager is created, the DI chain fails.

### Quick Reference

| Need | Use |
|------|-----|
| Get a manager in application code | `inject(CoreOperationsManager)` |
| Pass manager to a class | Constructor parameter: `def __init__(self, manager: CoreOperationsManager)` |
| Initialize all managers | `ManagerRegistry().initialize_managers()` (done at app startup) |
| Clean up at shutdown | `ManagerRegistry().cleanup_managers()` |
| Reset for tests | Use `isolated_managers` fixture |

### Available Protocols

SpritePal uses 5 protocols across two files:

**Manager protocols** (`core/protocols/manager_protocols.py`):

| Protocol | Purpose |
|----------|---------|
| `ROMCacheProtocol` | ROM file caching |
| `ROMExtractorProtocol` | Low-level ROM extraction |

**Dialog protocols** (`core/protocols/dialog_protocols.py`):

| Protocol | Purpose |
|----------|---------|
| `DialogFactoryProtocol` | Create dialog instances |
| `ArrangementDialogProtocol` | Grid arrangement dialog |

**Consolidated managers** (use concrete classes directly, not protocols):
- `CoreOperationsManager` - Extraction and injection operations
- `ApplicationStateManager` - Session, state, settings
- `ConfigurationService` - App configuration

### What NOT to Do

```python
# REMOVED - ManagerRegistry getter methods no longer exist
# from core.managers.registry import ManagerRegistry
# manager = ManagerRegistry().get_extraction_manager()  # Method removed

# CORRECT - use inject() with concrete manager class
from core.di_container import inject
from core.managers.core_operations_manager import CoreOperationsManager
manager = inject(CoreOperationsManager)
```

```python
# BAD - direct instantiation
from core.managers.core_operations_manager import CoreOperationsManager
manager = CoreOperationsManager()  # Missing required dependencies

# GOOD - use inject() for proper initialization
from core.di_container import inject
manager = inject(CoreOperationsManager)
```

---

## Manager Architecture

SpritePal uses consolidated managers for all business logic. The adapter pattern
that was previously used for backward compatibility has been fully removed.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│      DI Container (inject() with concrete classes)          │
│  inject(CoreOperationsManager) → CoreOperationsManager      │
│  inject(ApplicationStateManager) → ApplicationStateManager  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               Consolidated Managers                          │
│  CoreOperationsManager:                                      │
│    - Owns ROMService, VRAMService, ROMExtractor             │
│    - Owns all extraction/injection business logic            │
│    - Direct access via inject(CoreOperationsManager)         │
│                                                              │
│  ApplicationStateManager:                                    │
│    - Owns session, settings, state, history                  │
│    - Direct access via inject(ApplicationStateManager)       │
└─────────────────────────────────────────────────────────────┘
```

### Key Rules

1. **Use inject() for access**: Always get managers via `inject(ManagerClass)`,
   never instantiate directly.

2. **Single source of truth**: All business logic lives in consolidated managers.
   No adapters or wrappers needed.

3. **Services are shared**: ROMService, VRAMService, etc. are created once
   by CoreOperationsManager and reused.

### Example: Using CoreOperationsManager

```python
from core.di_container import inject
from core.managers.core_operations_manager import CoreOperationsManager

# Get manager via DI
manager = inject(CoreOperationsManager)

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

*Last updated: December 24, 2025 (Protocol simplification: 7 → 5 protocols, adapters removed)*
