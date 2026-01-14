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

### Manager Lifecycle

Managers are created at startup via `initialize_managers()`:

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

## Mesen Integration Subsystem

The `core/mesen_integration/` package provides tools for **live sprite capture** from the Mesen 2 emulator and **automated ROM offset discovery**. This is a critical subsystem for mapping VRAM tiles back to their source locations in ROM.

### Purpose

The subsystem bridges three domains:

1. **Mesen 2 Lua Scripts** (`mesen2_integration/lua_scripts/`) - Capture sprites at runtime
2. **JSON Exchange** (`mesen2_exchange/`) - Structured capture data
3. **Python Analysis** (`core/mesen_integration/`) - ROM offset discovery

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Mesen 2 Emulator                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ sprite_rom_finder.lua (click on sprite → get ROM offset)    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼ JSON
┌─────────────────────────────────────────────────────────────────────┐
│                  mesen2_exchange/*.json                             │
│  (OAM entries, VRAM tile data, DMA logs, timing info)               │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 core/mesen_integration/                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │         CorrelationPipeline (Orchestrator)                   │   │
│  │  load_dma_log() → load_capture() → build_database() → run() │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                               │                                     │
│         ┌─────────────────────┼─────────────────────┐              │
│         ▼                     ▼                     ▼              │
│  ┌─────────────┐    ┌─────────────────┐    ┌────────────────┐     │
│  │click_extractor│    │timing_correlator│    │address_space   │     │
│  │(parse JSON)  │    │(DMA matching)   │    │_bridge (SA-1)  │     │
│  └─────────────┘    └─────────────────┘    └────────────────┘     │
│         │                     │                     │              │
│         └──────────┬──────────┴─────────────────────┘              │
│                    ▼                                                │
│         ┌─────────────────────┐                                    │
│         │ tile_hash_database  │  Build searchable tile index       │
│         └─────────────────────┘                                    │
│                    │                                                │
│                    ▼                                                │
│         ┌─────────────────────┐                                    │
│         │  rom_tile_matcher   │  Find ROM offsets via hash lookup  │
│         └─────────────────────┘                                    │
│                    │                                                │
│                    ▼                                                │
│         ┌─────────────────────────────────────────────────────┐   │
│         │  capture_to_rom_mapper → CaptureMapResult            │   │
│         │  (confidence scoring, ambiguity detection)           │   │
│         └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                     ROM offset for extraction
```

### Module Responsibilities

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `click_extractor.py` | Parse Mesen JSON captures | `MesenCaptureParser`, `OAMEntry`, `TileData` |
| `address_space_bridge.py` | SA-1 ↔ SNES address conversion | `CanonicalAddress`, `sa1_to_canonical()` |
| `timing_correlator.py` | Match tiles to DMA events | `TimingCorrelator`, `DMAEvent`, `TileCorrelation` |
| `tile_hash_database.py` | Efficient tile similarity search | `TileHashDatabase`, `build_and_save_database()` |
| `rom_tile_matcher.py` | Find ROM offsets via tile hashing | `ROMTileMatcher`, `TileLocation` |
| `capture_to_rom_mapper.py` | Map entire captures to ROM | `CaptureToROMMapper`, `CaptureMapResult` |
| `full_correlation_pipeline.py` | Orchestrate end-to-end workflow | `CorrelationPipeline`, `PipelineResults` |
| `sa1_character_conversion.py` | SA-1 character format handling | `snes_4bpp_to_bitmap()`, `hash_two_planes()` |
| `gfx_pointer_table.py` | Parse GFX pointer tables | `GFXPointerTableParser`, `rom_to_sa1_cpu()` |
| `capture_renderer.py` | Render captures to images | `CaptureRenderer`, `render_capture_to_files()` |
| `sprite_reassembler.py` | Reassemble multi-OAM sprites | (Used internally by pipeline) |

### Import Rules

The mesen_integration package follows standard Core layer rules:

- ✅ **CAN import from**: `core/`, `utils/`, Python stdlib
- ❌ **CANNOT import from**: `ui/`, `core/managers/` (except via protocols)
- ❌ **CANNOT import from**: External emulators (pure Python analysis only)

### Data Flow

**Click-to-ROM Pipeline (sprite_rom_finder.lua → Python):**

```
1. User clicks sprite in Mesen 2 emulator
                    ↓
2. Lua script captures: OAM index, VRAM tile, DMA log
                    ↓
3. JSON written to mesen2_exchange/
                    ↓
4. click_extractor.py parses JSON → OAMEntry, TileData
                    ↓
5. timing_correlator.py correlates tile with DMA events
                    ↓
6. address_space_bridge.py converts SA-1 addresses → canonical
                    ↓
7. tile_hash_database.py indexes ROM tiles (with flip variants)
                    ↓
8. rom_tile_matcher.py looks up VRAM tile hash → TileLocation[]
                    ↓
9. capture_to_rom_mapper.py scores candidates, detects ambiguity
                    ↓
10. Return ROM offset with confidence score
```

### SA-1 Address Space

Kirby Super Star uses the SA-1 coprocessor, which has a different memory map than standard SNES. The `address_space_bridge.py` module handles:

- **Canonical addresses**: Unified representation for both SNES and SA-1 addresses
- **Staging buffer detection**: Identify WRAM, IRAM, BWRAM staging areas
- **DMA source normalization**: Convert DMA sources to ROM file offsets

**Example:**
```python
from core.mesen_integration import sa1_to_canonical, CanonicalAddress

# SA-1 CPU address 0xC08000 → ROM file offset 0x000000
canonical = sa1_to_canonical(0xC08000)
# canonical.rom_offset == 0x000000 (bank 0xC0 maps to ROM start)
```

### Key Patterns

**1. Tile Hash Lookup**

Tiles are indexed by their content hash (not position). This allows finding matching tiles anywhere in ROM:

```python
from core.mesen_integration import ROMTileMatcher

matcher = ROMTileMatcher(rom_data)
matcher.build_database()

# Lookup VRAM tile (32 bytes of 4bpp data)
locations = matcher.lookup_vram_tile(tile_bytes)
# Returns list of TileLocation(offset, flip_h, flip_v)
```

**2. Confidence Scoring**

The mapper detects ambiguous matches (multiple ROM locations with same tile):

```python
from core.mesen_integration import CaptureToROMMapper

mapper = CaptureToROMMapper(rom_path)
result = mapper.map_capture(capture_json)

if result.is_confident():
    offset = result.primary_rom_offset
else:
    # Multiple candidates - may need manual verification
    for entry in result.get_entries_for_offset(candidate):
        print(f"  {entry.scored_percentage}% confidence")
```

**3. Full Pipeline**

For end-to-end processing:

```python
from core.mesen_integration import CorrelationPipeline, format_pipeline_report

pipeline = CorrelationPipeline(rom_path)
pipeline.load_dma_log("mesen2_exchange/dma_log.txt")
pipeline.load_captures("mesen2_exchange/sprite_capture_*.json")
pipeline.build_database()

results = pipeline.run()
print(format_pipeline_report(results))
```

### Usage in SpritePal

This subsystem is used by:

1. **Manual Offset Control** (`ui/dialogs/manual_offset_dialog.py`) - For verifying ROM offsets
2. **Automated extraction workflows** - When Mesen 2 captures are available
3. **Development/debugging** - Understanding where sprite data comes from

### Related Documentation

- **Lua Scripts**: See `mesen2_integration/README.md` for script usage
- **SNES/SA-1 Hardware**: See `docs/mesen2/00_STABLE_SNES_FACTS.md`
- **Kirby-Specific Mapping**: See `docs/mesen2/03_GAME_MAPPING_KIRBY_SA1.md`

---

*Last updated: January 12, 2026 (Service consolidation in AppContext documented in CLAUDE.md)*
