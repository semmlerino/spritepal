# Frame Mapping Tool Maintainability Assessment

## 1. Code Structure & Responsibility Boundaries
**Rating: Needs Work**

The tool follows a layered architecture (Core Model -> Controller -> Workspace -> Views), but responsibilities are blurred in the middle layers.

- **God Objects:** `FrameMappingController` (approx 800+ lines) is a massive facade that wraps `PreviewService`, `PaletteService`, `OrganizationService`, `InjectionOrchestrator`, and `UndoRedoStack`. It handles everything from project loading to image processing.
- **Complexity Shifting:** `WorkspaceLogicHelper` exists primarily to reduce the line count of `FrameMappingWorkspace`, not to create a clean architectural boundary. It has cyclic dependencies (injected via setters) with the workspace components, effectively acting as an extension of the workspace class rather than a standalone service.
- **Domain Logic Leakage:** While `FrameMappingProject` is mostly a data holder, it contains logic for index maintenance (`_rebuild_indices`) and consistency checks, which is good. However, some domain logic (like auto-alignment and linking rules) resides in `WorkspaceLogicHelper`, coupling business rules to the UI.

**Actionable Recommendations:**
- Break `FrameMappingController` into smaller, focused controllers: `ProjectController` (lifecycle), `InjectionController` (ROM ops), and `MappingController` (alignment/linking).
- Convert `WorkspaceLogicHelper` into true domain services (e.g., `AutoAlignmentService`) that don't depend on UI widgets (`AIFramesPane`, etc.).

## 2. Naming & Readability
**Rating: Good**

Naming is generally precise and intention-revealing.

- **Precise Naming:** Terms like `AIFrame`, `GameFrame`, `FrameMapping`, and `SheetPalette` are used consistently across the codebase.
- **Clear Intent:** Method names like `inject_mapping`, `update_mapping_alignment`, and `detect_stale_entries` clearly describe their side effects.
- **Confusion Points:** `WorkspaceLogicHelper` is a generic name that masks its true purpose (a "UI Logic Mixin"). `project` in the controller refers to the data model, which is fine, but `_state` in the workspace refers to `WorkspaceStateManager`, which can be confused with the project state.

**Actionable Recommendations:**
- Rename `WorkspaceLogicHelper` to something reflecting its role, or better yet, dissolve it into focused services.
- Renaming `_state` to `_ui_state` in `FrameMappingWorkspace` would clarify that it holds transient UI state (selection, etc.) vs persistent project state.

## 3. Documentation & Intent Signaling
**Rating: Acceptable**

Docstrings are present and generally high-quality, but some architectural "why" is missing.

- **Good:** `FrameMappingProject` has excellent docstrings explaining version history and data structures. `InjectionOrchestrator` clearly explains its UI-independent role.
- **Missing:** The complex relationship between `FrameMappingWorkspace`, `FrameMappingController`, and `WorkspaceLogicHelper` is not well-documented. A new developer would struggle to understand *where* a user action is actually handled without tracing signals.
- **"BUG-FIX" Comments:** There are specific comments like "BUG-1 FIX" and "Phase 5 fix". While helpful for history, these should eventually be refactored into the code's structure or moved to commit messages to avoid noise.

**Actionable Recommendations:**
- Add a high-level architectural diagram or description in `ui/frame_mapping/README.md` explaining the signal flow.
- Clean up "BUG-FIX" comments where the code has stabilized.

## 4. Error Handling & Edge Cases
**Rating: Good**

Failure modes are generally explicit and handled via a `Result` pattern or specific signals.

- **Explicit Results:** `InjectionOrchestrator` returns `InjectionResult` objects instead of throwing exceptions, allowing for rich error reporting (messages, success flags) without crashing the UI.
- **Signal-Based Error Propagation:** The controller emits `error_occurred` which the workspace catches to show alerts. This keeps the UI responsive.
- **Stale Data Handling:** There is robust logic for detecting "stale" capture entries (`detect_stale_entries`), preventing crashes when underlying files change.
- **Silent Failures:** Some lookups return `None` (e.g., `get_game_frame_by_id`). Callers mostly check this, but it relies on discipline.

**Actionable Recommendations:**
- Ensure all `None` returns from lookups are handled, perhaps by using `Optional` types strictly (which is already largely done).

## 5. Coupling & Dependencies
**Rating: Acceptable**

The core logic is somewhat decoupled, but the UI layer is tightly knit.

- **Core Decoupling:** `InjectionOrchestrator` is designed to be UI-independent, which is excellent. It can be run from a CLI or test harness.
- **UI Coupling:** `FrameMappingWorkspace` is tightly coupled to `FrameMappingController`. The controller is effectively a "backend for frontend" specific to this workspace.
- **Service Facade:** The controller's usage of services is good, but it hides the dependencies from the workspace, making the controller a bottleneck.
- **Helper Cycles:** `WorkspaceLogicHelper` depends on `AIFramesPane`, `CapturesLibraryPane`, etc., creating a tight web of references that makes isolated testing of the helper impossible.

**Actionable Recommendations:**
- Decouple `WorkspaceLogicHelper` from specific UI panes. Pass data (models) instead of widgets.

## 6. Extensibility & Change Risk
**Rating: Needs Work**

Adding new features requires touching multiple layers.

- **Rigid Model:** `FrameMappingProject` has hardcoded lists of `AIFrame` and `GameFrame`. Adding a new type of frame (e.g., "ReferenceFrame") would require modifying the class, serialization, controller, and UI.
- **Hardcoded Tags:** `FRAME_TAGS` is a `frozenset` in `FrameMappingProject`. Making this dynamic would require a schema change.
- **Injection Pipeline:** The `InjectionOrchestrator` is complex (`_inject_tile_group`). Changing the injection logic (e.g., adding a new compression format) involves navigating a large, procedural method.

**Actionable Recommendations:**
- Extract the compression/injection strategy into separate classes (e.g., `TileInjector` strategy pattern) to make `InjectionOrchestrator` closed for modification but open for extension.

## 7. Test Coverage & Testability
**Rating: Acceptable**

The architecture supports testing, but coverage of the "glue" code is likely low.

- **Testable Core:** `FrameMappingProject` and `InjectionOrchestrator` are easy to unit test.
- **Untestable UI Logic:** The logic inside `FrameMappingWorkspace` and `WorkspaceLogicHelper` is hard to test because it requires a running Qt event loop and instantiated widgets.
- **Controller Testing:** The controller can be tested if the underlying services are mocked, but its large surface area makes this tedious.

**Actionable Recommendations:**
- Prioritize unit tests for `InjectionOrchestrator` and `FrameMappingProject`.
- Refactor `WorkspaceLogicHelper` to be pure logic (no Qt widgets) so it can be tested.

## 8. Technical Debt & Maintenance Hazards
**Rating: Acceptable**

- **"Logic Helper" Pattern:** This is a code smell. It suggests the workspace is doing too much and needs better decomposition, not just code extraction.
- **Large Files:** `frame_mapping_controller.py` and `frame_mapping_workspace.py` are large and growing.
- **TODOs:** There are a few "Phase X fix" comments indicating ongoing refactoring or incomplete migrations.

# Top 5 Maintainability Risks

1.  **Controller Bloat:** `FrameMappingController` is a single point of failure and change contention. It handles too many disparate responsibilities (file I/O, injection, undo/redo, organization).
2.  **Untestable UI Logic:** `WorkspaceLogicHelper` contains critical business rules (linking, auto-alignment) but is tightly coupled to Qt widgets, making it resistant to automated testing.
3.  **Complex Injection Routine:** `_inject_tile_group` in `InjectionOrchestrator` is a complex procedural block handling multiple compression types and padding logic. It is a high-risk area for regressions.
4.  **Signal Sprawl:** The web of signals in `FrameMappingWorkspace` (`_connect_signals`) is dense and hard to trace. Debugging "who triggered this update" is difficult.
5.  **Project Schema Rigidity:** The `FrameMappingProject` structure (serialized as JSON) is tightly coupled to the class definitions. Breaking changes in the schema require careful migration logic.

# First Refactor Plan (2 Weeks)

1.  **Decompose Controller (Days 1-3):**
    -   Split `FrameMappingController` into `FrameMappingProjectController` (loading/saving, frame management) and `FrameMappingInjectionController` (injection orchestration).
    -   Keep the main `FrameMappingController` as a thinner coordinator if necessary, or inject sub-controllers directly into the workspace.

2.  **Refactor Logic Helper (Days 4-7):**
    -   Identify pure logic methods in `WorkspaceLogicHelper` (e.g., `find_next_unmapped_ai_frame`, `_auto_align_mapping`).
    -   Extract these into a `MappingService` or `AutoAlignmentService` that takes *data* (Frames) as input, not Widgets.
    -   Write unit tests for these new services.

3.  **Strategy Pattern for Injection (Days 8-10):**
    -   Refactor `_inject_tile_group` in `InjectionOrchestrator`. Create a `TileInjectionStrategy` interface with `RawInjectionStrategy` and `HalInjectionStrategy` implementations.
    -   This isolates the complex compression/padding logic and makes it individually testable.

4.  **Clean Up Signals (Days 11-12):**
    -   Review `FrameMappingWorkspace` signals. Group related signals (e.g., all palette-related signals) into dedicated helper objects or sub-components to reduce the noise in the main workspace file.
