# Test Suite Audit Report - January 22, 2026

## Executive Summary
The test suite is comprehensive but suffers from fragmentation and redundancy, particularly in ROM injection and UI workflow testing. "Zombie" integration tests (heavy mocking, low signal) coexist with modern, real-component integration tests. Consolidating these will reduce maintenance burden and improve test discovery.

## 1. ROM Injection Redundancy
**Findings:**
- `tests/integration/test_rom_injection.py` is a low-value test file. It claims to be an integration test but relies heavily on mocks (`mock_hal`, mocked `sprite_config_loader`) and tests internal `ROMInjector` methods (`read_rom_header`, `calculate_checksum`) that are better suited for unit tests.
- `tests/unit/core/test_rom_injector_boundaries.py` tests `ROMInjector` logic but is narrowly focused on boundary conditions.
- `tests/integration/test_injection_manager.py` tests the actual injection workflow with real components, making `test_rom_injection.py`'s workflow tests redundant.

**Recommendation:**
- **Action:** **Delete** `tests/integration/test_rom_injection.py`.
- **Action:** **Move** the `read_rom_header` and `checksum_calculation` tests from the deleted file into `tests/unit/core/test_rom_injector_boundaries.py`.
- **Action:** **Rename** `tests/unit/core/test_rom_injector_boundaries.py` to `tests/unit/core/test_rom_injector.py` to reflect its broadened scope as the primary unit test for `ROMInjector` logic.

## 2. UI Workflow Test Fragmentation
**Findings:**
- `ROMWorkflowController` is tested in two separate locations:
    - `tests/ui/integration/test_rom_workflow_integration.py`: Tests state transitions and signal flow (High Value).
    - `tests/ui/rom_extraction/test_rom_workflow_controller.py`: Tests specific regression scenarios (Mesen captures, thumbnails).
- The split between `ui/integration` and `ui/rom_extraction` is arbitrary and confusing.

**Recommendation:**
- **Action:** **Merge** `tests/ui/rom_extraction/test_rom_workflow_controller.py` into `tests/ui/integration/test_rom_workflow_integration.py`.
- **Action:** **Delete** the now-empty `tests/ui/rom_extraction` directory if possible.

## 3. Regression Test "Barnacles"
**Findings:**
- `tests/ui/test_shared_controller_bug.py` is a single-test file validating a fixed bug in `EditingController`.
- `tests/ui/integration/test_editing_controller_integration.py` is the main integration test for `EditingController`.

**Recommendation:**
- **Action:** **Merge** the test case from `tests/ui/test_shared_controller_bug.py` into `tests/ui/integration/test_editing_controller_integration.py` (rename it to `test_shared_controller_multiple_views`).
- **Action:** **Delete** `tests/ui/test_shared_controller_bug.py`.

## 4. Manager Test Overlap
**Findings:**
- `tests/integration/test_manager_integration.py` tests the "Extraction -> Injection" round-trip workflow (System Test).
- `tests/integration/test_injection_manager.py` tests the "Injection" workflow in isolation (Component Integration Test).
- Both test the "happy path" of injection.

**Recommendation:**
- **Action:** **Retain both**, but ensure `test_injection_manager.py` focuses on *injection-specific* edge cases (metadata validation, negative offsets, file permissions) rather than just repeating the happy path workflow covered by the system integration test.

## Summary of Operations

| Target File | Action | Destination / Notes |
| :--- | :--- | :--- |
| `tests/integration/test_rom_injection.py` | **DELETE** | Move logic tests to `tests/unit/core/test_rom_injector.py`. |
| `tests/unit/core/test_rom_injector_boundaries.py` | **RENAME** | Rename to `test_rom_injector.py` and expand scope. |
| `tests/ui/rom_extraction/test_rom_workflow_controller.py` | **MERGE** | Merge into `tests/ui/integration/test_rom_workflow_integration.py`. |
| `tests/ui/test_shared_controller_bug.py` | **MERGE** | Merge into `tests/ui/integration/test_editing_controller_integration.py`. |
| `tests/integration/test_rom_extractor.py` | **KEEP** | This is the Gold Standard for extraction testing. |
