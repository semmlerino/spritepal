# Test Infrastructure Improvements Plan

## Executive Summary

Three test infrastructure issues to address, in recommended execution order:

| Issue | Severity | Scope | Approach |
|-------|----------|-------|----------|
| 1. DataRepository singleton | Medium | 7 files | Migrate to `isolated_data_repository` fixture |
| 2. Private API usage | Low | 109 calls | Extract public test-support methods; document alternatives |
| 3. Docs vs practice mismatch | Low | 4 doc files | Update documentation to match reality |

**Execution Strategy:** Issue 1 first (file conflicts with Issue 2), then Issues 2 & 3 in parallel.

---

## Issue 1: DataRepository Singleton Migration (Medium Severity)

### Problem
- 7 test files use `get_test_data_repository()` singleton
- Accumulates 28-42+ temp directories per session (no per-test cleanup)
- `isolated_data_repository` fixture already exists but is underutilized

### Solution

**Phase 1: Add deprecation warning**
- File: `tests/infrastructure/data_repository.py`
- Add `DeprecationWarning` to `get_test_data_repository()`

**Phase 2: Migrate 7 files to fixture**
1. `tests/infrastructure/test_helpers.py` - refactor helpers to accept fixture parameter
2. `tests/integration/test_extraction_manager.py` - 15+ tests
3. `tests/integration/test_manager_integration_real_tdd.py` - 8 tests
4. `tests/integration/test_manager_performance_benchmarks_tdd.py` - 5 tests (may use `session_data_repository`)
5. `tests/infrastructure/real_component_factory.py` - internal usage

**Phase 3: Update documentation**
- `tests/README.md` - add migration guide
- `docs/testing_guide.md` - document data repository fixtures

### Verification
```bash
pytest -W error::DeprecationWarning  # Should fail if singleton still used
pytest tests/integration/ -n auto -vv  # All tests pass parallel
```

---

## Issue 2: Private API Usage (Low Severity)

### Problem
- 109 private method calls (`._method()`) across tests
- Top offenders: `_extract_palettes()` (14), `_start_operation()`/`_finish_operation()` (21), `_browse_file()` (7)
- Risk: Tests break on internal refactors

### Solution

**Phase 1: Extract test-support methods for concurrency testing**
- File: `core/managers/base_manager.py`
- Add public methods:
  ```python
  def simulate_operation_start(self, operation_name: str) -> bool
  def simulate_operation_finish(self, operation_name: str) -> None
  ```

**Phase 2: Update 21 concurrency tests**
- Files: `tests/integration/test_base_manager.py`, `tests/integration/test_extraction_manager.py`
- Replace `manager._start_operation()` → `manager.simulate_operation_start()`

**Phase 3: Document signal-based alternatives for UI testing**
- File: `docs/testing_guide.md`
- Document using `qtbot.mouseClick()` + signal waits instead of `_browse_file()`

**Phase 4: Document algorithm testing as acceptable**
- `_extract_palettes()` tests pure algorithm without I/O - this is valid
- Add documentation justifying direct algorithm testing

### Files to modify
- `core/managers/base_manager.py` - add test-support methods
- `tests/integration/test_base_manager.py` - update concurrency tests
- `docs/testing_guide.md` - document patterns

---

## Issue 3: Docs vs Practice Mismatch (Low Severity)

### Problem
- Docs say "almost never" use `session_app_context`, but 17 tests use it with `@pytest.mark.shared_state_safe`
- Mocking guidance too prescriptive (doesn't account for unit vs integration vs UI)
- Signal testing shows only one approach (QSignalSpy), not alternatives

### Solution

**Phase 1: Update session_app_context guidance**
- Files: `tests/README.md`, `tests/fixtures/app_context_fixtures.py`
- Document when session scope is appropriate (read-only, performance-sensitive)
- Add migration pattern from session→function scope

**Phase 2: Add layer-based mocking strategy**
- File: `docs/testing_guide.md`
- Document:
  - Unit tests: mock everything except class under test
  - Integration tests: mock system boundaries (HAL, disk I/O errors)
  - UI tests: mock managers, test widget behavior

**Phase 3: Document signal testing approaches**
- File: `docs/testing_guide.md`
- Document three approaches with pros/cons:
  1. `qtbot.waitSignal()` - async operations
  2. `QSignalSpy` - emission count/payload inspection
  3. `MultiSignalRecorder` - complex multi-signal workflows

**Phase 4: Clarify parallel safety**
- Files: `tests/fixtures/core_fixtures.py`, `tests/README.md`
- Explain xdist worker isolation (each worker has own session context)

---

## Execution Order

```
Issue 1 (DataRepository)  ─────────────────────────┐
                                                   │
                                                   ▼
                              ┌────────────────────┴────────────────────┐
                              │                                         │
                              ▼                                         ▼
                    Issue 2 (Private API)              Issue 3 (Documentation)
                              │                                         │
                              └─────────────────┬───────────────────────┘
                                                │
                                                ▼
                                            Verify
```

**Rationale:** Issue 1 has file conflicts with Issue 2 (both touch `test_extraction_manager.py`). Complete Issue 1 first, then run Issues 2 & 3 in parallel.

---

## Verification Checklist

- [ ] `pytest -W error::DeprecationWarning` passes (no singleton usage)
- [ ] `pytest tests/integration/ -n auto` passes (parallel safe)
- [ ] `ls /tmp/spritepal_*` shows no accumulated temp dirs after test run
- [ ] Documentation examples are runnable
- [ ] All tests pass: `pytest`

---

## Files Changed Summary

| File | Issue 1 | Issue 2 | Issue 3 |
|------|:-------:|:-------:|:-------:|
| `tests/infrastructure/data_repository.py` | ✅ | | |
| `tests/infrastructure/test_helpers.py` | ✅ | | |
| `tests/integration/test_extraction_manager.py` | ✅ | ✅ | |
| `core/managers/base_manager.py` | | ✅ | |
| `docs/testing_guide.md` | ✅ | ✅ | ✅ |
| `tests/README.md` | ✅ | | ✅ |
| `tests/fixtures/app_context_fixtures.py` | | | ✅ |
| `tests/fixtures/core_fixtures.py` | | | ✅ |
