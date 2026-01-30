# Recommended Service Extractions

**Status:** Active TODO list
**Source:** Extracted from ASSESSMENT_IP.MD Section F (January 2026)

These service extractions follow the pattern established in Phase 2 (MesenCaptureSync) and Phase 3 (LibraryService) refactoring.

---

## High-Value Extractions (Priority Order)

### 1. PreviewService extraction from `ROMWorkflowController` (~10 methods)

**Methods to extract:**
- `_on_preview_ready()`
- `_on_preview_error()`
- `_generate_preview_thumbnail()`

**Impact:** Would reduce controller to ~69 methods

### 2. ThumbnailService extraction from `ROMWorkflowController` (~8 methods)

**Methods to extract:**
- `_queue_thumbnail()`
- `_on_thumbnail_ready()`
- `_load_library_thumbnail()`

**Impact:** Cohesive subsystem for async thumbnail generation/caching

### 3. StateTransitionService extraction from `ROMWorkflowController`

**Methods to extract:**
- `_set_state()`
- `_transition_to_edit_mode()`
- `_transition_to_preview_mode()`

**Impact:** Encapsulate workflow state machine

---

## Medium-Term Goals

- Extract similar services from `MainWindow` (currently ~2500 lines)
- Extract services from `CoreOperationsManager` (currently ~900 lines)
- Replace dict-based payloads with typed dataclasses
- Move toward target architecture (layered services)

---

## Completed Refactoring (Reference)

| Phase | Service | Methods Extracted | Status |
|-------|---------|-------------------|--------|
| 1 | Error handling in file_dialogs.py | 4 methods | Done |
| 2 | MesenCaptureSync | 9 methods | Done |
| 3 | LibraryService | 7 methods | Done |

**Result:** ROMWorkflowController reduced from ~98 methods to ~79 methods

---

*For historical context and full architecture analysis, see `archive/ASSESSMENT_IP_HISTORICAL.md`*
