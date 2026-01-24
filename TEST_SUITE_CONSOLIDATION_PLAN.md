# Test Suite Consolidation & Refactor Plan

**Date:** January 24, 2026
**Objective:** Address structural fragmentation, reduce redundancy, and improve test clarity following the January 2026 audit.

## 1. Executive Summary
The SpritePal test suite is comprehensive (3400+ tests) and fast (~60s), indicating good performance. However, it suffers from structural fragmentation and specific pockets of high redundancy, particularly in UI widget testing and legacy integration paths.

### Key Issues Identified
1.  **Directory Fragmentation:** Tests are split between `tests/` and `ui/sprite_editor/tests/`, obscuring the full scope of coverage.
2.  **Component Redundancy:** `HexOffsetInput` and `HexLineEdit` represent duplicated UI logic with duplicated test suites.
3.  **Granularity:** Repository tests are overly granular, inflating test counts without adding significant signal.
4.  **Legacy Artifacts:** "Redesign" integration tests coexist with older workflow tests, potentially testing dead code paths.

---

## 2. Detailed Findings & Recommendations

### 2.1 UI Component Duplication
-   **Finding:** Two hex input widgets exist: `HexOffsetInput` (older, composite) and `HexLineEdit` (newer, atomic).
-   **Redundancy:** Both suites extensively test hex string parsing, prefix handling (`0x`, `$`), and validation logic.
-   **Recommendation:** Refactor `HexOffsetInput` to consume `HexLineEdit`. Consolidate parsing/validation tests into `test_hex_line_edit.py`.

### 2.2 Repository Test Granularity
-   **Finding:** `tests/unit/core/repositories/test_frame_mapping_repository.py` uses separate classes for every migration version and edge case.
-   **Recommendation:** Merge migration classes into a single `TestRepositoryMigrations` class. Merge edge case classes into `TestRepositoryErrorHandling`.

### 2.3 Directory Structure
-   **Finding:** A significant chunk of UI tests resides in `ui/sprite_editor/tests/`, outside the main `tests/` root.
-   **Recommendation:** Move `ui/sprite_editor/tests/` to `tests/ui/sprite_editor/`.

### 2.4 Integration Test Overlap
-   **Finding:** `tests/integration/test_rom_workflow_integration.py` overlaps with `ui/sprite_editor/tests/test_redesign_integration.py`.
-   **Recommendation:** Audit `test_rom_workflow_integration.py` and deprecate or merge into `test_redesign_integration.py`.

### 2.5 Excessive Concurrency Testing
-   **Finding:** `tests/unit/core/services/test_lru_cache.py` contains redundant thread-safety scenarios.
-   **Recommendation:** Keep high-level stress tests; remove implementation-specific scenarios (e.g., RLock reentrancy).

### 2.6 Misleading Naming
-   **Finding:** `test_error_handler_comprehensive.py` only covers the GUI handler.
-   **Recommendation:** Rename to `test_gui_error_handler_integration.py`.

---

## 3. Refactor Phases

### Phase 1: Directory Consolidation ✅ COMPLETED (January 24, 2026)
-   ✅ Moved `ui/sprite_editor/tests/` to `tests/ui/sprite_editor/`.
-   ✅ Updated `pyproject.toml` `testpaths` to point only to `tests/`.
-   ✅ Updated imports in moved files.

### Phase 2: Repository & Cache Cleanup
-   Consolidate classes in `test_frame_mapping_repository.py`.
-   Prune redundant scenarios in `test_lru_cache.py`.
-   Rename `test_error_handler_comprehensive.py` -> `test_gui_error_handler.py`.

### Phase 3: Integration Audit
-   Compare `test_rom_workflow_integration.py` and `test_redesign_integration.py`.
-   Skip or remove legacy UI integration paths.

### Phase 4: Component & Test De-duplication (High Impact)
-   Refactor `HexOffsetInput` (code) to use `HexLineEdit`.
-   Prune `test_hex_offset_input.py` to focus on integration, removing redundant parsing tests already covered by `test_hex_line_edit.py`.

---

## 4. Execution Order
1.  **Phase 1** (Directory move) - Structural.
2.  **Phase 2** (Repository/Cache cleanup) - Test-only.
3.  **Phase 3** (Integration cleanup) - Review-heavy.
4.  **Phase 4** (Component refactor) - Code changes + Test pruning.

---

## 5. Metrics & Targets

| Metric | Current | Target | Status |
| :--- | :--- | :--- | :--- |
| **Test Count** | 3459 | ~3000 (-15%) | In progress |
| **Execution Time** | 60s | < 60s | On track |
| **Test Roots** | ~~2~~ → 1 | 1 | ✅ Complete |

## Conclusion
The suite is healthy but needs pruning and structural organization. ~~Consolidating the test directory structure is the highest priority for maintainability.~~ **Phase 1 complete (January 24, 2026):** Test directory structure consolidated to single root. Remaining phases focus on test cleanup and redundancy elimination.
