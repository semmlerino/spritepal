# Audit Report: SpritePal Test Suite Consolidation & Optimization (January 16, 2026)

This audit evaluates the current test suite (approx. 2440 tests) for redundancy, bloat, and false confidence. The suite is currently heavy on "signal wiring" and "framework smoke tests" that increase maintenance costs without providing unique behavioral confidence.

## 1. Redundant Framework & Infrastructure Smoke Tests
These tests primarily verify that Qt or Python works as intended, rather than testing SpritePal's business logic or UI behavior.

| Test File / Group | Recommendation | Rationale |
| :--- | :--- | :--- |
| `tests/integration/test_qt_infrastructure.py` | **Remove** | Only contains a test for `QApplication.instance()` being a singleton. Low signal. |
| `tests/integration/test_qt_signal_architecture.py` | **Rewrite / Merge** | `test_casting_preserves_functionality` and `test_signal_delivery_performance` are bloat. Keep only `test_thread_safety_signal_emission` and merge into `tests/integration/test_thread_safety_comprehensive.py`. |
| `tests/unit/test_app_context.py` | **Prune** | Remove `test_deprecated_functions_were_removed`. Tombstone tests are low value once a refactor is stable. |
| `tests/integration/test_ui_components_real.py` | **Remove** | `TestImageUtils` is identical to `TestPilToQPixmap` in `tests/unit/test_image_utils.py`. |

## 2. Redundant UI Signal "Contract" Tests
These tests verify that clicking a button emits a signal. These are brittle and redundant because any functional integration test that actually *uses* the UI will implicitly verify these signals.

| Test File / Group | Recommendation | Rationale |
| :--- | :--- | :--- |
| `tests/ui/integration/test_extract_tab_signals.py` | **Remove** | Redundant with `tests/integration/test_complete_ui_workflows_comprehensive.py`. |
| `tests/ui/integration/test_inject_tab_signals.py` | **Remove** | Redundant with `tests/integration/test_complete_ui_workflows_comprehensive.py`. |
| `tests/ui/integration/test_icon_toolbar_signals.py` | **Remove** | Redundant with functional UI tests. |
| `tests/ui/integration/test_palette_panel_signals.py` | **Remove** | Redundant with functional UI tests. |
| `tests/ui/integration/test_pixel_canvas_signals.py` | **Remove** | Redundant with functional UI tests. |

## 3. Over-Granular Integration Tests
Multiple small integration files test individual manager behaviors that are already covered by comprehensive workflow tests.

| Test File / Group | Recommendation | Rationale |
| :--- | :--- | :--- |
| `tests/integration/test_circular_dependency_fix.py` | **Remove** | The issue is fixed and `MainWindow` init is covered by almost every other UI test. |
| `tests/integration/test_error_handler.py` | **Merge** | Merge with `tests/integration/test_error_handler_thread_safety.py` into a single `tests/integration/test_error_handler_comprehensive.py`. |
| `tests/integration/test_decomp.py` | **Move/Refactor** | Requires a real ROM. Move to a `tests/manual/` directory or update to use a mocked ROM fixture to prevent constant skipping in CI. |
| `tests/integration/test_business_logic_mocked.py` | **Remove** | `TestVRAMExtractionWorkerMocked` is redundant with unit tests. `TestBusinessLogicOnly` is redundant with `tests/unit/test_palette_manager.py`. |

## 4. Logic & Constant Mapping
Address translation logic is currently buried in constant validation tests.

| Test File / Group | Recommendation | Rationale |
| :--- | :--- | :--- |
| `tests/unit/test_constants_validation.py` | **Split** | Extract SA-1, HiROM, and LoROM address translation tests into `tests/unit/test_address_translation.py`. The "powers of two" and "hex string" checks are low-signal sanity checks that can be significantly slimmed down. |

## 5. Mesen Integration Granularity
The Mesen integration has high test-file bloat.

| Test File / Group | Recommendation | Rationale |
| :--- | :--- | :--- |
| `tests/ui/rom_extraction/test_mesen2_integration.py` | **Merge** | Merge all `tests/ui/rom_extraction/test_mesen*.py` files into a single `tests/ui/integration/test_mesen_workflow.py`. The current separation increases overhead without increasing confidence. |

---

## Coverage Gap Analysis & False Confidence

1.  **False Confidence in Mocks:** `tests/ui/integration/test_rom_workflow_integration.py` relies heavily on `MockPreviewCoordinator`. While it tests the controller's logic, it provides zero confidence that the real `SmartPreviewCoordinator` behaves correctly. This should be rewritten to use the real coordinator with mocked file-system calls.
2.  **Redundant Coverage:** The `pil_to_qpixmap` function is tested in at least 3 different files (`test_image_utils.py`, `test_ui_components_real.py`, `test_business_logic_mocked.py`). This is classic "bloat" where the same bug fix might require updating 3 tests.
3.  **Apparent Coverage vs. Real Safety:** The massive number of signal tests (Contract tests) gives a false sense of safety. They pass as long as the signal exists, but they don't catch bugs where the signal is emitted with the *wrong data* at the *wrong time* in a real workflow.

## Recommended Preservation Map

| Core Behavior | Preserved via... | Redundant Tests to Prune |
| :--- | :--- | :--- |
| **HAL Compression** | `tests/unit/test_hal_parsing.py` & `tests/integration/test_hal_compression.py` | `tests/integration/test_decomp.py` (if made redundant) |
| **UI Workflow** | `tests/integration/test_complete_ui_workflows_comprehensive.py` | `*_signals.py`, `test_circular_dependency_fix.py` |
| **Palette Management** | `tests/unit/test_palette_manager.py` | `TestBusinessLogicOnly` in `test_business_logic_mocked.py` |
| **Signal Integrity** | `tests/integration/test_thread_safety_comprehensive.py` | `test_qt_signal_architecture.py` (partial), `test_qt_infrastructure.py` |

## Summary of Actions
- **Remove:** 8-10 files.
- **Merge:** 12 files into 4.
- **Move:** 1 file (manual ROM test).
- **Consolidation Impact:** Estimated reduction of ~200 redundant tests while maintaining 99% of actual behavioral confidence.