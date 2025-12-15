# MainWindow Flow Documentation

## Overview

`MainWindow` (`ui/main_window.py`) is the primary UI coordinator with ~55 methods. This guide documents the key user action flows to help developers trace through the codebase.

## Architecture

```
MainWindow
    ├── tab_coordinator          # Manages ROM/VRAM tabs
    ├── extraction_panel         # VRAM extraction UI
    ├── rom_extraction_panel     # ROM extraction UI
    ├── preview_coordinator      # Preview display management
    ├── toolbar_manager          # Toolbar button states
    ├── status_bar_manager       # Status bar messages
    ├── output_settings_manager  # Output name, grayscale, metadata
    └── controller               # Business logic coordinator
```

## Flow 1: Extract Button Click

### VRAM Mode

```
User clicks "Extract" button (VRAM tab active)
         ↓
MainWindow.on_extract_clicked()
         ↓
_handle_vram_extraction()
         ↓
├── Get params from extraction_panel.get_extraction_params()
├── Disable extract button (toolbar_manager)
├── Show "Extracting..." status
└── Call controller.start_extraction(params)
         ↓
Controller creates ExtractionWorker
         ↓
Worker emits signals:
├── progress → Controller → MainWindow (status updates)
├── finished → Controller.extraction_complete()
│   └── MainWindow.extraction_complete()
│       ├── Store extracted_files
│       ├── Enable post-extraction buttons
│       └── Emit extraction_completed signal
└── error → Controller.extraction_failed()
    └── MainWindow.extraction_failed()
        └── Show error message
```

### ROM Mode

```
User clicks "Extract" button (ROM tab active)
         ↓
MainWindow.on_extract_clicked()
         ↓
_handle_rom_extraction()
         ↓
├── Get params from rom_extraction_panel.get_extraction_params()
├── Validate via inject(ExtractionManagerProtocol).validate_extraction_params()
│   └── On validation error → Show QMessageBox, return early
├── Store output_path
├── Disable extract button
├── Show "Extracting from ROM..." status
└── Call controller.start_rom_extraction(params)
         ↓
Controller creates ROMExtractionWorker
         ↓
[Same signal flow as VRAM mode]
```

**Key Files:**
- `ui/main_window.py:402-408` - `on_extract_clicked()`
- `ui/main_window.py:471-503` - `_handle_rom_extraction()`
- `ui/main_window.py:678-705` - `extraction_complete()`
- `core/controller.py` - Controller extraction methods

## Flow 2: ROM File Loading

```
User clicks "Browse ROM" in ROMExtractionPanel
         ↓
ROMExtractionPanel._browse_rom()
         ↓
QFileDialog.getOpenFileName()
         ↓
User selects ROM file
         ↓
_load_rom_file(rom_path)
         ↓
├── Validate ROM exists
├── Store rom_path, calculate rom_size
├── Update rom_file_widget display
├── Start header loading worker (_start_header_loading)
│   └── HeaderLoadWorker runs in background
│       ├── finished → _on_header_loaded()
│       │   ├── Display ROM name
│       │   └── Enable sprite loading options
│       └── error → _on_header_load_error()
└── Emit files_changed signal
         ↓
MainWindow._on_rom_files_changed()
         ↓
├── Update status bar
└── Check if extraction is ready
```

**Key Files:**
- `ui/rom_extraction_panel.py:415-430` - `_browse_rom()`
- `ui/rom_extraction_panel.py:472-519` - `_load_rom_file()`
- `ui/main_window.py:529-548` - `_connect_signals()`

## Flow 3: Sprite Selection (ROM Mode)

```
User selects sprite from dropdown
         ↓
ROMExtractionPanel._on_sprite_changed(index)
         ↓
├── Get sprite location at index
├── Update state_manager with new offset
├── Show sprite preview in selector widget
└── Call _check_extraction_ready()
         ↓
├── If all params valid:
│   ├── Emit extraction_ready(True)
│   └── Update extraction button state
└── If params invalid:
    └── Emit extraction_ready(False)
         ↓
MainWindow._on_rom_extraction_ready(is_ready)
         ↓
toolbar_manager.set_extract_enabled(is_ready)
```

**Key Files:**
- `ui/rom_extraction_panel.py:866-908` - `_on_sprite_changed()`
- `ui/rom_extraction_panel.py:910-940` - `_check_extraction_ready()`

## Flow 4: Inject to VRAM

```
User clicks "Inject" button
         ↓
MainWindow.on_inject_clicked()
         ↓
├── Check _output_path exists
└── Emit inject_requested signal
         ↓
[External handler - typically opens InjectionDialog]
```

**Key Files:**
- `ui/main_window.py:428-431` - `on_inject_clicked()`
- `ui/injection_dialog.py` - InjectionDialog

## Flow 5: Manual Offset Dialog

```
User clicks "Manual Offset" button
         ↓
ROMExtractionPanel._open_manual_offset_dialog()
         ↓
├── Create ManualOffsetDialogSingleton.get_instance()
├── Configure dialog with current ROM data
├── Connect signals:
│   ├── offset_changed → _on_dialog_offset_changed()
│   └── sprite_found → _on_dialog_sprite_found()
└── Show dialog
         ↓
User adjusts offset in dialog
         ↓
Dialog emits offset_changed(new_offset)
         ↓
_on_dialog_offset_changed(offset)
         ↓
├── Update state_manager
└── Refresh preview
         ↓
User clicks "Apply"
         ↓
_add_selected_sprite()
         ↓
├── Add sprite to locations list
├── Update sprite selector
└── Close dialog
```

**Key Files:**
- `ui/rom_extraction_panel.py:591-667` - `_open_manual_offset_dialog()`
- `ui/dialogs/unified_manual_offset_dialog.py` - Dialog implementation

## Signal Connection Map

### MainWindow Signal Connections

| Signal | Source | Handler | Purpose |
|--------|--------|---------|---------|
| `files_changed` | extraction_panel | `_on_files_changed` | VRAM files updated |
| `extraction_ready` | extraction_panel | `_on_vram_extraction_ready` | Enable/disable extract |
| `mode_changed` | extraction_panel | `_on_extraction_mode_changed` | Switch mode display |
| `files_changed` | rom_extraction_panel | `_on_rom_files_changed` | ROM files updated |
| `extraction_ready` | rom_extraction_panel | `_on_rom_extraction_ready` | Enable/disable extract |
| `output_name_changed` | rom_extraction_panel | `_on_rom_output_name_changed` | Sync output name |
| `grayscale_toggled` | output_settings_manager | `_update_output_info_label` | Update display |
| `metadata_toggled` | output_settings_manager | `_update_output_info_label` | Update display |

### Controller Signal Connections

| Signal | Source | Handler | Purpose |
|--------|--------|---------|---------|
| `preview_ready` | controller | `_on_controller_preview_ready` | Show preview |
| `grayscale_ready` | controller | `_on_controller_grayscale_ready` | Show grayscale |
| `palettes_ready` | controller | `_on_controller_palettes_ready` | Update palette UI |
| `extraction_complete` | controller | `extraction_complete` | Handle completion |
| `extraction_failed` | controller | `extraction_failed` | Handle errors |

## State Management

### Key State Variables

| Variable | Location | Purpose |
|----------|----------|---------|
| `_output_path` | MainWindow | Current extraction output path |
| `_extracted_files` | MainWindow | List of extracted file paths |
| `rom_path` | ROMExtractionPanel | Currently loaded ROM |
| `sprite_locations` | ROMExtractionPanel | Available sprite offsets |
| `_manual_offset` | ROMExtractionPanel | User-specified offset |

### Button States

| Button | Enabled When |
|--------|--------------|
| Extract | `extraction_ready` signal emitted with `True` |
| Open Editor | After successful extraction (`_extracted_files` populated) |
| Arrange Rows | After successful extraction |
| Arrange Grid | After successful extraction |
| Inject | After successful extraction (`_output_path` set) |

## Debugging Tips

### Trace a Flow

Add logging at key points:
```python
import logging
logger = logging.getLogger(__name__)

def on_extract_clicked(self):
    logger.debug(f"Extract clicked, ROM tab: {self.tab_coordinator.is_rom_tab_active()}")
    # ...
```

### Check Signal Connections

```python
# In _connect_signals(), verify connections
print(f"Connected: {self.extraction_panel.files_changed.receivers()}")
```

### Verify State

```python
# After extraction
print(f"Output path: {self._output_path}")
print(f"Extracted files: {self._extracted_files}")
```

## See Also

- [architecture.md](architecture.md) - Layer structure
- [dependency_injection_guide.md](dependency_injection_guide.md) - How managers are obtained
- [dialog_development_guide.md](dialog_development_guide.md) - Dialog patterns
