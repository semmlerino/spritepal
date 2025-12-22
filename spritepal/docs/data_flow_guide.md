# SpritePal Data Flow Guide

This document traces how data moves through the SpritePal system, helping developers understand key workflows without reading multiple source files.

---

## 1. Sprite Extraction Flow

SpritePal supports two extraction modes: **VRAM extraction** (from emulator memory dumps) and **ROM extraction** (directly from game ROMs).

### 1.1 VRAM Extraction Flow

```
User selects VRAM/CGRAM files
         │
         ▼
┌────────────────────────────┐
│ ROMExtractionPanel         │  ui/rom_extraction_panel.py
│ _on_vram_file_selected()   │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ CoreOperationsManager      │  core/managers/core_operations_manager.py
│ extract_from_vram()        │  Coordinates extraction, owns state
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ VRAMService                │  core/services/vram_service.py
│ extract_from_vram()        │  Validates files, delegates to extractor
│ _extract_palettes()        │  Reads CGRAM palette data
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ SpriteExtractor            │  core/extractor.py
│ load_vram()                │  Loads VRAM binary data
│ extract_tiles()            │  Decodes 4BPP tiles to pixels
│ _decode_4bpp_tile()        │  Converts 4BPP format to indexed color
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ image_utils                │  core/services/image_utils.py
│ pil_to_qpixmap()           │  Converts PIL Image → QPixmap for display
└────────────────────────────┘
         │
         ▼
     PNG output / Preview display
```

**Key files:**
- `ui/rom_extraction_panel.py` - UI entry point
- `core/managers/core_operations_manager.py:extract_from_vram()` - Manager coordination
- `core/services/vram_service.py:extract_from_vram()` - Service delegation
- `core/extractor.py:SpriteExtractor` - Core tile decoding logic

---

### 1.2 ROM Extraction Flow

```
User selects ROM file
         │
         ▼
┌────────────────────────────┐
│ ROMExtractionPanel         │  ui/rom_extraction_panel.py
│ _load_rom()                │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ CoreOperationsManager      │  core/managers/core_operations_manager.py
│ extract_from_rom()         │  Coordinates ROM extraction
│ get_rom_extractor()        │  Creates/returns ROMExtractor
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ROMService                 │  core/services/rom_service.py
│ extract_from_rom()         │  ROM-specific validation
│ get_known_sprite_locations │  Returns known game sprite addresses
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ROMExtractor               │  core/rom_extractor.py
│ extract_sprite_from_rom()  │  Main extraction entry point
│ _validate_and_read_rom()   │  Validates ROM file format
│ _decompress_sprite_data()  │  Calls HAL for decompression
│ _convert_4bpp_to_png()     │  Converts decompressed data to image
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ HALProcessPool             │  core/hal_compression.py
│ decompress()               │  Calls external 'exhal' binary
│                            │  Returns decompressed tile data
└────────────────────────────┘
         │
         ▼
     PNG output / Preview display
```

**Key files:**
- `core/rom_extractor.py:ROMExtractor` - ROM-specific extraction logic
- `core/hal_compression.py:HALProcessPool` - External decompression via `exhal` binary
- `config/known_sprites.json` - Database of known sprite locations per game

---

## 2. Settings/Configuration Flow

SpritePal uses a layered configuration system with multiple settings files.

### 2.1 Settings Files

| File | Purpose | When Used |
|------|---------|-----------|
| `.spritepal_settings.json` | Production settings | Normal app launch |
| `.spritepal-test_settings.json` | Unit test settings | When `SPRITEPAL_TEST_MODE` is set |
| `.spritepal-uitest_settings.json` | UI test settings | UI-specific test scenarios |

### 2.2 Configuration Load Flow

```
Application Launch (launch_spritepal.py)
         │
         ▼
┌────────────────────────────┐
│ Early ConfigurationService │  launch_spritepal.py:26-42
│ Load feature flags         │  Reads "experimental" settings
│ (composed dialogs, etc.)   │  BEFORE managers are initialized
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ManagerRegistry            │  core/managers/registry.py
│ initialize_managers()      │  Creates all manager instances
│ configure_container()      │  Registers with DI container
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ConfigurationService       │  core/configuration_service.py
│ (main instance)            │  Computes application paths:
│                            │  - settings_file, cache_directory
│                            │  - log_directory, config_directory
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ SessionManager             │  core/managers/session_manager.py
│ _load_settings()           │  Loads JSON settings
│ _merge_with_defaults()     │  Fills missing values with defaults
│ save_settings()            │  Persists changes to JSON file
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ApplicationStateManager    │  core/managers/application_state_manager.py
│ workflow_state_changed     │  Emits signals on state changes
│                            │  UI components listen to this
└────────────────────────────┘
```

**Key files:**
- `core/configuration_service.py:ConfigurationService` - Path resolution
- `core/managers/session_manager.py:SessionManager` - Settings persistence
- `core/managers/application_state_manager.py` - Runtime state + signals

### 2.3 Settings Access Pattern

```python
# In UI components, use dependency injection:
from core.di_container import inject
from core.protocols.manager_protocols import SettingsManagerProtocol

settings_manager = inject(SettingsManagerProtocol)
value = settings_manager.get("some_setting", default_value)
```

---

## 3. Error Flow

SpritePal uses a custom exception hierarchy with centralized error handling.

### 3.1 Exception Hierarchy

```
Exception
    └── ManagerError (base for all SpritePal errors)
            ├── ExtractionError      # Sprite extraction failures
            ├── InjectionError       # Sprite injection failures
            ├── SessionError         # Settings/session failures
            ├── ValidationError      # Parameter validation failures
            ├── PreviewError         # Preview generation failures
            ├── FileOperationError   # File I/O failures
            ├── NavigationError      # Navigation/browse failures
            └── CacheError           # Cache operation failures
                    ├── CacheCorruptionError
                    └── CachePermissionError
```

Defined in: `core/exceptions.py`

### 3.2 Error Propagation Flow

```
Exception occurs in core layer
         │
         ▼
┌────────────────────────────┐
│ Service/Manager Layer      │  Catches, logs, optionally re-raises
│ logger.error(...)          │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ErrorHandler               │  ui/common/error_handler.py
│ (Thread-safe)              │  Routes errors to appropriate UI
│ handle_error()             │  Shows user-friendly messages
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ConsoleErrorHandler        │  core/console_error_handler.py
│ (CLI/logging mode)         │  Outputs to console/log file
│                            │  Used when no UI is available
└────────────────────────────┘
         │
         ▼
     User sees error message or log entry
```

**Key files:**
- `core/exceptions.py` - Exception class definitions
- `ui/common/error_handler.py` - UI error handler (thread-safe)
- `core/console_error_handler.py` - Console/logging error handler

### 3.3 Error Handling Pattern

```python
from core.exceptions import ExtractionError

try:
    result = extractor.extract_sprite(params)
except ExtractionError as e:
    # Specific extraction failure - show user-friendly message
    error_handler.handle_error(e, "Extraction failed")
except ManagerError as e:
    # Generic manager error - log and notify
    logger.error(f"Operation failed: {e}")
    error_handler.handle_error(e, "Operation failed")
```

---

## 4. Injection Flow

Sprite injection writes modified sprites back to ROM or VRAM files.

```
User modifies sprite
         │
         ▼
┌────────────────────────────┐
│ InjectionDialog            │  ui/injection_dialog.py
│ _on_inject_clicked()       │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ InjectionManager           │  core/managers/injection_manager.py
│ inject_sprite()            │  Validates and coordinates injection
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ InjectionWorker            │  ui/workers/injection_worker.py
│ run()                      │  Background thread for injection
│                            │  Emits progress/completion signals
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ HALProcessPool             │  core/hal_compression.py
│ compress()                 │  Compresses sprite data for ROM
└────────────────────────────┘
         │
         ▼
     Modified ROM file written
```

**Key files:**
- `core/managers/core_operations_manager.py` - Injection coordination
- `core/workers/injection.py` - Background injection workers (VRAMInjectionWorker, ROMInjectionWorker)

---

## 5. Preview Generation Flow

Preview images are generated for thumbnails and sprite display.

```
Sprite data loaded
         │
         ▼
┌────────────────────────────┐
│ PreviewCoordinator         │  ui/managers/preview_coordinator.py
│ generate_preview()         │  UI-layer coordination
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ PreviewGenerator           │  core/services/preview_generator.py
│ generate()                 │  Creates PIL Image from tile data
│ _apply_palette()           │  Maps indexed colors to RGB
│ _scale_image()             │  Scales for display
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ BatchThumbnailWorker       │  ui/workers/batch_thumbnail_worker.py
│ run()                      │  Background thread for batch generation
│                            │  Emits thumbnail_ready signal per item
└────────────────────────────┘
         │
         ▼
     QPixmap ready for display
```

**Key files:**
- `core/services/preview_generator.py:PreviewGenerator` - Core preview generation
- `ui/workers/batch_thumbnail_worker.py` - Batch thumbnail generation

---

## 6. Manager Initialization Order

Managers are initialized in a specific order due to dependencies. **Changing this order can break the application.**

```
launch_spritepal.py
         │
         ▼
ManagerRegistry.initialize_managers()
         │
         ├── 1. ApplicationStateManager   (no dependencies)
         │
         ├── 2. SettingsManager           (reads ConfigurationService paths)
         │
         ├── 3. CoreOperationsManager     (depends on StateManager)
         │
         └── 4. register_managers()         (registers ExtractionManagerProtocol,
                                             InjectionManagerProtocol as adapters)
```

**Note**: `ExtractionManagerProtocol` and `InjectionManagerProtocol` are implemented via adapters that delegate to `CoreOperationsManager`. See `docs/architecture.md` for the adapter pattern details.

**WARNING**: The order is implicit in `core/managers/registry.py:initialize_managers()`. Adding new managers requires careful consideration of dependencies.

---

## Quick Reference: Where to Find Code

| Task | Primary File | Key Method |
|------|--------------|------------|
| VRAM extraction | `core/extractor.py` | `SpriteExtractor.extract_tiles()` |
| ROM extraction | `core/rom_extractor.py` | `ROMExtractor.extract_sprite_from_rom()` |
| HAL compression | `core/hal_compression.py` | `HALProcessPool.compress/decompress()` |
| Settings load | `core/managers/session_manager.py` | `SessionManager._load_settings()` |
| Error handling | `ui/common/error_handler.py` | `ErrorHandler.handle_error()` |
| Preview generation | `core/services/preview_generator.py` | `PreviewGenerator.generate()` |
| DI injection | `core/di_container.py` | `inject()` |

---

*Last updated: December 22, 2025*
