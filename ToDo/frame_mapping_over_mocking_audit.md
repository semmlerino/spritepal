# Audit Report: Frame Mapping Test Suite Over-Mocking

**Date:** February 6, 2026  
**Status:** Actionable Report  

## 1. Categorized Worst Offenders

### Pure Interaction Tests (Brittle)
- **Files:** `tests/unit/ui/frame_mapping/test_palette_info_on_selection.py`, `tests/ui/frame_mapping/test_workspace_logic_helper.py`
- **Description:** These tests bypass constructors using `__new__` and manually inject mocks into private attributes (e.g., `_ai_frames_pane`, `_controller`). They assert *how* the helper calls its collaborators rather than the resulting state.
- **Severity:** High (Breaks on almost any refactor of internal method names).

### Mocking Core Data Structures
- **Files:** `tests/unit/ui/frame_mapping/services/test_palette_service.py`, `tests/unit/ui/frame_mapping/services/test_preview_service.py`, `tests/unit/core/services/test_injection_orchestrator.py`
- **Description:** `FrameMappingProject`, `GameFrame`, and `AIFrame` are frequently mocked using `Mock(spec=...)`. These are lightweight data holders; mocking them adds setup complexity and obscures errors in how services access their attributes.
- **Severity:** Medium (Makes tests harder to read and maintain).

### Mocked Too Deep (Patch Soup)
- **Files:** `tests/unit/ui/frame_mapping/services/test_preview_service.py`, `tests/unit/ui/frame_mapping/facades/test_injection_facade.py`
- **Description:** Tests that patch multiple layers of the system (e.g., repository → renderer → image converter) simultaneously. This creates a "synthetic world" where the test passes even if the integration between these components is broken.
- **Severity:** Medium (Lowers confidence in true system behavior).

### Mocking Where Real Lightweight Dependencies Are Better
- **Files:** `tests/unit/ui/frame_mapping/test_dialog_coordinator.py`
- **Description:** Patches `SpriteSelectionDialog` entirely. This prevents verifying that the coordinator actually passes valid data or handles dialog results correctly.
- **Severity:** Low (Mainly a missed opportunity for better coverage).

---

## 2. Rewrite Suggestions

| Offender | Stop Mocking | Replace With | Assert Instead |
| :--- | :--- | :--- | :--- |
| **Logic Helpers** | Private pane attributes | Real `WorkspaceStateManager` + Fake Panes | State manager values and "Fake" pane captured state. |
| **Services** | `FrameMappingProject` | Real `FrameMappingProject` instance | Side effects on the project (e.g., `mapping.status`). |
| **Preview/Palette** | `CaptureResultRepository` | Real `CaptureResultRepository` (it's a lightweight cache) | Actual data returned from the service. |
| **Dialog Coords** | Dialog classes | Real Dialogs (if headless-safe) or a "Fake" factory | Data passed to the dialog and coordinator's response to results. |

---

## 3. Repo-Wide Testing Guidelines

1. **Data Models are Real:** Never mock `FrameMappingProject`, `GameFrame`, `AIFrame`, or `SheetPalette`. They are plain-old-Python-objects (POPOs) or dataclasses. Using real objects ensures your tests respect their schema.
2. **State over Interaction:** Prefer `assert project.get_mapping(...).status == "injected"` over `assert mock_pane.set_status.called`. Testing state changes is significantly less brittle than testing method call counts.
3. **Use "Fakes" for UI Boundaries:** If a UI component (like a Pane) is too heavy for unit tests, implement a lightweight `FakePane` class that records calls in public attributes. This is cleaner and more type-safe than `MagicMock`.
4. **Leverage `populated_controller`:** Reuse the high-quality fixtures found in `tests/unit/ui/frame_mapping/conftest.py` which provide a pre-wired, real environment for testing logic.
5. **Real Files for Real IO:** Use `tmp_path` and real (small) sample files for tests involving JSON parsing or image loading. The project already has `MINIMAL_PNG_DATA` and `create_test_capture` helpers—use them.
6. **No `__new__` for DI:** If a class is too hard to instantiate in a test, it's a signal the class is doing too much or has tight coupling. Refactor the constructor instead of bypassing it.
