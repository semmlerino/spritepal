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
    │     Registers SERVICES as concrete classes:                   │
    │     • ConfigurationService                                    │
    │     • ROMCache (factory, lazy)                                │
    │     • ROMExtractor (factory, lazy)                            │
    │                          │                                    │
    │                          ▼                                    │
    │  2. Create ApplicationStateManager                            │
    │     • Handles: session, settings, state, history              │
    │     ⚠️ CRITICAL: Must be registered BEFORE CoreOperations     │
    │                          │                                    │
    │                          ▼                                    │
    │  3. Create SpritePresetManager                                │
    │     • Handles: user-defined sprite presets                    │
    │                          │                                    │
    │                          ▼                                    │
    │  4. Create CoreOperationsManager                              │
    │     • Handles: extraction, injection, palette, nav            │
    └───────────────────────────────────────────────────────────────┘
                    │
                    ▼
           Application Ready
```

### Dependency Chain

When managers are created:

```
ROMExtractor needs ROMCache
    └── ROMCache needs ApplicationStateManager (for settings)
            └── ✓ Already created (step 2)
```

### Common Initialization Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "AppContext not initialized" | Accessing managers before `create_app_context()` | Ensure `initialize_managers()` runs first |
| "ApplicationStateManager required first" | CoreOperationsManager created before ApplicationStateManager | Check manager creation order |

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
│ initialize_managers()      │  core/managers/__init__.py
│                            │  Creates managers in order
└────────────────────────────┘
         │
         ▼
┌────────────────────────────┐
│ ApplicationStateManager    │  core/managers/application_state_manager.py
│ _load_settings()           │  Loads JSON settings
│ _merge_with_defaults()     │  Fills missing values
│                            │  Emits workflow_state_changed
│                            │  UI components listen to this
└────────────────────────────┘
```

### 4.3 Settings Access Pattern

```python
from core.app_context import get_app_context

# Settings are part of ApplicationStateManager
app_state = get_app_context().application_state_manager
value = app_state.settings.get("some_setting", default_value)
```

**Note:** Settings functionality is integrated into `ApplicationStateManager`. Access via `get_app_context().application_state_manager`.

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
│ SmartPreviewCoordinator     │  ui/common/smart_preview_coordinator.py
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

## 5. Sprite Editor Tab and Mesen2 Integration

### 5.1 Embedded Sprite Editor Tab

The main SpritePal window has 3 extraction tabs:
- **Tab 0**: ROM Extraction
- **Tab 1**: VRAM Extraction
- **Tab 2**: Sprite Editor (embedded)

The Sprite Editor tab embeds the full 4-step workflow without menus/toolbar/statusbar:
1. Extract tab - Load sprites from ROM offset or VRAM dump
2. Edit tab - Modify sprite pixels and palettes
3. Inject tab - Repack modified sprites back to ROM or VRAM
4. Multi-Palette tab - Manage alternative palettes

**Modes:**
The editor has a **Mode Toggle** (ROM | VRAM) in the header:
- **ROM Mode**: Operates directly on ROM files using offsets (default for Mesen2 captures).
- **VRAM Mode**: Operates on emulator VRAM/CGRAM dumps.

```
SpriteEditTab (ui/sprite_edit_tab.py)
├── Header (Mode Toggle: ROM/VRAM)
├── MainController (from sprite_editor subsystem)
│   ├── ExtractionController
│   ├── EditingController
│   ├── InjectionController
│   └── PaletteController
└── Internal QTabWidget
    ├── ExtractTab
    ├── EditTab
    ├── InjectTab
    └── MultiPaletteTab
```

### 5.2 Jump-to-Offset from Mesen2 Captures

```
User double-clicks ROM offset in Recent Captures
         │
         ▼
ROMExtractionPanel._on_mesen2_offset_activated()
         │
         ▼
ROMExtractionPanel.open_in_sprite_editor.emit(offset)
         │
         ▼
MainWindow._on_open_in_sprite_editor(offset)
         │
         ├── Switch to Sprite Editor tab (index 2)
         │
         └── SpriteEditTab.jump_to_offset(offset)
             ├── Switch to ROM Mode
             ├── Switch to Extract subtab
             ├── Set offset in ExtractTab
             └── Emit status_message signal
```

### 5.3 Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+1` | Switch to ROM Extraction tab |
| `Ctrl+2` | Switch to VRAM Extraction tab |
| `Ctrl+3` | Switch to Sprite Editor tab |
| `F6` | Jump to last Mesen2 capture in Sprite Editor |

Implemented in `MainWindow.keyPressEvent()`.

### 5.4 Status Bar Mesen2 Indicator

The status bar shows Mesen2 watch status:
- Green dot `●` when log watcher is active
- Gray dot `●` when inactive

Updated via:
```
ROMExtractionPanel.mesen2_watching_changed.emit(bool)
       │
       ▼
MainWindow._connect_signals()
       │
       ▼
StatusBarManager.set_mesen2_watching(bool)
```

---

## Quick Reference

| Task | Primary File | Key Method |
|------|--------------|------------|
| VRAM extraction | `core/extractor.py` | `SpriteExtractor.extract_tiles()` |
| ROM extraction | `core/rom_extractor.py` | `ROMExtractor.extract_sprite_from_rom()` |
| HAL compression | `core/hal_compression.py` | `HALProcessPool.compress/decompress()` |
| Settings load | `core/managers/application_state_manager.py` | `ApplicationStateManager._load_settings()` |
| Error handling | `ui/common/error_handler.py` | `ErrorHandler.handle_error()` |
| Preview generation | `core/services/preview_generator.py` | `PreviewGenerator.generate()` |
| Manager access | `core/app_context.py` | `get_app_context()` |
| Dump file detection | `core/services/dump_file_detection_service.py` | `detect_related_files()`, `auto_detect_all()` |
| Extraction readiness | `core/services/extraction_readiness_service.py` | `check_vram_readiness()`, `check_rom_extraction_readiness()` |
| Sprite Editor embedding | `ui/sprite_edit_tab.py` | `SpriteEditTab.jump_to_offset()` |
| Mesen2 offset handling | `ui/rom_extraction_panel.py` | `ROMExtractionPanel._on_mesen2_offset_activated()` |

---

*Last updated: January 8, 2026 (Fixed PreviewCoordinator file path reference)*
