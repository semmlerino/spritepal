# Recommended Service Extractions

**Status:** Active TODO list
**Last verified:** January 2026

These service extractions follow the pattern established in Phase 2 (MesenCaptureSync) and Phase 3 (LibraryService) refactoring.

---

## Current State

**ROMWorkflowController:** 85 methods / ~3,200 lines

---

## Completed Extractions

| Phase | Service | Methods Extracted | Location |
|-------|---------|-------------------|----------|
| 1 | Error handling in file_dialogs.py | 4 methods | `ui/dialogs/file_dialogs.py` |
| 2 | MesenCaptureSync | 9 methods | `core/services/mesen_capture_sync.py` |
| 3 | LibraryService | 7 methods | `core/services/library_service.py` |

---

## High-Value Extractions (Priority Order)

### 1. ThumbnailService extraction (~7 methods)

**Methods to extract:**
- `_setup_thumbnail_worker()`
- `_on_thumbnail_ready()`
- `_request_capture_thumbnail()`
- `_request_all_asset_thumbnails()`
- `_generate_library_thumbnail()`
- `_load_library_thumbnail()`
- `_pil_to_qpixmap()` (utility, could be shared)

**Impact:** Cohesive subsystem for async thumbnail generation/caching. Would reduce controller to ~78 methods.

### 2. PreviewService extraction (~3 methods)

**Methods to extract:**
- `_on_preview_ready()`
- `_on_preview_error()`
- `_get_rom_data_for_preview()`

**Impact:** Encapsulate preview generation/error handling. Would reduce controller to ~75 methods.

**Note:** A separate `PreviewService` already exists for FrameMappingController (`ui/frame_mapping/services/preview_service.py`). The ROM workflow preview logic is different but could follow a similar pattern.

---

## Medium-Term Goals

- Extract similar services from `MainWindow` (currently ~2500 lines)
- Extract services from `CoreOperationsManager` (currently ~900 lines)
- Replace dict-based payloads with typed dataclasses
- Move toward target architecture (layered services)

---

## Removed from Plan

**StateTransitionService** — Originally proposed to extract `_set_state()`, `_transition_to_edit_mode()`, `_transition_to_preview_mode()`. These methods no longer exist in the controller (removed or refactored in prior work). No longer applicable.

---

*For historical context and full architecture analysis, see `archive/ASSESSMENT_IP_HISTORICAL.md`*
