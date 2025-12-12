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
│       Core Layer (core/)            │  ← Domain Logic
├─────────────────────────────────────┤
│       Utils Layer (utils/)          │  ← Shared Utilities
└─────────────────────────────────────┘
```

### Import Rules

1. **UI Layer (`ui/`)**
   - ✅ CAN import from: `core/`, `core/managers/`, `utils/`
   - ❌ CANNOT import from: other UI modules (except submodules)
   - Purpose: Presentation layer only, no business logic

2. **Manager Layer (`core/managers/`)**
   - ✅ CAN import from: `core/`, `utils/`
   - ❌ CANNOT import from: `ui/`
   - Purpose: Business logic, workflow coordination

3. **Core Layer (`core/`)**
   - ✅ CAN import from: `utils/`
   - ❌ CANNOT import from: `ui/`, `core/managers/`
   - Purpose: Domain logic, data structures, algorithms

4. **Utils Layer (`utils/`)**
   - ✅ CAN import from: Python standard library only
   - ❌ CANNOT import from: ANY SpritePal modules
   - Purpose: Shared utilities, constants, helpers

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
   def __init__(self, extraction_manager: ExtractionManagerProtocol):
       self.extraction_manager = extraction_manager
   ```

3. **Protocol-Based Injection**
   Use `inject()` for resolving protocols when constructing objects:
   ```python
   from spritepal.core.di_container import inject
   from spritepal.core.protocols.manager_protocols import ExtractionManagerProtocol

   # At application entry point or factory
   extraction_manager = inject(ExtractionManagerProtocol)
   panel = ROMExtractionPanel(extraction_manager=extraction_manager)
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
   from spritepal.core.di_container import inject
   manager = inject(ExtractionManagerProtocol)
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

### Dialog Initialization Pattern

All dialogs should follow the initialization pattern enforced by `DialogBase`:

```python
from spritepal.ui.components.base import DialogBase

class MyDialog(DialogBase):
    def __init__(self, parent: QWidget | None = None):
        # Step 1: Declare ALL instance variables
        self.my_widget: QWidget | None = None
        self.my_data: list[str] = []
        
        # Step 2: Call super().__init__() 
        super().__init__(parent)  # This calls _setup_ui()
        
    def _setup_ui(self):
        # Step 3: Create widgets (variables already declared)
        self.my_widget = QPushButton("Click me")
```

This prevents the common bug where instance variables declared after `_setup_ui()` overwrite already-created widgets.

### Singleton Cleanup Order

At application shutdown, singletons must be cleaned up in the correct order to avoid dangling references and segfaults:

```
1. UI Components (MainWindow, dialogs)
   ↓
2. Worker Pools (HALProcessPool, preview workers)
   ↓
3. ManagerRegistry.cleanup_managers()
   ↓
4. DI Container (reset_container())
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

### Dependency Injection Pattern

SpritePal uses constructor injection with the `inject()` function:

```python
# Getting manager instances
from core.di_container import inject
from core.protocols.manager_protocols import ExtractionManagerProtocol

extraction_manager = inject(ExtractionManagerProtocol)

# In class constructors (required parameters)
class MyWorker:
    def __init__(self, params: dict, extraction_manager: ExtractionManager):
        self.manager = extraction_manager
```

**Do NOT use:**
- Module-level convenience functions (removed)
- Direct `ManagerRegistry()` access in production code (use `inject()`)
- Optional manager parameters (now required)