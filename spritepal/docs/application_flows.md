# SpritePal Application Flows

This document traces how data and control flow through the SpritePal system.

---

## 1. Initialization Flow

Components must be initialized in this exact order. **Changing this order will break the application.**

```
Application Entry Point (launch_spritepal.py)
                    │
                    ▼
    ┌───────────────────────────────────────────────────────────────┐
    │  initialize_managers("SpritePal", settings_path=...)          │
    │                                                               │
    │  1. configure_container()                                     │
    │     Registers SERVICES (not managers):                        │
    │     • ConfigurationServiceProtocol → ConfigurationService     │
    │     • SettingsManagerProtocol → factory (lazy)                │
    │     • ROMCacheProtocol → factory (lazy)                       │
    │     • ROMExtractorProtocol → factory (lazy)                   │
    │                          │                                    │
    │                          ▼                                    │
    │  2. Create ApplicationStateManager                            │
    │     • Handles: session, settings, state, history              │
    │     • Registers: ApplicationStateManagerProtocol              │
    │     ⚠️ CRITICAL: Must be registered BEFORE CoreOperations     │
    │                          │                                    │
    │                          ▼                                    │
    │  3. Create SpritePresetManager                                │
    │     • Handles: user-defined sprite presets                    │
    │                          │                                    │
    │                          ▼                                    │
    │  4. Create CoreOperationsManager                              │
    │     • Handles: extraction, injection, palette, nav            │
    │     • Registered as: CoreOperationsManager (concrete class)   │
    └───────────────────────────────────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────────────────────────────────┐
    │  register_ui_factories()                                      │
    │  ⚠️ MUST be called AFTER initialize_managers()               │
    │  Registers: DialogFactoryProtocol, etc.                       │
    └───────────────────────────────────────────────────────────────┘
                    │
                    ▼
           Application Ready
```

### Dependency Chain

When you call `inject(ROMExtractorProtocol)`:

```
ROMExtractor needs ROMCacheProtocol
    └── ROMCache needs SettingsManagerProtocol
            └── SettingsManager needs ApplicationStateManagerProtocol
                    └── ✓ Already registered (step 2)
```

### Common Initialization Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "No registration for ApplicationStateManagerProtocol" | CoreOperationsManager created before ApplicationStateManager | Ensure `configure_container()` runs first |
| "No registration for DialogFactoryProtocol" | UI code called inject before `register_ui_factories()` | Call `register_ui_factories()` after managers |
| "Factory for X previously failed" | Factory threw exception, container cached failure | Call `reset_container()` and reinitialize |

---

## 2. Extraction Flows

### 2.1 VRAM Extraction

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
│ extract_from_vram()        │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ VRAMService                │  core/services/vram_service.py
│ extract_from_vram()        │
│ _extract_palettes()        │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ SpriteExtractor            │  core/extractor.py
│ load_vram()                │
│ extract_tiles()            │
│ _decode_4bpp_tile()        │
└────────────────────────────┘
         │
         ▼
     PNG output / Preview display
```

### 2.2 ROM Extraction

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
│ extract_from_rom()         │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ROMExtractor               │  core/rom_extractor.py
│ extract_sprite_from_rom()  │
│ _decompress_sprite_data()  │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ HALProcessPool             │  core/hal_compression.py
│ decompress()               │  Calls external 'exhal' binary
└────────────────────────────┘
         │
         ▼
     PNG output / Preview display
```

---

## 3. MainWindow User Action Flows

### 3.1 Extract Button Click

```
User clicks "Extract" button
         │
         ▼
MainWindow.on_extract_clicked()
         │
         ├── VRAM tab active → _handle_vram_extraction()
         │   ├── Get params from extraction_panel
         │   ├── Disable extract button
         │   └── Call controller.start_extraction(params)
         │
         └── ROM tab active → _handle_rom_extraction()
             ├── Get params from rom_extraction_panel
             ├── Validate via CoreOperationsManager
             └── Call controller.start_rom_extraction(params)
                      │
                      ▼
              Controller creates Worker
                      │
                      ▼
              Worker emits signals:
              ├── progress → status updates
              ├── finished → MainWindow.extraction_complete()
              └── error → MainWindow.extraction_failed()
```

### 3.2 ROM File Loading

```
User clicks "Browse ROM"
         │
         ▼
ROMExtractionPanel._browse_rom()
         │
         ▼
QFileDialog.getOpenFileName()
         │
         ▼
_load_rom_file(rom_path)
         │
         ├── Validate ROM exists
         ├── Store rom_path, calculate rom_size
         ├── Start header loading worker
         │   └── HeaderLoadWorker runs in background
         │       ├── finished → _on_header_loaded()
         │       └── error → _on_header_load_error()
         └── Emit files_changed signal
                  │
                  ▼
         MainWindow._on_rom_files_changed()
```

### 3.3 Signal Connection Map

| Signal | Source | Handler | Purpose |
|--------|--------|---------|---------|
| `files_changed` | extraction_panel | `_on_files_changed` | VRAM files updated |
| `extraction_ready` | extraction_panel | `_on_vram_extraction_ready` | Enable/disable extract |
| `files_changed` | rom_extraction_panel | `_on_rom_files_changed` | ROM files updated |
| `preview_ready` | controller | `_on_controller_preview_ready` | Show preview |
| `extraction_complete` | controller | `extraction_complete` | Handle completion |

---

## 4. Configuration Flow

### 4.1 Settings Files

| File | Purpose |
|------|---------|
| `.spritepal_settings.json` | Production settings |
| `.spritepal-test_settings.json` | Unit test settings |
| `.spritepal-uitest_settings.json` | UI test settings |

### 4.2 Configuration Load Flow

```
Application Launch
         │
         ▼
┌────────────────────────────┐
│ ConfigurationService       │  Early load for feature flags
│ Load feature flags         │  BEFORE managers initialized
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ManagerRegistry            │  core/managers/registry.py
│ initialize_managers()      │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ SessionManager             │  core/managers/session_manager.py
│ _load_settings()           │  Loads JSON settings
│ _merge_with_defaults()     │  Fills missing values
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ApplicationStateManager    │  Emits workflow_state_changed
│                            │  UI components listen to this
└────────────────────────────┘
```

### 4.3 Settings Access Pattern

```python
from core.managers.application_state_manager import ApplicationStateManager
from core.di_container import inject

# Settings are now part of ApplicationStateManager
app_state = inject(ApplicationStateManager)
value = app_state.settings.get("some_setting", default_value)
```

**Note:** `SettingsManagerProtocol` has been consolidated into `ApplicationStateManager`. Use the concrete class directly.

---

## 5. Error Flow

### 5.1 Exception Hierarchy

```
Exception
    └── ManagerError (base for all SpritePal errors)
            ├── ExtractionError
            ├── InjectionError
            ├── SessionError
            ├── ValidationError
            ├── PreviewError
            ├── FileOperationError
            ├── NavigationError
            └── CacheError
                    ├── CacheCorruptionError
                    └── CachePermissionError
```

Defined in: `core/exceptions.py`

### 5.2 Error Propagation

```
Exception occurs in core layer
         │
         ▼
┌────────────────────────────┐
│ Service/Manager Layer      │  Catches, logs, optionally re-raises
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ErrorHandler               │  ui/common/error_handler.py
│ (Thread-safe)              │  Routes errors to appropriate UI
└────────────────────────────┘
         │
         ▼
     User sees error message
```

---

## 6. Preview Generation Flow

```
Sprite data loaded
         │
         ▼
┌────────────────────────────┐
│ PreviewCoordinator         │  ui/managers/preview_coordinator.py
│ generate_preview()         │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ PreviewGenerator           │  core/services/preview_generator.py
│ generate()                 │
│ _apply_palette()           │
│ _scale_image()             │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ BatchThumbnailWorker       │  ui/workers/batch_thumbnail_worker.py
│ run()                      │  Background thread for batch generation
└────────────────────────────┘
         │
         ▼
     QPixmap ready for display
```

---

## 7. Injection Flow

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
│ CoreOperationsManager      │  core/managers/core_operations_manager.py
│ inject_sprite()            │
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ InjectionWorker            │  ui/workers/injection_worker.py
│ run()                      │  Background thread
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

---

## Quick Reference

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

*Last updated: December 24, 2025 (Updated for consolidated managers)*
