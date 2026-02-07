# Testing Guidelines Review: Quality and Real-World Adherence

## Guideline Quality Assessment

Overall, the guidance is strong and mostly modern. It explicitly covers behavior-first testing, boundary-only mocking, isolation, Qt async safety, and deterministic waits.

- Behavior over implementation: `docs/testing_guide.md:18`
- Real components over mocks: `docs/testing_guide.md:19`
- Signal/wait guidance: `docs/testing_guide.md:71`, `docs/testing_guide.md:77`
- Avoid sleep in Qt tests: `docs/testing_guide.md:97`
- Thread-safe image guidance: `docs/testing_guide.md:94`, `docs/testing_guide.md:119`
- Shared-state enforcement in code: `tests/conftest.py:625`, `tests/conftest.py:644`
- Strict marker and timeout baseline: `pyproject.toml:414`, `pyproject.toml:427`

### Gaps / Ambiguities / Outdated Areas

1. Documentation inconsistency on manager access
- `tests/README.md:90` says use `get_app_context()` exclusively.
- Other test docs favor fixture-driven access (`app_context`) as default: `tests/README.md:205`, `tests/FIXTURE_CHEATSHEET.md:65`.

2. Outdated test placement guidance
- `tests/FIXTURE_CHEATSHEET.md:112` still suggests `tests/test_<module>.py`, which conflicts with current split (`tests/unit/`, `tests/integration/`, `tests/ui/`).

3. Missing explicit anti-coupling policy language
- Policy says "test behavior, not implementation" (`docs/testing_guide.md:18`), but does not concretely ban private-state assertions and strict call choreography.
- Existing internal audit already flags this risk area: `docs/ToDo/impl_coupling_test_audit.md:3`, `docs/ToDo/impl_coupling_test_audit.md:35`.

## Adherence Findings (with Representative Examples)

### Where Tests Clearly Follow the Guidelines

1. Shared-state safety is actively enforced
- Runtime fixture enforces marker use for `session_app_context`: `tests/conftest.py:625`, `tests/conftest.py:644`.
- Marker contract is declared in pytest config: `pyproject.toml:457`.

2. Signal testing patterns are broadly aligned
- Extensive use of `with qtbot.waitSignal(...)` context-manager form (158 usages in the suite).
- Strong examples in worker lifecycle tests: `tests/ui/integration/test_worker_signal_lifecycle.py:24`, `tests/ui/integration/test_worker_signal_lifecycle.py:412`.

3. Real-component integration patterns exist
- App-context-backed integration scope: `tests/integration/test_sprite_gallery_integration.py:28`.
- Thread-safe image usage in worker-related tests: `tests/integration/test_preview_generator.py:66`.

### Where Tests Diverge from Guidelines

1. Non-deterministic timing still present (`time.sleep`)
- Unannotated sleeps in active test files:
  - `tests/unit/ui/frame_mapping/services/test_thumbnail_disk_cache.py:107`
  - `tests/ui/frame_mapping/services/test_thumbnail_service_disk_cache.py:169`
  - `tests/unit/ui/controllers/test_fmc_preview_cache.py:187`
  - `tests/unit/core/services/test_lru_cache.py:284`

2. Heavy fixed-delay Qt waits (brittleness/perf drag)
- Large concentration of `qtbot.wait(...)` in one file:
  - `tests/ui/integration/test_offset_browser_nearby.py:153`
  - `tests/ui/integration/test_offset_browser_nearby.py:170`
  - `tests/ui/integration/test_offset_browser_nearby.py:644`

3. Implementation-detail coupling and over-mocking
- Internal state and call-choreography assertions in UI helper tests:
  - `tests/ui/frame_mapping/test_workspace_logic_helper.py:58`
  - `tests/ui/frame_mapping/test_workspace_logic_helper.py:135`
  - `tests/ui/frame_mapping/test_workspace_logic_helper.py:243`
- Mock-heavy "integration" test with deep wiring mocks:
  - `tests/integration/test_startup_state.py:3`
  - `tests/integration/test_startup_state.py:23`
  - `tests/integration/test_startup_state.py:143`

## Most Impactful Policy-vs-Practice Inconsistencies

1. Behavior-first policy vs implementation-coupled assertions in several high-value suites.
2. Deterministic async guidance vs continued use of sleeps/fixed waits in cache and nearby-offset tests.
3. "Single source of truth" intent vs conflicting practical guidance across `docs/testing_guide.md`, `tests/README.md`, and `tests/FIXTURE_CHEATSHEET.md`.

## Priority Recommendations

### Doc Updates

1. P0: Reconcile test docs into one canonical rule set.
- Align `tests/README.md` and `tests/FIXTURE_CHEATSHEET.md` with `docs/testing_guide.md`.
- Remove/clarify conflicting `get_app_context()` wording in test docs.

2. P0: Update placement guidance.
- Replace legacy `tests/test_<module>.py` paths with current unit/integration/ui structure.

3. P1: Add explicit anti-coupling section.
- Ban assertions on private attributes and strict call ordering unless the call sequence is externally observable behavior.
- Link to rewrite patterns (state/result assertions, emitted-signal semantics, user-visible outcomes).

### Test Suite Fixes

1. P0: Eliminate unannotated `time.sleep()` from active tests.
- Replace with deterministic mtime control (`os.utime`), explicit clocks, or event/signal synchronization.

2. P0: Refactor `test_offset_browser_nearby` away from fixed `qtbot.wait(...)` delays.
- Use signal-driven checks or `waitUntil` with explicit state predicates.

3. P1: Reduce coupling in `test_workspace_logic_helper`.
- Shift from direct private-state access and call-count assertions to public behavior/outcome checks.

4. P1: Re-scope/refactor mock-heavy integration tests (e.g., `test_startup_state`).
- Either make them true integration tests with more real components or move to unit/component scope.

### Quick Wins

1. Add a CI guard to block new unannotated `time.sleep()` in tests.
2. Add a soft linter check (warn first) for new private-member assertions in tests.
3. Add a short contributor checklist in `docs/testing_guide.md` for deterministic async patterns and anti-coupling expectations.

---

Assessment method: static review of repository documentation and representative test files; no full-suite runtime execution performed in this review.
