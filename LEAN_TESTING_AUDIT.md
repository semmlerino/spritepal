# Lean Testing Audit Report

## Executive Summary
The `tests/` suite is generally well-structured but suffers from "Identity Crisis" in several files, where Unit and Integration tests are mixed, leading to confusion and potential maintenance bloat. UI tests are over-mocked, testing framework internals (like `QComboBox`) rather than business logic.

**Potential Reductions:**
- **Execution Time:** ~15-20% by consolidating integration tests and reducing redundant "Real HAL" invocations.
- **Maintenance Burden:** ~25% by removing brittle UI-widget mocks and unifying ROM injection tests.

## 1. Dead Weight & Redundancy

The following tests provide overlapping coverage or low value:

| Test File | Issue | Recommendation |
| :--- | :--- | :--- |
| `tests/integration/test_palette_injection.py` | Fully redundant with `tests/unit/core/test_rom_injector.py` (which contains integration logic). | **REMOVE** (Merge unique cases into `test_rom_injector.py`) |
| `tests/unit/core/test_rom_injector.py` | Contains a hidden `TestROMInjectorIntegration` class. | **SPLIT** move integration class to `tests/integration/` |
| `tests/integration/test_rom_injection_settings.py` | Tests `InjectionDialog` widgets to verify settings persistence. High maintenance, low value. | **REWRITE** as `test_persistence_logic.py` targeting `CoreOperationsManager` directly. |
| `tests/integration/test_parallel_sprite_finder.py` | Misnamed. It heavily mocks `SpriteFinder`, making it a Unit test for the Parallel Orchestrator. | **RENAME** to `tests/unit/core/test_parallel_orchestrator.py`. |

## 2. Refactoring Suggestions

### A. Consolidate ROM Injection Logic
Currently, injection logic is tested across `tests/unit/core/test_rom_injector.py`, `tests/integration/test_palette_injection.py`, and `tests/integration/test_rom_injection_settings.py`.

**Action:**
1.  Extract `TestROMInjectorIntegration` from `tests/unit/core/test_rom_injector.py`.
2.  Merge `tests/integration/test_palette_injection.py` into it.
3.  Create `tests/integration/test_rom_injection_workflow.py` as the single source of truth for "Write to ROM" integration tests.

### B. Simplify Persistence Testing
`tests/integration/test_rom_injection_settings.py` mocks complex UI interactions just to see if a dictionary was saved.

**Action:**
1.  Delete `tests/integration/test_rom_injection_settings.py`.
2.  Enhance `tests/integration/test_core_operations_manager.py` to cover `save_rom_injection_settings` with 2-3 focused test cases verifying the `settings_manager` state changes.

### C. Unify Sprite Finder Tests
`tests/unit/test_sprite_finder.py` contains `TestSpriteFinderRealHAL` (Integration).

**Action:**
1.  Move `TestSpriteFinderRealHAL` to `tests/integration/test_sprite_finding_system.py`.
2.  Keep `tests/unit/test_sprite_finder.py` strictly for the pure Python logic (Candidate objects, filtering).

## 3. Preservation Plan

To maintain coverage while reducing bloat:

1.  **Shift Left**: Move "Settings Persistence" validation from UI tests (Dialogs) to Manager tests (`CoreOperationsManager`).
2.  **Explicit Marking**: Ensure all tests requiring `exhal`/`inhal` binaries are marked `@pytest.mark.real_hal` (currently inconsistent).
3.  **Controller Testing**: Prefer testing `ui/controllers/` over `ui/dialogs/`. Dialog tests should only verify signal wiring, not business logic.

## 4. Implementation Checklist

- [ ] **Delete** `tests/integration/test_palette_injection.py`
- [ ] **Refactor** `tests/integration/test_core_operations_manager.py` to include injection settings persistence.
- [ ] **Delete** `tests/integration/test_rom_injection_settings.py`.
- [ ] **Move** `TestROMInjectorIntegration` class from `tests/unit/core/test_rom_injector.py` to `tests/integration/test_rom_injection_workflow.py`.
