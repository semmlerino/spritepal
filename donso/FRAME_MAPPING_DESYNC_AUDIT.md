# Frame Mapping Workflow Audit: UI-Logic Desynchronization

**Date:** 2026-01-25
**Scope:** End-to-end Frame Mapping (Extract → Edit → Inject)
**Focus:** State management, Palette integrity, and UI consistency.

## 1. State Map & Sources of Truth

The system currently suffers from "Split-Brain" state management where the UI Views (Panes) act as competing sources of truth against the Domain Model and State Manager.

| Concept | Primary Source of Truth | Shadow/Competing Sources | Invalidation Trigger |
| :--- | :--- | :--- | :--- |
| **Project Data** | `FrameMappingProject` (Model) | `FrameMappingRepository` (Disk), `FrameMappingController._project` | `project_changed` signal |
| **Selection (AI)** | **Ambiguous**: `AIFramesPane` (View) vs `WorkspaceStateManager` | `FrameMappingWorkspace._state.selected_ai_frame_id` | User click, Auto-advance |
| **Selection (Game)** | **Ambiguous**: `CapturesLibraryPane` (View) vs `WorkspaceStateManager` | `FrameMappingWorkspace._state.selected_game_id` | User click |
| **Active Palette** | `FrameMappingProject.sheet_palette` | `PaletteService` (Logic), `SheetPaletteWidget` (UI), `EditorPalettePanel` (UI) | `sheet_palette_changed` |
| **Palette Indices** | **NONE** (Indices are transient/lossy) | `AIFrame` (PNG on disk), `SheetPalette.color_mappings` (Dict RGB->Int) | Injection (Re-quantization) |
| **Alignment** | `FrameMapping` (Model) | `WorkbenchCanvas` (UI local state), `MappingPanel` (UI table) | `alignment_updated` |

### Critical Architectural Weakness: Pane-driven Selection
`FrameMappingWorkspace` methods like `_get_selected_ai_frame_id()` prefer `pane.get_selected_id()` over the internal state manager.
*   **Risk**: If a frame is filtered out (e.g., "Unmapped Only"), it cannot be selected in the list.
*   **Result**: The pane reports `None`, causing the workspace to deselect the frame internally, even if the user didn't request a deselection (e.g., during Undo/Redo or data refresh).

## 2. Desync Bug Inventory

| Priority | Symptom | Root Cause | Impact | Fix Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **CRITICAL** | **Palette Index Amnesia**: User paints specific palette indices (e.g., to distinguish two identical colors), but injection ignores them. | **RGBA Round-trip**: `InjectionOrchestrator` converts source images to RGBA for compositing, destroying index data. Re-quantization uses RGB matching, collapsing identical colors to a single index. | **Data Loss**: Advanced masking/palette tricks are impossible. The "Palette Editor" is misleading. | **Pass Indexed Data**: Refactor `SpriteCompositor` to handle indexed images or pass a separate "Index Map" through the pipeline. |
| **HIGH** | **Selection Loss on Filter**: Filtering the list (e.g., "Unmapped Only") deselects the current frame if it gets hidden. | **View-Coupled State**: Workspace queries the ListWidget for selection state. If the item isn't visible, it's not "selected". | **UX Frustration**: User loses context when toggling filters or searching. | **Decouple Selection**: Make `WorkspaceStateManager` the absolute truth. Panes only *reflect* state, they don't *define* it. |
| **MEDIUM** | **Canvas Edit Block**: User selects a game frame in library, tries to align AI frame, but nothing happens. | **Context Guard**: `_on_alignment_changed` blocks edits if `current_canvas_game_id` != `mapping.game_frame_id`. Selecting a game frame updates the canvas but not the mapping context. | **Confusion**: UI looks interactive but ignores input. | **Explicit Modes**: Differentiate "Browsing Mode" (preview only) from "Mapping Mode" (alignment active). |
| **MEDIUM** | **Stale Previews**: Game Frame previews don't update if the underlying ROM data changes. | **Cache Invalidation**: Previews are cached by Capture ID/Mtime. They don't track the ROM data that would be used if "Re-injected". | **Misleading UI**: User thinks "Reuse ROM" worked, but preview shows old state. | **ROM Dependency**: Include ROM hash/timestamp in preview cache key for "simulated" views. |

## 3. Palette-Specific Deep Dive

The Palette pipeline is currently **lossy and non-deterministic** for ambiguous colors.

1.  **Editing**: `AIFramePaletteEditorWindow` saves a valid P-mode (Indexed) PNG.
    *   *State*: Correct indices on disk.
2.  **Loading**: `InjectionOrchestrator` loads `Image.open(...).convert("RGBA")`.
    *   *State*: **Indices DESTROYED**. (255, 0, 0) is just red; origin index (5 vs 6) is lost.
3.  **Compositing**: `SpriteCompositor` performs affine transforms (scale/flip) on RGBA data.
4.  **Injection**: `quantize_with_mappings` maps RGB back to indices.
    *   *State*: Uses `SheetPalette.color_mappings` (RGB -> Int).
    *   *Defect*: This dict can only map (255, 0, 0) to *one* index (e.g., 5). Any pixels intended to be 6 are forced to 5.

**Verdict**: The current architecture cannot support "Index Painting" (where the user manually assigns indices to pixels of the same color). The `AIFramePaletteEditorWindow` promises functionality the engine cannot deliver.

## 4. Invariants & Assertions

To prevent future regression, the following invariants must be enforced:

1.  **Selection Integrity**:
    *   `pane.get_selected_id() == state_manager.selected_id` (unless pane is filtering it out).
    *   *Assertion*: Workspace should log warning if pane reports `None` while state manager has ID.

2.  **Palette Conservation**:
    *   `unique_indices(source_image) <= unique_indices(injected_image)` (Indices shouldn't disappear).
    *   *Assertion*: `InjectionOrchestrator` should warn if the number of unique colors in the input PNG > number of unique indices in the output tiles.

3.  **Mapping Consistency**:
    *   `mapping.game_frame_id` must always exist in `project.game_frames`.
    *   *Assertion*: `FrameMappingProject` validation on load.

## 5. Recommendations (Ranked)

1.  **Refactor Injection Pipeline for Index Preservation (High Effort / High Value)**
    *   Modify `SpriteCompositor` to accept an optional `index_map` (or work in P-mode if no transforms are applied).
    *   If transforms *are* applied, warn the user that index precision will be lost.
    *   Change `SheetPalette` to support spatial/pixel-perfect index mapping if needed (complex).
    *   *Immediate Mitigation*: Warn users in `Palette Editor` that index painting only works if colors are unique.

2.  **Decouple Selection State (Medium Effort / High Value)**
    *   Move `selected_ai_frame_id` and `selected_game_id` exclusively to `WorkspaceStateManager` (or `FrameMappingController`).
    *   Panes listen to `selection_changed` signal to highlight rows.
    *   Panes emit `row_clicked` signals, but do not store "selection" as a logical state.

3.  **Fix "Split-Brain" Navigation (Low Effort / Medium Value)**
    *   In `_on_game_frame_selected`, only update the canvas if the user is *not* currently editing a mapping.
    *   Add a visual indicator (e.g., "Previewing Capture - Alignment Disabled") when browsing unrelated captures.

4.  **Automated Desync Detection (Debug Tool)**
    *   Add a "Debug State" panel (overlay) showing:
        *   Manager Selection vs Pane Selection.
        *   Current Palette Hash.
        *   Preview Cache Hit/Miss stats.