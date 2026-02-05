# Test Suite Audit Report

**Date:** February 5, 2026
**Focus:** Redundancy, Bloat, and False Confidence

## Executive Summary

The SpritePal test suite is extensive but suffers from significant bloat and "framework testing." A large number of tests verify Qt's internal behavior or trivial getter/setter logic rather than application business logic. This increases maintenance cost (test run time, update friction) without increasing confidence in the application's correctness.

## 1. Tests to Remove (High Confidence)

These tests provide little to no value for the application's correctness and should be deleted immediately.

| Test File | Rationale |
| :--- | :--- |
| `tests/integration/test_qt_signal_slot_patterns.py` | **Framework Testing.** Explicitly states it tests "framework patterns... rather than application logic." Verifies that Qt signals work, which is the library's responsibility. |
| `tests/integration/test_qt_threading_patterns.py` | **Framework Testing.** Tests `QThread` subclassing, mutex locking, and event loops. We should assume the underlying framework works. |
| `tests/integration/test_ui_qt_safety.py` | **Pattern Enforcement.** Tests that `if container is not None:` is used instead of `if container:`. This is a coding standard to be enforced by linting/review, not a runtime test suite running 20+ checks. |
| `tests/ui/components/test_file_selector.py` | **Low Signal / Trivial.** Tests basic getters/setters (`get_path`, `set_path`) and that Qt widgets are initialized. |
| `tests/ui/components/test_hex_offset_input.py` | **Low Signal / Trivial.** Tests basic properties of a custom widget that are largely just proxying Qt methods. |
| `tests/integration/test_base_manager.py` | **Redundant Abstraction.** Tests an abstract base class. Logic should be verified via the concrete implementations (e.g., `ExtractionManager`, `InjectionManager`) which are already tested. |

## 2. Tests to Merge (Consolidation)

These areas have overlapping scope and should be consolidated to reduce "split brain" testing.

| Primary Target | Source(s) to Merge In | Rationale |
| :--- | :--- | :--- |
| `tests/integration/test_memory_management.py` (Create New) | `tests/integration/test_memory_leak_detection.py`<br>`tests/integration/test_memory_management_integration.py` | Both files test memory leaks, weak references, and cleanup. Consolidate into a single, authoritative memory test suite. |
| `tests/integration/test_rom_workflow.py` | `tests/integration/test_rom_loading_workflow.py`<br>`tests/integration/test_rom_extractor.py` | `test_rom_loading_workflow.py` tests the UI aspect of loading, while `test_rom_extractor.py` tests the logic. The boundaries are blurred. Ensure UI tests mock the extractor logic, and logic tests don't touch UI. |
| `tests/integration/test_dialog_integration.py` (Rename) | `tests/integration/test_dialog_real_integration.py`<br>`tests/unit/ui/dialogs/` | The "real" integration tests were created to replace mocked unit tests. If the unit tests in `tests/unit/ui/dialogs/` cover the same paths using mocks, delete the unit tests and keep the "real" integration tests as they provide higher confidence. |

## 3. Renaming & Cleanup

| Current File | Action | Rationale |
| :--- | :--- | :--- |
| `tests/integration/test_main_window_state_integration_real.py` | Rename to `test_main_window_integration.py` | The `_real` suffix implies a `_mock` version exists. If the mock version is gone, drop the suffix. |
| `tests/infrastructure/test_thread_safe_test_image.py` | **Flag for Review** | This tests a *test utility* (`ThreadSafeTestImage`). While good practice for complex helpers, ensure it doesn't grow into a project of its own. |

## 4. Coverage Gaps & False Confidence

*   **UI Logic vs. Qt Behavior:** A significant portion of "UI tests" are verifying that `setText()` updates the text property. True UI logic tests should focus on:
    *   **Signals:** "When I click this, does that signal emit with the right data?"
    *   **State:** "When I set this property, does the widget enable/disable the correct children?"
    *   **Data Binding:** "Does the view correctly reflect the model state?"
    *   *Action:* Refactor UI tests to focus on these interactions, removing checks for standard Qt behavior.

*   **Mocking Depth:** The existence of `_real.py` tests suggests that previous tests relied too heavily on mocks, hiding integration bugs.
    *   *Recommendation:* Prefer "sociable" unit tests (using real value objects and helpers) over "solitary" unit tests (mocking everything) for the core domain. Keep mocks at the I/O boundaries (Filesystem, Mesen2 API).

## 5. Action Plan

1.  **Delete** the files listed in Section 1.
2.  **Consolidate** memory tests into `tests/integration/test_memory_management.py`.
3.  **Rename** `test_main_window_state_integration_real.py` to `test_main_window_integration.py`.
4.  **Review** `tests/unit/ui/dialogs/` and delete tests fully covered by `tests/integration/test_dialog_real_integration.py`.

This cleanup will significantly reduce noise and make the test suite a more reliable indicator of *application* health.
