# SpritePal Test Suite Review: Brittleness Analysis & Fixes (v11)

## Version History
- v11: Critical review corrections. Removed incorrect Phase 3 fixes (sleeps are already correct). Replaced fragile line-number allowlist with inline `# sleep-ok` comments. Removed Phase 5 (YAGNI). Added `--strict` flag to address enforcement gap. Updated verification commands to use `uv run`. Simplified scope.
- v10: Simplified based on code review. Fixed broken sleep regex, removed RealComponentFactory warning machinery (just fix call sites), removed dual CI lanes, added success criteria and prioritized fix list, fixed QThread.quit() trap.
- v9: Kept leak-mode default strict with an optional warn lane, prioritized wait-helper inventory before adding shims, reused/expanded the existing regex sleep checker with an allowlist, and guarded RealComponentFactory changes with lazy Qt imports and call-site migration.

## Executive Summary

**What already works (no changes needed):**
- `--leak-mode=fail` is already implemented in `tests/conftest.py:201-216`
- Anti-pattern checker exists at `tests/infrastructure/check_test_patterns.py`
- `qt_fixtures.py` leak detector already uses `QThread.msleep()` as primary (correct)
- `real_component_factory.py` cleanup sleep is for OS-level thread teardown (correct)

**What's broken and needs fixing:**
1. Sleep regex catches `time.sleep(1)` but misses float violations like `time.sleep(0.01)`
2. No mechanism to allowlist intentional sleeps (threading tests, benchmarks)
3. Wait helpers undocumented; developers don't know `qt_waits.py` is canonical

**What's NOT broken (removed from v10):**
- `real_component_factory.py:726` — sleep is for OS thread cleanup AFTER QThreads are gone; correct as-is
- `qt_fixtures.py:355,358` — fallback for non-Qt contexts; primary path uses `msleep()`; correct as-is

---

## Success Criteria

- [ ] Anti-pattern checker catches float sleeps (`time.sleep(0.01)`)
- [ ] Checker skips lines containing `# sleep-ok:`
- [ ] `--strict` flag added for CI enforcement (optional)
- [ ] Intentional sleeps annotated with `# sleep-ok: <reason>`
- [ ] `qt_waits.py` documented as canonical in CLAUDE.md
- [ ] No false positives from the checker on intentional sleeps

---

## Phase 1: Fix the Anti-Pattern Checker (45 min)

### Current Problems

1. The existing pattern `r'time\.sleep\(\d+\)'` requires **integer** arguments, but every real violation uses floats:
   ```
   tests/test_qt_signal_architecture.py:97:  time.sleep(0.01)
   tests/fixtures/qt_fixtures.py:355:        time.sleep(poll_interval_ms / 1000.0)
   tests/infrastructure/real_component_factory.py:726: time.sleep(0.15)
   ```

2. **Enforcement gap:** The checker returns exit code 0 for warnings-only, so CI won't fail on `time.sleep` violations.

### Fix 1: Update Patterns

In `tests/infrastructure/check_test_patterns.py`, replace:
```python
AntiPattern(
    r'time\.sleep\(\d+\)',
    'Use qtbot.wait() or qtbot.waitSignal() instead of time.sleep() in Qt tests',
    'warning'
),
```

With:
```python
AntiPattern(
    r'time\.sleep\([^)]+\)',
    'Prefer qtbot.wait() in Qt tests; allowlist with "# sleep-ok: reason" if intentional',
    'warning'
),
AntiPattern(
    r'from time import sleep',
    'Import time module instead; bare sleep() is harder to grep for',
    'warning'
),
```

**Note on regex:** `[^)]+` stops at the first `)`, so `time.sleep(get_delay())` matches as `time.sleep(get_delay(`. This still flags the line, which is sufficient.

### Fix 2: Add Allowlist Support

In the `check_file()` function, add skip logic for allowlisted lines:

```python
# Inside the loop over ANTI_PATTERNS, after getting the line:
line = lines[line_num - 1] if line_num <= len(lines) else ''
stripped = line.lstrip()

# Skip if in a comment
if stripped.startswith('#'):
    continue

# Skip if explicitly allowlisted
if '# sleep-ok' in line:
    continue
```

### Fix 3: Add `--strict` Flag for CI Enforcement

In `_parse_args()`:
```python
parser.add_argument(
    '--strict',
    action='store_true',
    help='Exit with code 1 if any issues found (warnings or errors). Default: only errors fail.',
)
```

In `main()`, change the return logic:
```python
# Old:
return 1 if has_errors else 0

# New:
if has_errors:
    return 1
if args.strict and all_issues:
    return 1
return 0
```

**Enforcement modes:**
| Mode | Errors | Warnings | Use Case |
|------|--------|----------|----------|
| Default | Fail | Pass | Local development |
| `--strict` | Fail | Fail | CI enforcement |

### Verification
```bash
# Advisory mode (default) - warnings printed but exit 0
uv run python -m tests.infrastructure.check_test_patterns --paths tests

# Strict mode - warnings cause exit 1
uv run python -m tests.infrastructure.check_test_patterns --paths tests --strict
```

---

## Phase 2: Annotate Intentional Sleeps (1 hr)

### Triage Rules

| Condition | Action |
|-----------|--------|
| Threading stress test, any sleep duration | Annotate `# sleep-ok: thread interleaving` |
| Performance/benchmark test | Annotate `# sleep-ok: benchmark timing` |
| `patch('time.sleep')` or `mock_sleep` | Annotate `# sleep-ok: mocked in test` |
| Fixture cleanup fallback | Annotate `# sleep-ok: non-Qt fallback` |
| OS-level thread cleanup | Annotate `# sleep-ok: OS thread teardown` |
| Mock delay simulation | Annotate `# sleep-ok: simulated delay` |
| Unclear | Investigate before annotating |

### Files to Annotate

**Threading/concurrency tests (intentional interleaving):**
```python
# tests/test_qt_signal_architecture.py
time.sleep(0.01)  # sleep-ok: thread interleaving test

# tests/test_thread_safe_singleton.py
time.sleep(0.01)  # sleep-ok: concurrent access test

# tests/test_qt_threading_patterns.py
time.sleep(0.01)  # sleep-ok: thread sync test

# tests/test_phase1_stability_fixes.py
time.sleep(0.01)  # sleep-ok: race condition test
```

**Performance/benchmark tests:**
```python
# tests/test_performance_benchmarks.py
time.sleep(1.0)  # sleep-ok: benchmark cooldown
time.sleep(0.001)  # sleep-ok: rate limiting test
```

**Fixture cleanup (correct fallbacks):**
```python
# tests/fixtures/qt_fixtures.py:355,358
time.sleep(poll_interval_ms / 1000.0)  # sleep-ok: non-Qt fallback

# tests/infrastructure/real_component_factory.py:726
time.sleep(0.15)  # sleep-ok: OS thread teardown after gc.collect()
```

**Mock delays:**
```python
# tests/infrastructure/mock_hal.py:110
time.sleep(self._mock_delay)  # sleep-ok: simulated processing delay
```

**Test instrumentation (mocked):**
```python
# tests/test_hal_compression.py - these mock time.sleep, no annotation needed
# The patch('time.sleep') context makes it clear
```

### Verification

After annotating, run:
```bash
uv run python -m tests.infrastructure.check_test_patterns --paths tests
```

Warnings should drop to near-zero. Any remaining warnings need investigation.

---

## Phase 3: Document Canonical Wait Helpers (30 min)

### Decision: `tests/fixtures/qt_waits.py` is Canonical

**Current helpers in qt_waits.py:**
- `wait_for_condition(qtbot, condition, timeout_ms)` - use this
- `wait_for(qtbot, ms)` - use this
- `process_events(qtbot)` - use this
- `wait_for_widget_ready(qtbot, widget)` - use this
- `wait_for_signal_processed(qtbot, signal)` - use this

**Frozen (do not add new code):**
- `tests/infrastructure/signal_testing_utils.py` - SignalSpy is fine, but don't add wait helpers here
- `tests/infrastructure/qt_testing_framework.py` - legacy, freeze
- `tests/infrastructure/qt_real_testing.py` - freeze

### Add to CLAUDE.md

Add under "Test Fixture Selection Guide":
```markdown
### Wait Helper Usage

| Need | Use | NOT |
|------|-----|-----|
| Wait for condition | `wait_for_condition(qtbot, cond, timeout)` from `qt_waits.py` | `time.sleep()` |
| Wait fixed time | `qtbot.wait(ms)` or `wait_for(qtbot, ms)` | `time.sleep()` |
| Wait for signal | `qtbot.waitSignal(signal, timeout)` | Custom wait loops |
| Wait for thread exit | `thread.wait(timeout)` for QThread | `time.sleep()` + `isRunning()` |

**Intentional sleeps:** If `time.sleep()` is truly needed (thread interleaving tests, OS cleanup), annotate with `# sleep-ok: <reason>`.
```

---

## Removed from v10 (Incorrect or Over-Engineered)

### Phase 3 Code Changes - REMOVED

v10 proposed replacing sleeps in:
- `real_component_factory.py:726` with `QThread.wait()`
- `qt_fixtures.py:355,358` with `qtbot.wait()`

**Why removed:**
1. `real_component_factory.py:726` runs AFTER `gc.collect()` — no QThread objects exist to wait on. This sleep is for OS kernel thread cleanup, not Qt synchronization.
2. `qt_fixtures.py` already uses `QThread.currentThread().msleep()` as primary. The `time.sleep()` is a fallback for non-Qt contexts where `qtbot` wouldn't exist anyway.

Both are correct as-is. Annotate with `# sleep-ok` instead.

### Phase 5 QThread Wait Helper - REMOVED

**Why removed:** YAGNI. The existing patterns for QThread termination work. If a helper is needed later, add it then.

### Line-Number Allowlist File - REMOVED

**Why removed:** Line numbers shift on any edit. Inline `# sleep-ok` comments are:
- Co-located with the code they describe
- Self-documenting
- Immune to line number drift
- Greppable (`rg "sleep-ok"`)

---

## Critical Files to Modify

| File | Changes |
|------|---------|
| `tests/infrastructure/check_test_patterns.py` | Fix regex, add `# sleep-ok` skip logic, add `--strict` flag |
| `tests/fixtures/qt_fixtures.py:355,358` | Add `# sleep-ok: non-Qt fallback` comment |
| `tests/infrastructure/real_component_factory.py:726` | Add `# sleep-ok: OS thread teardown` comment |
| ~15 test files | Add `# sleep-ok: <reason>` to intentional sleeps |
| `CLAUDE.md` | Document canonical wait helpers |

---

## Verification Commands

**Run anti-pattern checker (advisory mode - default):**
```bash
uv run python -m tests.infrastructure.check_test_patterns --paths tests
```

**Run anti-pattern checker (strict mode - for CI):**
```bash
uv run python -m tests.infrastructure.check_test_patterns --paths tests --strict
```

**Run tests (strict leaks, single lane):**
```bash
QT_QPA_PLATFORM=offscreen uv run pytest --leak-mode=fail --maxfail=1 --tb=short
```

**Check remaining unannotated sleeps:**
```bash
rg -n "time\.sleep\(" tests/ | rg -v "sleep-ok|patch.*sleep"
```

**List all annotated sleeps:**
```bash
rg -n "sleep-ok" tests/
```

---

## What's NOT Changing

- `--leak-mode` implementation (already works)
- Marker validation (already enforced via `--strict-markers`)
- Order randomization (optional, add later if desired)
- Signal API consistency (guidance only, no lint)
- Class-scoped fixture isolation (low priority)
- Actual sleep behavior in `qt_fixtures.py` and `real_component_factory.py` (already correct)
