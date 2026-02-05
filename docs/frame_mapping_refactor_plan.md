# Frame Mapping Refactor Plan (Multi-Phase)

Last updated: 2026-02-05

## Scope
This plan targets maintainability and change safety for the Frame Mapping subsystem while preserving behavior.

## Why We Are Doing This
The current system works functionally, but maintenance cost and regression risk are high for normal feature work. Refactoring is required now because:
- High-impact reliability risks exist in core save/injection flows.
- Important mutation and signal boundaries are not consistently enforced.
- Core orchestration and canvas layers are too large for low-risk incremental change.
- Documentation and tests do not fully cover current architecture seams.

If we postpone this work, new features (additional mapping modes, richer palette workflows, new injection behavior) will continue increasing hidden coupling and breakage probability.

## Completion Status

| Phase | Status | Summary |
|-------|--------|---------|
| 0 | **Done** (core items) | R1 + R3 bugs fixed, regression tests added |
| 1 | **Done** (signal emissions) | 2 direct `project_changed.emit()` violations fixed |
| 2 | **Done** (minimum viable) | R3 bug fixed via correct ID comparison + field rename |
| 3 | Deferred | Connection registry is over-engineering at current scale |
| 4 | Deferred | Workspace size is manageable; extract when blocked |
| 5 | Deferred | Canvas rendering code is tightly coupled by nature |
| 6 | Skipped | No second mapping mode planned; premature abstraction |
| 7 | **Done** (partial) | Signal docs updated, backup artifact deleted |

## Original Findings Baseline

### 1. Code Structure and Responsibility Boundaries: Needs Work
- `FrameMappingWorkspace` is still a large orchestration hub with manual signal wiring and many handlers.
- `FrameMappingController` mixes composition-root responsibilities with broad operational API.
- `WorkbenchCanvas` combines rendering, async orchestration, preview generation, alignment logic, and interaction tools.

### 2. Naming and Readability: Acceptable
- Most names are clear, but `frame_id` is overloaded across AI and game ID domains.
- Some internal constructs are not self-explanatory (`_project_holder` indirection pattern).

### 3. Documentation and Intent Signaling: Acceptable
- Docstring coverage is generally good.
- Signal architecture doc is out of date in key places and can mislead maintainers.

### 4. Error Handling and Edge Cases: Needs Work
- Some broad exception boundaries hide operational failures.
- Save pipeline reports success based on exception behavior, not operation result.
- Recursive queue processing pattern is fragile for large batches.

### 5. Coupling and Dependencies: Needs Work
- Multiple layers bypass controller boundaries and emit signals directly.
- Coordinators and windows can mutate project state or emit persistence signals directly.
- Private field reach-through exists between coordinator and editor windows.

### 6. Extensibility and Change Risk: Needs Work
- Link policy is hardcoded around 1:1 assumptions.
- Status handling is still largely string-driven in data/control paths.

### 7. Test Coverage and Testability: Acceptable
- Strong coverage breadth overall.
- Gaps exist around newly extracted coordinators/facades and specific integrity paths.

### 8. Technical Debt and Maintenance Hazards: Needs Work
- Backups/artefacts are present in source tree.
- Large duplicated signal wiring patterns increase drift risk.
- Runtime monkey-patching of widget methods increases hidden behavior.

## Top Risks

| Risk | Description | Status |
|------|-------------|--------|
| R1 | Auto-save can report success on failure | **Fixed** (`1306069d`) |
| R2 | Mutation boundary violations create inconsistent dirty/signal behavior | **Fixed** — 2 `project_changed.emit()` call sites (`f03228a6`). PaletteService mutations are proper (service emits its own signal, controller relays). |
| R3 | ID-domain confusion can corrupt stale-entry/batch accounting | **Fixed** (`709e61fd`) — comparison uses mapping lookup; field renamed to `stale_entry_game_frame_id` |
| R4 | Oversized orchestration/canvas classes increase regression risk | Open — deferred, extract when a specific change is blocked |
| R5 | Architecture docs and seam-level tests lag current implementation | **Partially fixed** — signal docs updated, regression tests added |

---

## Phase 0: Safety Rails and Baseline — DONE

### What Was Done
- Fixed save-result semantics: `_SaveWorker.run()` checks `save_project()` return value (`1306069d`)
- Fixed stale-entry ID domain bug: comparison now looks up game frame ID via mapping (`709e61fd`)
- Renamed `stale_entry_frame_id` → `stale_entry_game_frame_id` for clarity
- Added 7 regression tests (`d3043a0e`):
  - `test_auto_save_manager.py`: worker success/failure/exception paths, manager callback behavior
  - `test_injection_stale_entry.py`: stale entry detection with matching/differing/null game frame IDs

### What Was Descoped
- Smoke flow documentation (link creation, alignment, inject, load/save) — not needed for bug fixes
- Runtime assertions for invariants — the bugs were fixed directly
- Dirty-flag transition tests — existing coverage adequate

### Verification
- 331 unit tests pass (frame mapping)
- 369 integration tests pass
- ruff, basedpyright: 0 errors

---

## Phase 1: Boundary Enforcement — DONE (signal emissions)

### What Was Done
- Replaced 2 direct `self._controller.project_changed.emit()` calls with `self._controller.emit_project_changed()` (`f03228a6`):
  - `frame_mapping_workspace.py:1401` (row reorder/clear path)
  - `palette_coordinator.py:410` (palette editor save path)

### What Was Descoped
- **PaletteService mutations (lines 102-103, 149-157) are not boundary violations.** The service receives the project as a parameter, mutates it, and emits its own `sheet_palette_changed` signal. The controller relays this signal via a connection at `frame_mapping_controller.py:601`. This is the proper service pattern.
- New controller APIs for AI frame path updates / in-game edited path updates — not needed; existing `emit_project_changed()` wrapper is sufficient
- Seam tests for mutation paths — existing test coverage is adequate

### Remaining Work (if needed later)
- `save_requested.emit()` calls outside controller — not found in current code (no violation exists)
- Formal contract tests for mutation→signal→dirty invariants — add when a bug motivates it

---

## Phase 2: ID Domain Hardening — DONE (minimum viable)

### What Was Done
- Fixed the actual R3 bug: `handle_async_injection_finished` now looks up the mapping's `game_frame_id` instead of comparing AI frame ID against game frame ID
- Renamed `stale_entry_frame_id` → `stale_entry_game_frame_id` throughout the codebase
- Added 3 targeted tests for stale-entry domain correctness

### What Was Descoped
- **Typed identifiers / type aliases** — Over-engineering for this codebase. The rename eliminates the ambiguity. Adding `NewType("AIFrameId", str)` etc. would add ceremony without catching bugs the rename doesn't already prevent.
- Broader `ai_`/`game_` prefix rename campaign — do incrementally when touching each file

---

## Phase 3: Signal and Event Wiring Refactor — DEFERRED

**Rationale:** 80 manual connections in a stable app don't justify a registry abstraction. The asymmetric disconnect concern (the original motivation) should be fixed directly by mirroring connect/disconnect blocks, not by building infrastructure.

**Trigger to revisit:** If signal wiring bugs become a recurring source of regressions.

---

## Phase 4: Workspace Decomposition — DEFERRED

**Rationale:** `FrameMappingWorkspace` at 1,657 lines with clear sections is maintainable. The methods are mostly thin delegates. Extract only when a specific change is blocked by the size.

**Trigger to revisit:** If a feature requires adding >100 lines to the workspace, extract the relevant section first.

---

## Phase 5: Workbench Canvas Decomposition — DEFERRED

**Rationale:** `WorkbenchCanvas` at 2,988 lines is large but rendering code is tightly coupled by nature. High risk of regression for unclear benefit. The current structure has clear section comments.

**Trigger to revisit:** If a rendering bug is difficult to isolate due to class size.

---

## Phase 6: Mapping Policy and Status Model — SKIPPED

**Rationale:** Premature abstraction. Only justified if a second mapping mode is planned. Current 1:1 behavior is hardcoded in ~3 places; extract when needed.

---

## Phase 7: Documentation and Cleanup — DONE (partial)

### What Was Done
- Updated `docs/frame_mapping_signals.md` with `mapping_displaced` signal and current date (`55b39629`)
- Deleted backup artifact `ui/frame_mapping/windows/ai_frame_palette_editor.py.backup`

### What Was Descoped
- Maintenance checklist / CI checks for backup artifacts — not worth the setup for a single-user project
- Full architecture boundary documentation — the existing `docs/architecture.md` and `.claude/rules/` files serve this purpose

---

## Sequencing and Risk Control
- Execute phases in order; do not start major decomposition before Phase 0-2 complete.
- Keep each phase in reviewable PR slices with explicit rollback scope.
- After each phase:
  - run targeted tests for touched areas
  - run lint and type checks
  - record migration notes and known limitations
- Avoid mixing boundary changes and major structural extraction in the same PR.

## Commits (2026-02-05)

| Commit | Phase | Description |
|--------|-------|-------------|
| `1306069d` | 0 | fix: check `_save_project()` return value in `_SaveWorker.run()` |
| `709e61fd` | 0, 2 | fix: correct ID domain mismatch in stale-entry tracking |
| `d3043a0e` | 0 | test: add regression tests for auto-save and stale-entry bug fixes |
| `f03228a6` | 1 | fix: use `emit_project_changed()` method instead of direct signal emission |
| `55b39629` | 7 | docs: add `mapping_displaced` signal to frame mapping signals documentation |
