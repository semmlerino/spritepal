# Test Suite Audit Report

**Date:** January 24, 2026
**Status:** Diagnostic Complete

## Executive Summary
The `spritepal` test suite is comprehensive but exhibits signs of fragmentation and redundancy, particularly in the "Sprite Finding" and "HAL Compression" domains. While recent efforts have consolidated palette tests (`test_palette_workflow.py`), similar consolidation is needed for core logic tests. There is also a proliferation of specific "repro" tests in the UI suite that should be grouped into feature-based regression suites.

## 1. Redundancy & Consolidation Candidates

### A. Sprite Finder Logic
**Current State:**
- `tests/unit/test_sprite_finder.py`: Mocked unit tests for `SpriteFinder`.
- `tests/integration/test_integration_sprite_finder.py`: Tests `SpriteFinder` with real components, but also re-tests HAL compression and ROM extraction.
- `tests/integration/test_parallel_sprite_finder.py`: Tests `ParallelSpriteFinder` wrapper.

**Recommendation:** **MERGE & PRUNE**
1.  **Remove** the `TestHALCompression` and `TestROMExtractor` classes from `tests/integration/test_integration_sprite_finder.py`. These behaviors are already covered in dedicated test files.
2.  **Rename** `tests/integration/test_integration_sprite_finder.py` to `tests/integration/test_sprite_discovery.py` and focus it strictly on the *integration* of the finder with the file system and real ROM data.
3.  **Keep** `tests/unit/test_sprite_finder.py` for logic/edge case testing (confidence thresholds, metric parsing).

### B. HAL Compression
**Current State:**
- `tests/integration/test_hal_compression.py`: Main integration test.
- `tests/unit/test_hal_golden.py`: Golden file testing.
- `tests/unit/test_hal_parsing.py`: Unit testing parsing logic.
- `tests/integration/test_integration_sprite_finder.py`: *Redundant* HAL cycle tests.

**Recommendation:** **REMOVE REDUNDANCY**
- As mentioned above, remove HAL tests from the sprite finder integration suite. The dedicated files (`test_hal_compression.py` and `test_hal_golden.py`) provide better, more focused coverage.

### C. UI Regression Tests ("Repro" Bloat)
**Current State:**
The `tests/ui` directory contains numerous single-issue reproduction tests:
- `test_finding_1_repro.py`
- `test_finding_2_repro.py`
- `test_finding_4_repro.py`
- `test_batch_injection_performance_repro.py`
- `test_mode_switch_repro.py`

**Recommendation:** **CONSOLIDATE**
- Group these into feature-specific regression suites.
    - `test_finding_*_repro.py` -> `tests/ui/integration/test_finding_regressions.py`
    - `test_batch_injection_performance_repro.py` -> Move to `tests/performance/` or `tests/integration/test_injection_performance.py`.

## 2. High-Value vs. Low-Signal Tests

| Test Category | Signal Level | Notes | Action |
| :--- | :--- | :--- | :--- |
| **Core/Unit (Mocks)** | High | Good for logic verification (e.g. `test_sprite_finder.py`). | **Keep** |
| **UI Integration** | High | `test_palette_workflow.py` is a model for how these should be structured. | **Keep & Emulate** |
| **Mixed Integration** | Low | `test_integration_sprite_finder.py` is noisy because it tests too many things (HAL, ROM, Finder). | **Refactor** |
| **Repro Scripts** | Medium | High signal for specific bugs, but high maintenance cost as separate files. | **Merge** |

## 3. Coverage Gaps & Risks

- **Controller Logic:** While `EditingController` is heavily tested via UI integration tests, other controllers like `ROMWorkflowController` rely on complex interactions that might be better tested with dedicated "headless" controller tests (mocking the View) to ensure state transitions are correct without the overhead of `qtbot`.
- **Palette Persistence:** We have `test_palette_persistence.py` (settings) and `test_palette_load_sync.py` (runtime). Ensure there is a test that bridges the gap: "Application starts, loads last palette, AND the canvas correctly renders with it" (combining persistence and sync).

## 4. Action Plan

1.  **Immediate:** Strip `tests/integration/test_integration_sprite_finder.py` of HAL and ROM Extractor tests.
2.  **Short Term:** Create `tests/ui/regressions/` folder and move/merge loose `repro` tests there.
3.  **Long Term:** Audit `tests/integration` to ensure every file has a clear, single responsibility (e.g., "Testing the database layer", "Testing the HAL bridge") rather than "Testing everything related to Sprites".

## 5. Mapping Behaviors to Tests

- **Behavior:** "Find sprites in a ROM"
  - *Primary Test:* `tests/integration/test_sprite_discovery.py` (Renamed from `test_integration_sprite_finder.py`)
  - *Logic Test:* `tests/unit/test_sprite_finder.py`

- **Behavior:** "Compress/Decompress HAL"
  - *Primary Test:* `tests/integration/test_hal_compression.py`
  - *Golden Test:* `tests/unit/test_hal_golden.py`

- **Behavior:** "Edit Palette"
  - *Primary Test:* `tests/ui/integration/test_palette_workflow.py`
  - *Sync Test:* `tests/ui/integration/test_palette_load_sync.py`