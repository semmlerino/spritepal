# Test Suite Audit & Refactoring Plan

**Date:** January 21, 2026
**Scope:** `tests/` directory (Unit, Integration, UI)

## 1. Executive Summary
The test suite suffers from **significant redundancy in the "Integration" layer**, particularly around Manager classes where wrapper methods are tested separately from the underlying logic they wrap. There is also a category of **"Static Analysis as Tests"** (e.g., checking for `terminate()` calls via regex) that belongs in a linter or pre-commit hook, not `pytest`.

**Key Stats:**
- **High Redundancy:** `CoreOperationsManager`, `ExtractionManager`, and `InjectionManager` tests.
- **Low Signal:** Constant validation tests and trivial "assert object exists" checks.
- **False Confidence:** Some unit tests mock filesystem interactions so heavily they validate the mock, not the code.

---

## 2. Audit & Recommendations by Category

### A. Core Operations & Managers (High Redundancy)
*Current State:* `CoreOperationsManager` is the central facade, but `ExtractionManager` and `InjectionManager` have their own overlapping test files.
*Behavior Covered:* Extract, Inject, Validation.

| Test File | Diagnosis | Recommendation |
| :--- | :--- | :--- |
| `tests/integration/test_extraction_manager.py` | **Redundant**. Tests logic already covered in `test_core_operations_manager.py` or `test_rom_extractor.py`. | **Merge** unique edge cases into `test_core_operations_manager.py`, then **Remove**. |
| `tests/integration/test_injection_manager.py` | **Redundant**. Wrapper tests for injection logic. | **Merge** unique edge cases into `test_core_operations_manager.py`, then **Remove**. |
| `tests/integration/test_core_operations_manager.py` | **Keeper**. This should be the single source of truth for high-level operation integration. | **Rewrite** to include the merged cases from above. |

### B. ROM Extraction & HAL Logic (Split Personality)
*Current State:* Logic is split between "unit" tests (which often do I/O) and "integration" tests (which do the same I/O).

| Test File | Diagnosis | Recommendation |
| :--- | :--- | :--- |
| `tests/unit/test_rom_extractor_logic.py` | **Confused Identity**. Contains integration-style tests that overlap with `test_rom_extractor.py`. | **Merge** into `tests/integration/test_rom_extractor.py`. |
| `tests/unit/test_constants_validation.py` | **Low Signal**. Validates that constants equal themselves. | **Remove**. |
| `tests/unit/test_extraction_audit_fixes.py` | **High Value**. Tests specific failure modes (timeouts, compression ratios). | **Keep** as is (or rename to `test_extraction_safety.py`). |

### C. UI & Workflow (Signal vs. Noise)
*Current State:* Good recent move to "Real Component" testing, but older TDD artifacts remain.

| Test File | Diagnosis | Recommendation |
| :--- | :--- | :--- |
| `tests/ui/test_revert_desync.py` | **Valuable**. Covers desync bugs in revert workflow. | **Keep**. |
| `tests/integration/test_worker_manager.py` | **Mixed**. Functional tests are good; "Meta-tests" (scanning code for strings) are bad. | ✅ **DONE**. Static analysis tests moved to `scripts/lint_safety.py`. |

> **Audit Corrections:** Original audit referenced `test_mode_switch_repro.py` and `test_ui_audit_fixes.py` which do not exist. The desync testing is actually in `test_revert_desync.py`.

---

## 3. Mapping Tests to Core Behaviors

| Core Behavior | Current Coverage Source | Status | Action |
| :--- | :--- | :--- | :--- |
| **ROM Parsing** | `test_rom_extractor.py`, `test_hal_parser.py` | **Good** | Consolidate scattered unit tests into these two. |
| **Sprite Editing** | `tests/ui/test_editor_*.py` | **Fragmented** | Keep distinct, but ensure they use `isolated_data_repository`. |
| **Injection** | `test_rom_injector.py`, `test_injection_manager.py` | **Duplicated** | Drop the manager wrapper tests; rely on the injector tests + 1-2 E2E tests in `CoreOps`. |
| **State/Config** | `test_app_state_manager.py` | **OK** | Ensure it tests persistence, not just in-memory dicts. |

---

## 4. Coverage Gaps & Risks

1.  **Concurrent ROM Access:**
    - *Risk:* Usage of `shutil` and file handles is tested sequentially.
    - *Gap:* No tests ensure the UI handles a locked ROM file gracefully (e.g., if Mesen 2 has it open).

2.  **Large ROM Types (ExHiROM):**
    - *Risk:* Most tests use small dummy files.
    - *Gap:* Addressing logic for >4MB ROMs is theoretically covered but practically under-tested in integration.

3.  **Mesen 2 Integration:**
    - *Risk:* heavily mocked.
    - *Gap:* The actual Lua-to-Python bridge is difficult to test without a running emulator, leading to "mock confidence."

## 5. Proposed Action Plan

1.  ✅ **Purge Low-Hanging Fruit:** Delete `test_constants_validation.py` and the static analysis tests inside `test_worker_manager.py`. **DONE**
2.  ✅ **Consolidate Managers:** Remove duplicate validation tests from `ExtractionManager` and `InjectionManager` test files. Unique edge cases retained. **DONE**
3.  ✅ **Unify Extractor Tests:** Merge key tests from `test_rom_extractor_logic.py` into `test_rom_extractor.py`. **DONE**
4.  ✅ **Linting Script:** Created `scripts/lint_safety.py` to handle the "check for `.terminate()` calls" requirement. **DONE**

---

## 6. Refactoring Summary (Completed January 21, 2026)

| Action | Files Changed | Tests Removed | Notes |
| :--- | :--- | :--- | :--- |
| Delete constants validation | `tests/unit/test_constants_validation.py` | 12 | Tests validated constants equal themselves |
| Extract static analysis | `tests/integration/test_worker_manager.py` | 2 | Moved to `scripts/lint_safety.py` |
| Merge ROM extractor tests | `tests/unit/test_rom_extractor_logic.py` → `tests/integration/test_rom_extractor.py` | ~18 (moved) | Integration tests merged, helper functions retained |
| Remove stub tests | `tests/integration/test_injection_manager.py` | 3 | Empty `pass` stubs provided false confidence |
| Consolidate extraction validation | `tests/integration/test_extraction_manager.py` | 8 | Duplicated `test_core_operations_manager.py` coverage |
| Consolidate injection validation | `tests/integration/test_injection_manager.py` | 5 | Duplicated `test_core_operations_manager.py` coverage |

**Estimated Total Tests Removed:** ~30+ redundant/low-value tests
