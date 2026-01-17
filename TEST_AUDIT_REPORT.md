# SpritePal Test Suite Audit Report
**Date**: January 17, 2026
**Focus**: Redundancy, Bloat, and Signal-to-Noise Ratio

## 1. High-Redundancy "Signal Coverage" Meta-Tests
The suite contains several files dedicated to verifying signal connections via heavy mocking. These are the primary source of bloat and maintenance cost.

*   **Files**: 
    *   `tests/ui/integration/test_signal_emission_coverage.py`
    *   `tests/ui/integration/test_signal_receiver_coverage.py`
    *   `tests/ui/integration/test_signal_downstream_effects.py`
    *   `tests/ui/integration/test_tier3_coverage_gaps.py`
*   **Today's Confidence**: **Low**. These tests verify if "Mock A calls Signal B." They do not prove the UI works, and they are brittle to signal signature changes. 
*   **Primary Behavior Overlap**: Covered by `test_editing_controller_integration.py` and `test_rom_workflow_integration.py`.
*   **Recommendation**: **Remove**. The existing workflow-based integration tests already verify these signals by asserting on observable state changes (e.g., drawing a pixel updates the undo stack).

## 2. Implementation-Detail Bloat (HAL Compression)
The HAL concurrency tests are significantly over-engineered, focusing on mocking Python's internal multiprocessing behavior.

*   **File**: `tests/integration/test_hal_compression.py` (1300+ lines).
*   **Today's Confidence**: **Moderate**. While process lifecycle is important, the tests focus on "mock-timing" (e.g., asserting `mock_proc.terminate` was called) rather than "system-outcome" (e.g., "can I still compress after a worker crashes?").
*   **Recommendation**: **Rewrite & Prune**. Consolidate the lifecycle tests into 5-10 robust integration tests using `MockHALProcessPool` or actual short-lived processes. Move bit-level validation entirely to `test_hal_parsing.py`.

## 3. Trivial "Sanity" Tests
Several files contain tests that assert basic language features or boilerplate that is implicitly verified by every other test.

*   **Examples**:
    *   `tests/unit/test_core_infrastructure.py`: `test_exception_inheritance_chain` (asserts inheritance).
    *   `tests/unit/test_sprite_regions.py`: `test_sprite_region_creation` (asserts `self.x = x`).
    *   `tests/integration/test_rom_extractor.py`: `test_init_creates_components` (asserts `self.x is not None`).
*   **Today's Confidence**: **Zero**. These never fail unless the code literally won't run.
*   **Recommendation**: **Remove**. These increase the noise floor without protecting against regressions.

## 4. Brittle UI Tests (Layout)
Tests that mock internal panels to verify layout behavior provide false confidence, especially after the Dock-based UI redesign.

*   **File**: `tests/ui/test_layout_responsiveness.py`.
*   **Today's Confidence**: **Low**. It uses `MockPanel` to verify `QSplitter` behavior. This doesn't catch real layout bugs (like overlapping widgets or CSS masking issues) and is likely obsolete after the move to `QDockWidget`.
*   **Recommendation**: **Remove**. Replace with higher-level "Visibility" checks in main UI tests if necessary.

## 5. Summary of Recommended Actions

| Category | Action | Target Files/Patterns |
| :--- | :--- | :--- |
| **Redundant Coverage** | **Remove** | `tests/ui/integration/test_signal_*`, `test_tier3_coverage_gaps.py` |
| **Trivial Logic** | **Remove** | Inheritance tests, simple `__init__` field assignments. |
| **Bug Fixes** | **Merge** | Move `test_..._bug.py` and `test_..._fixes.py` into primary component tests. |
| **Heavy Mocks** | **Rewrite** | `tests/integration/test_hal_compression.py` (focus on outcomes, not internal mock calls). |
| **Infrastructure** | **Keep** | `tests/integration/test_base_manager.py` (verified thread/GC safety). |

## 6. Coverage Gaps & Fragility
*   **False Confidence**: Many UI integration tests use `controller.handle_pixel_press` instead of `qtbot.mouseClick` on the canvas. This proves the logic works but skips the "View -> Controller" wiring.
*   **Gap**: There is minimal coverage for **Path Resilience** (handling ROMs in directories with spaces, non-ASCII characters, or read-only permissions).

**Diagnostic Conclusion**: The test suite is currently "fat." Pruning the identified meta-tests and trivial sanity checks would reduce the maintenance surface by ~15% while increasing the meaningful "signal" per test run.
