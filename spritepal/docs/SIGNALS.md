# SpritePal Signal Reference

This document lists all Qt signals in the application, organized by source component.

## Core Manager Signals

### CoreOperationsManager (`core/managers/core_operations_manager.py`)

**Extraction signals:**
| Signal | Payload | When emitted |
|--------|---------|--------------|
| `extraction_progress` | `str` | Progress message during extraction |
| `extraction_warning` | `str` | Partial success warning |
| `preview_generated` | `(object, int)` | QPixmap and offset after preview generation |
| `palettes_extracted` | `dict` | Palette data extracted from sprite |
| `active_palettes_found` | `list[int]` | List of non-black palette indices |
| `files_created` | `list[str]` | Paths of extracted files |

**Injection signals:**
| Signal | Payload | When emitted |
|--------|---------|--------------|
| `injection_progress` | `str` | Progress message during injection |
| `injection_finished` | `(bool, str)` | Success flag and message |
| `compression_info` | `dict` | Compression statistics |
| `progress_percent` | `int` | 0-100 for progress bars |

**Cache signals:**
| Signal | Payload | When emitted |
|--------|---------|--------------|
| `cache_operation_started` | `(str, str)` | Operation type, cache key |
| `cache_hit` | `(str, float)` | Cache key, time saved |
| `cache_miss` | `str` | Cache key |
| `cache_saved` | `(str, int)` | Cache key, size in bytes |

### ApplicationStateManager (`core/managers/application_state_manager.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `state_changed` | `(str, dict)` | Category and data when any state changes |
| `workflow_state_changed` | `(object, object)` | Old and new workflow states |
| `session_changed` | `()` | Session data modified |
| `files_updated` | `dict` | File paths changed |
| `settings_saved` | `()` | Settings persisted to disk |
| `session_restored` | `dict` | Session loaded from disk |
| `cache_stats_updated` | `dict` | Cache metrics updated |
| `current_offset_changed` | `int` | ROM offset selection changed |
| `preview_ready` | `(int, QImage)` | Offset and preview image |

### BaseManager (`core/managers/base_manager.py`)

All managers inherit these signals:
| Signal | Payload | When emitted |
|--------|---------|--------------|
| `error_occurred` | `str` | Any error during operation |
| `warning_occurred` | `str` | Non-fatal warning |
| `operation_started` | `str` | Operation name when starting |
| `operation_finished` | `str` | Operation name when complete |
| `progress_updated` | `(str, int, int)` | Operation, current, total |

### SpritePresetManager (`core/managers/sprite_preset_manager.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `preset_added` | `str` | Preset name added |
| `preset_removed` | `str` | Preset name removed |
| `preset_updated` | `str` | Preset name updated |
| `presets_loaded` | `()` | Presets loaded from disk |
| `presets_imported` | `int` | Count of imported presets |

---

## Controller Signals (`core/controller.py`)

**Status signals:**
| Signal | Payload | When emitted |
|--------|---------|--------------|
| `status_message_changed` | `str` | Status bar text update |
| `status_message_timed` | `(str, int)` | Message and timeout (ms) |

**Preview signals:**
| Signal | Payload | When emitted |
|--------|---------|--------------|
| `preview_ready` | `(object, int)` | QPixmap and tile count |
| `preview_updated` | `(object, int)` | Preview update without reset |
| `grayscale_image_ready` | `object` | PIL Image for palette work |
| `preview_info_changed` | `str` | Info text update |
| `preview_cleared` | `()` | Clear preview request |

**Data signals:**
| Signal | Payload | When emitted |
|--------|---------|--------------|
| `palettes_ready` | `dict` | Palette data ready |
| `active_palettes_ready` | `list[int]` | Active palette indices |
| `extraction_completed` | `list[str]` | Extracted file paths |
| `extraction_error` | `str` | Error message |

---

## Worker Signals

### BaseWorker (`core/workers/base.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `progress` | `(int, str)` | Progress percent and message |
| `error` | `(str, Exception)` | Error message and exception |
| `warning` | `str` | Warning message |
| `operation_finished` | `(bool, str)` | Success flag and message |

### ExtractionWorker (`core/workers/specialized.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `preview_ready` | `(object, int)` | Image and tile count |
| `preview_image_ready` | `object` | PIL image |
| `palettes_ready` | `dict` | Palette data |
| `active_palettes_ready` | `list` | Active indices |
| `extraction_finished` | `list` | Extracted files |

### InjectionWorker (`core/workers/specialized.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `progress_percent` | `int` | 0-100 progress |
| `compression_info` | `dict` | Stats dictionary |
| `injection_finished` | `(bool, str)` | Success and message |

### ScanWorker (`core/workers/specialized.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `item_found` | `dict` | Found sprite info |
| `scan_stats` | `dict` | Scan statistics |
| `scan_progress` | `(int, int)` | Current and total |
| `scan_finished` | `bool` | Success flag |
| `cache_status` | `str` | Cache status message |
| `cache_progress` | `int` | Cache save progress |

---

## UI Component Signals

### MainWindow (`ui/main_window.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `extract_requested` | `()` | User clicks Extract |
| `open_in_editor_requested` | `str` | Path to open externally |
| `arrange_rows_requested` | `str` | Path for row arrangement |
| `arrange_grid_requested` | `str` | Path for grid arrangement |
| `inject_requested` | `()` | User clicks Inject |
| `extraction_completed` | `list` | After successful extraction |
| `extraction_error_occurred` | `str` | After extraction failure |

### ExtractionPanel (`ui/extraction_panel.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `file_dropped` | `str` | File path dropped on panel |
| `files_changed` | `()` | Input files changed |
| `extraction_ready` | `(bool, str)` | Ready state and reason |
| `offset_changed` | `int` | VRAM offset changed |
| `mode_changed` | `int` | Extraction mode changed |

### WorkerOrchestrator (`ui/rom_extraction/worker_orchestrator.py`)

| Signal | Payload | When emitted |
|--------|---------|--------------|
| `header_loaded` | `dict` | ROM header parsed |
| `header_error` | `str` | Header parse failed |
| `sprite_locations_loaded` | `list` | Known sprite list |
| `scan_progress` | `(int, int, str)` | Progress with message |
| `sprite_found` | `dict` | Single sprite found |
| `scan_complete` | `(list, bool)` | Results and cache flag |
| `scan_error` | `str` | Scan failed |

---

## Common Connection Patterns

### Connecting to manager signals
```python
from core.di_container import inject
from core.protocols.manager_protocols import ExtractionManagerProtocol

manager = inject(ExtractionManagerProtocol)
manager.extraction_progress.connect(self._on_progress)
manager.files_created.connect(self._on_files_created)
```

### Cross-thread connections
```python
# Use QueuedConnection for signals crossing thread boundaries
worker.finished.connect(
    self._on_worker_finished,
    Qt.ConnectionType.QueuedConnection
)
```

### Cleanup on widget destruction
```python
def closeEvent(self, event):
    # Disconnect to prevent signals to deleted objects
    self._manager.extraction_progress.disconnect(self._on_progress)
    super().closeEvent(event)
```

---

## Signal Naming Conventions

| Pattern | Meaning |
|---------|---------|
| `*_ready` | Data is available for use |
| `*_changed` | State has been modified |
| `*_requested` | User action needs handling |
| `*_completed` / `*_finished` | Operation done |
| `*_error` / `*_failed` | Operation failed |
| `*_progress` | Intermediate status update |

---

*To add a new signal: Define it on the class, document it here, and update tests.*
