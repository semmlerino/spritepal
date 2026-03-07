# Pytest Performance Audit & Optimization Plan

## Status (2026-02-06)

| Finding | Status | Notes |
|---------|--------|-------|
| Eager PySide6 imports in fixtures | **Fixed** | `dialog_fixtures.py` was the last offender — deferred in d7531d7f. All 7 fixture modules now use lazy imports. |
| pytest-qt plugin overhead | **Won't fix** | Plugin hooks run during config phase, not code-controllable. Measured `-p no:qt` vs normal for core tests: ~1s difference (9.0s vs 10.0s) — not worth special-casing. |
| Thread cleanup overhead | **Already optimized** | `cleanup_workers` has early exits: skips non-Qt tests, skips when `_worker_registry` is empty. No further action needed. |
| Redundant import cascades | **Already fixed** | `core_fixtures.py` imports only `is_headless` (no PySide6 chain). |
| `norecursedirs` missing | **Already configured** | `pyproject.toml` has entries; no interfering dirs exist. |

**Collection time (post-fix):** ~21–28s for 3928 tests (WSL2, varies with filesystem caching).

---

## Findings: What is slow and why (original audit)

1. **Massive Collection Overhead (The #1 Bottleneck)**
   - **Measurement:** Collecting 3,924 tests takes **~76 seconds**.
   - **Reason:** Eager imports. `tests/fixtures/dialog_fixtures.py` (and others) perform top-level imports of `PySide6.QtWidgets`. Because these are in the root `conftest.py` via `pytest_plugins`, **Qt initializes on every single run**, even for `--collect-only` or when running a single non-GUI unit test.
   - **Impact:** This adds a fixed ~40s tax to every test session before a single test even starts.

2. **Plugin Interaction Costs**
   - **Measurement:** Disabling the `qt` plugin reduces collection time from **76s to 34s**.
   - **Reason:** The `pytest-qt` plugin performs extensive environment checks and hook setups. When combined with eager application imports in fixtures, it forces the OS to load heavy shared libraries (Qt, Graphics drivers) during the discovery phase.

3. **Thread Leak Detection Overhead**
   - **Observation:** Every test using a GUI or Manager fixture runs `cleanup_workers`.
   - **Reason:** This fixture performs a `threading.enumerate()` and a poll-loop check. While necessary for stability, it adds 10-50ms of "silence" at the end of every test. Across 4,000 tests, this adds up to minutes of wall-clock time.

4. **Redundant Import Cascades**
   - **Observation:** Most tests in `tests/unit/core` import `ui` components indirectly because shared fixtures or utility modules aren't strictly decoupled.

---

## Recommended Changes

### 1. Quick Wins (Immediate Impact / Low Effort)

- **Lazy Load Qt in Fixtures:** Move all `PySide6` imports inside the fixture functions or `if TYPE_CHECKING` blocks in `tests/fixtures/`. Specifically target `dialog_fixtures.py` and `qt_fixtures.py`. This prevents Qt from booting during collection.
- **Narrow Test Discovery:** Update `testpaths` in `pyproject.toml` to be more specific if possible, or use `norecursedirs` to explicitly skip large data/archive folders that might be accidentally scanned.
- **Disable XDist for small runs:** While parallel execution is fast for the full suite, the overhead of spawning workers for < 50 tests is negative.

### 2. Technical Suggestions (Medium Effort)

- **Decouple Core and UI Fixtures:** Ensure that `tests/fixtures/core_fixtures.py` does not import anything from `PySide6`. Currently, it imports `is_headless` from `qt_fixtures`, which triggers the chain.
- **Optimize Thread Cleanup:** Modify `cleanup_workers` to only run the expensive poll-loop if `threading.active_count()` actually changed since the start of the test.
- **Use `sys.modules` Guard:** Use an import hook (similar to the existing `QPixmap` guard) to prevent `ui` modules from being imported during unit tests in `tests/unit/core`.

### 3. Big Wins (High Impact / Strategic)

- **Move to `pytest-qt`'s `qapp` exclusively:** Instead of a custom session-scoped `qt_app`, rely entirely on `pytest-qt`'s built-in lifecycle but configure it to be lazier.
- **Pre-compiled Bytecode:** In CI, cache the `.pytest_cache` and `__pycache__` more aggressively.
- **Split Suites:** Separate "Pure Core" tests from "GUI Integration" tests at the directory level so that core tests can be run with `-p no:qt` to bypass all PySide6 overhead.

---

## Implementation Concepts

### Concept 1: Lazy Imports in `dialog_fixtures.py`
```python
# Instead of top-level: from PySide6.QtWidgets import QMessageBox
def _start_patches(self) -> None:
    from PySide6.QtWidgets import QMessageBox  # Move inside method
    # ... rest of logic
```

### Concept 2: Optimization in `conftest.py`
```python
# tests/conftest.py
def pytest_configure(config):
    # Only install the QPixmap guard if we are actually running GUI tests
    if config.getoption("-m") and "gui" in config.getoption("-m"):
        install_qpixmap_guard()
```

### Concept 3: Faster Collection via `pyproject.toml`
```toml
[tool.pytest.ini_options]
# Add these to speed up discovery
testpaths = ["tests"]
norecursedirs = [".git", "archive*", "extracted_sprites", "dumps", "roms*"]
```
