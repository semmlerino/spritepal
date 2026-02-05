# Frame Mapping Signal Flow Documentation

**Last Updated:** 2026-02-05

This document describes all signal chains in the Frame Mapping subsystem with flow diagrams showing how signals propagate through the system during key operations.

---

## Table of Contents

1. [Signal Overview Table](#1-signal-overview-table)
2. [Signal Flow Diagrams](#2-signal-flow-diagrams)
3. [Causality Chains](#3-causality-chains)

---

## 1. Signal Overview Table

### Controller Signals (FrameMappingController)

| Signal Name | Source | Purpose | Connected Handlers |
|-------------|--------|---------|-------------------|
| `project_changed` | FrameMappingController:65 | Emitted when project is loaded/created/modified (structural changes) | Workspace: `_on_project_changed()` - refreshes all panes, canvas, mapping panel |
| `ai_frames_loaded` | FrameMappingController:66 | Emitted when AI frames are loaded | Workspace: `_on_ai_frames_loaded()` - shows count in status bar |
| `game_frame_added` | FrameMappingController:67 | Emitted when a game frame is added | Workspace: `_on_game_frame_added()` - shows status message |
| `game_frame_removed` | FrameMappingController:68 | Emitted when a game frame is removed | (No direct handler - handled via `project_changed`) |
| `mapping_created` | FrameMappingController:69 | Emitted when a mapping is created | (Tracked internally, triggers `project_changed`) |
| `mapping_displaced` | FrameMappingController:152 | Emitted when a mapping creation displaces existing mappings (1:1 enforcement) | Workspace: `_on_mapping_displaced()` - updates displaced frames |
| `mapping_removed` | FrameMappingController:70 | Emitted when a mapping is removed | (Tracked internally, triggers `project_changed`) |
| `mapping_injected` | FrameMappingController:71 | Emitted when injection succeeds | Workspace: `_on_mapping_injected()` - shows success dialog |
| `error_occurred` | FrameMappingController:72 | Emitted on errors | Workspace: `_on_error()` - displays error dialog |
| `status_update` | FrameMappingController:73 | Emitted for UI status messages | Workspace: `_on_status_update()` - shows in status bar |
| `save_requested` | FrameMappingController:74 | Emitted when auto-save should occur | Workspace: `_auto_save_after_injection()` |
| `stale_entries_warning` | FrameMappingController:75 | Emitted when stored entry IDs are stale | Workspace: `_on_stale_entries_warning()` - shows canvas warning |
| `alignment_updated` | FrameMappingController:76 | Emitted when alignment changes (not structural) | Workspace: `_on_alignment_updated()` - updates mapping panel row only |
| `sheet_palette_changed` | FrameMappingController:77 | Emitted when sheet palette is set/cleared | Workspace: `_on_sheet_palette_changed()` - syncs palette to panes |
| `frame_renamed` | FrameMappingController:79 | Emitted when AI frame display name changes | Workspace: `_on_frame_organization_changed()` - refreshes AI pane |
| `frame_tags_changed` | FrameMappingController:80 | Emitted when AI frame tags change | Workspace: `_on_frame_organization_changed()` - refreshes AI pane |
| `capture_renamed` | FrameMappingController:82 | Emitted when game frame display name changes | Workspace: `_on_capture_organization_changed()` - refreshes captures pane |
| `capture_import_requested` | FrameMappingController:86 | Emitted when capture parsed, workspace shows dialog | Workspace: `_on_capture_import_requested()` - queues dialog |
| `can_undo_changed` | FrameMappingController:88 | Emitted when undo availability changes | (Future: will enable/disable undo button) |
| `can_redo_changed` | FrameMappingController:89 | Emitted when redo availability changes | (Future: will enable/disable redo button) |

### Preview Service Signals (PreviewService)

| Signal Name | Source | Purpose | Connected Handlers |
|-------------|--------|---------|-------------------|
| `stale_entries_warning` | PreviewService:36 | Emitted when stored entry IDs are stale | Controller (forwarded) → Workspace: shows warning |

### Palette Service Signals (PaletteService)

| Signal Name | Source | Purpose | Connected Handlers |
|-------------|--------|---------|-------------------|
| `sheet_palette_changed` | PaletteService:35 | Emitted when sheet palette is modified | Controller (forwarded) → Workspace: syncs palette |

### Organization Service Signals (OrganizationService)

| Signal Name | Source | Purpose | Connected Handlers |
|-------------|--------|---------|-------------------|
| `frame_renamed` | OrganizationService:32 | Emitted when AI frame display name changes | Controller (forwarded) → Workspace: refreshes pane |
| `frame_tags_changed` | OrganizationService:33 | Emitted when AI frame tags change | Controller (forwarded) → Workspace: refreshes pane |
| `capture_renamed` | OrganizationService:34 | Emitted when game frame display name changes | Controller (forwarded) → Workspace: refreshes pane |

### Dialog Coordinator Signals (DialogCoordinator)

| Signal Name | Source | Purpose | Connected Handlers |
|-------------|--------|---------|-------------------|
| `dialog_completed` | DialogCoordinator:43 | Emitted when a dialog completes | (Used internally for tracking) |
| `capture_import_completed` | DialogCoordinator:44 | Emitted when capture import succeeds | (Used internally for tracking) |
| `queue_processing_finished` | DialogCoordinator:45 | Emitted when batch import queue completes | Workspace: `_on_capture_queue_finished()` - shows count |

### AI Frames Pane Signals (AIFramesPane)

| Signal Name | Source | Purpose | Connected Handlers |
|-------------|--------|---------|-------------------|
| `ai_frame_selected` | AIFramesPane:80 | Emitted when an AI frame is selected | Workspace: `_on_ai_frame_selected()` - syncs canvas/drawer |
| `map_requested` | AIFramesPane:81 | Emitted when user clicks Map button | Workspace: `_on_map_selected()` - creates mapping |
| `auto_advance_changed` | AIFramesPane:82 | Emitted when auto-advance toggle changes | Workspace: `_on_auto_advance_changed()` - updates state |
| `edit_in_sprite_editor_requested` | AIFramesPane:83 | Emitted when user requests edit | Workspace: `_on_edit_frame()` - emits to main window |
| `edit_frame_palette_requested` | AIFramesPane:84 | Emitted when user wants to edit palette indices | Workspace: `_on_edit_frame_palette()` - opens palette editor |
| `remove_from_project_requested` | AIFramesPane:85 | Emitted when user requests removal | Workspace: `_on_remove_ai_frame()` - removes frame |
| `palette_edit_requested` | AIFramesPane:87 | Emitted when user wants to edit sheet palette | Workspace: `_on_palette_edit_requested()` - opens dialog |
| `palette_extract_requested` | AIFramesPane:88 | Emitted when user wants to extract palette | Workspace: `_on_palette_extract_requested()` - generates palette |
| `palette_clear_requested` | AIFramesPane:89 | Emitted when user wants to clear palette | Workspace: `_on_palette_clear_requested()` - clears palette |
| `palette_color_changed` | AIFramesPane:92 | Emitted when user edits a palette color | Workspace: `_on_palette_color_changed()` - updates controller |
| `palette_swatch_hovered` | AIFramesPane:93 | Emitted when user hovers palette swatch | Workspace: `_on_palette_swatch_hovered()` - highlights canvas pixels |
| `folder_dropped` | AIFramesPane:95 | Emitted when folder dropped on pane | Workspace: `_on_ai_folder_dropped()` - loads frames |
| `tab_folder_changed` | AIFramesPane:96 | Emitted when active tab's folder changes | Workspace: `_on_ai_tab_folder_changed()` - reloads frames |
| `frame_rename_requested` | AIFramesPane:98 | Emitted when user renames frame | Workspace: `_on_frame_rename_requested()` - updates display name |
| `frame_tag_toggled` | AIFramesPane:99 | Emitted when user toggles frame tag | Workspace: `_on_frame_tag_toggled()` - updates tags |

### Captures Library Pane Signals (CapturesLibraryPane)

| Signal Name | Source | Purpose | Connected Handlers |
|-------------|--------|---------|-------------------|
| `game_frame_selected` | CapturesLibraryPane:56 | Emitted when a game frame is selected | Workspace: `_on_game_frame_selected()` - updates canvas preview |
| `edit_in_sprite_editor_requested` | CapturesLibraryPane:57 | Emitted when user requests edit | Workspace: `_on_edit_game_frame()` - emits to main window |
| `delete_capture_requested` | CapturesLibraryPane:58 | Emitted when user requests deletion | Workspace: `_on_delete_capture()` - removes game frame |
| `show_details_requested` | CapturesLibraryPane:59 | Emitted when user wants to see details | Workspace: `_on_show_capture_details()` - shows info dialog |
| `capture_rename_requested` | CapturesLibraryPane:60 | Emitted when user wants to rename | Workspace: `_on_capture_rename_requested()` - updates display name |

### Mapping Panel Signals (MappingPanel)

| Signal Name | Source | Purpose | Connected Handlers |
|-------------|--------|---------|-------------------|
| `mapping_selected` | MappingPanel:61 | Emitted when a mapping row is selected | Workspace: `_on_mapping_selected()` - syncs AI pane/canvas |
| `edit_frame_requested` | MappingPanel:62 | Emitted when user clicks Edit Frame | Workspace: `_on_edit_frame()` - emits to main window |
| `remove_mapping_requested` | MappingPanel:63 | Emitted when user requests removal | Workspace: `_on_remove_mapping()` - removes mapping |
| `adjust_alignment_requested` | MappingPanel:64 | Emitted when user clicks Adjust | Workspace: `_on_adjust_alignment()` - focuses canvas |
| `drop_game_frame_requested` | MappingPanel:65 | Emitted when game frame dropped on row | Workspace: `_on_drop_game_frame()` - creates/replaces mapping |
| `inject_mapping_requested` | MappingPanel:66 | Emitted when user requests injection | Workspace: `_on_inject_single()` - injects single frame |
| `inject_selected_requested` | MappingPanel:67 | Emitted when user requests batch injection | Workspace: `_on_inject_selected()` - injects checked frames |

### Workbench Canvas Signals (WorkbenchCanvas)

| Signal Name | Source | Purpose | Connected Handlers |
|-------------|--------|---------|-------------------|
| `alignment_changed` | WorkbenchCanvas:200+ | Emitted when user adjusts alignment | Workspace: `_on_alignment_changed()` - updates controller |
| `compression_type_changed` | WorkbenchCanvas:200+ | Emitted when user changes compression | Workspace: `_on_compression_type_changed()` - updates game frame |
| `apply_transforms_to_all_requested` | WorkbenchCanvas:200+ | Emitted when user requests bulk apply | Workspace: `_on_apply_transforms_to_all()` - updates all mappings |
| `pixel_hovered` | WorkbenchCanvas:200+ | Emitted when mouse hovers pixel | Workspace: `_on_pixel_hovered()` - highlights palette swatch |
| `pixel_left` | WorkbenchCanvas:200+ | Emitted when mouse leaves canvas | Workspace: `_on_pixel_left()` - clears palette highlight |
| `eyedropper_picked` | WorkbenchCanvas:200+ | Emitted when eyedropper picks color | Workspace: `_on_eyedropper_picked()` - selects palette swatch |
| `zoom_changed` | WorkbenchCanvas:200+ | Emitted when view zoom changes | (Internal - updates zoom label) |

### Workspace Signals (FrameMappingWorkspace)

| Signal Name | Source | Purpose | Connected Handlers |
|-------------|--------|---------|-------------------|
| `edit_in_sprite_editor_requested` | FrameMappingWorkspace:78 | Request to edit a frame in sprite editor | MainWindow:1537 → `_on_edit_frame_from_mapping()` - switches to sprite editor, jumps to first ROM offset |

---

## 2. Signal Flow Diagrams

### a. Create Mapping Flow

User creates a link between AI frame and game frame.

```
User Action: Click "Map Selected" or Drag-Drop Game Frame
    │
    ├─→ [AIFramesPane] map_requested
    │       └─→ [Workspace] _on_map_selected()
    │               └─→ _attempt_link(ai_id, game_id)
    │
    └─→ [MappingPanel] drop_game_frame_requested(ai_id, game_id)
            └─→ [Workspace] _on_drop_game_frame()
                    └─→ _attempt_link(ai_id, game_id)

[Workspace] _attempt_link()
    ├─→ Check existing links → Show confirmation dialogs if needed
    └─→ [Controller] create_mapping(ai_id, game_id)
            ├─→ [UndoStack] push(CreateMappingCommand)
            ├─→ [Project] create_mapping()
            └─→ [Controller] mapping_created.emit(ai_id, game_id)

[Controller] mapping_created + project_changed signals
    └─→ [Workspace] _on_project_changed()
            ├─→ Refresh AI frames pane status
            ├─→ Refresh captures library link status
            ├─→ Refresh mapping panel
            └─→ Update canvas with alignment

Auto-Advance (if enabled)
    └─→ [Workspace] Find next unmapped frame
            └─→ [AIFramesPane] select_frame(next_index)
                    └─→ ai_frame_selected.emit(next_id)
```

**Key Files:**
- `ui/workspaces/frame_mapping_workspace.py:619-1582` (_on_map_selected, _attempt_link)
- `ui/frame_mapping/controllers/frame_mapping_controller.py:452-519` (create_mapping)

---

### b. Frame Selection Flow

User clicks an AI frame, triggering canvas and drawer sync.

```
User Action: Click AI Frame in Left Pane
    │
    └─→ [AIFramesPane] ai_frame_selected.emit(ai_frame_id)
            └─→ [Workspace] _on_ai_frame_selected(frame_id)
                    ├─→ Load AI frame into canvas
                    ├─→ [MappingPanel] select_row_by_ai_id(frame_id)
                    ├─→ Check for existing mapping
                    │       └─→ If mapped:
                    │               ├─→ Load game frame preview
                    │               ├─→ Set alignment on canvas
                    │               ├─→ [CapturesPane] select_frame(game_id)
                    │               └─→ Update state tracking
                    └─→ Update Map button state

Alternative: User Clicks Mapping in Drawer
    │
    └─→ [MappingPanel] mapping_selected.emit(ai_frame_id)
            └─→ [Workspace] _on_mapping_selected(ai_frame_id)
                    ├─→ [AIFramesPane] select_frame(ai_index)
                    ├─→ Load frames into canvas
                    └─→ [CapturesPane] select_frame(game_id)
```

**Key Files:**
- `ui/workspaces/frame_mapping_workspace.py:484-540, 572-616` (_on_ai_frame_selected, _on_mapping_selected)
- `ui/frame_mapping/views/ai_frames_pane.py:80` (signal definition)

---

### c. Capture Import Flow

User imports a Mesen 2 capture file, triggering sprite selection dialog.

```
User Action: Click "Import Capture" or "Import Directory"
    │
    ├─→ [Workspace] _on_import_capture()
    │       └─→ [Controller] import_mesen_capture(path)
    │
    └─→ [Workspace] _on_import_capture_dir()
            └─→ [Controller] import_capture_directory(dir_path)

[Controller] import_mesen_capture(capture_path)
    ├─→ Parse capture file via MesenCaptureParser
    └─→ [Controller] capture_import_requested.emit(capture_result, capture_path)
            └─→ [Workspace] _on_capture_import_requested()
                    ├─→ [DialogCoordinator] queue_capture_import()
                    └─→ If queue size == 1:
                            └─→ [DialogCoordinator] process_capture_import_queue()

[DialogCoordinator] process_capture_import_queue()
    ├─→ Show SpriteSelectionDialog
    ├─→ User selects entries → dialog.exec() returns Accepted
    ├─→ [Controller] complete_capture_import(path, result, selected_entries)
    │       ├─→ [CaptureRenderer] render_selection() → generate preview
    │       ├─→ [PreviewService] set_preview_cache()
    │       ├─→ [Project] add_game_frame()
    │       ├─→ [Controller] game_frame_added.emit(frame_id)
    │       ├─→ [Controller] project_changed.emit()
    │       └─→ [Controller] save_requested.emit()
    │
    ├─→ Pop from queue
    └─→ Recursive call for next capture

[DialogCoordinator] All captures processed
    └─→ queue_processing_finished.emit(import_count)
            └─→ [Workspace] _on_capture_queue_finished()
                    └─→ Show status message
```

**Key Files:**
- `ui/workspaces/frame_mapping_workspace.py:1831-1861` (_on_import_capture, _on_import_capture_dir)
- `ui/frame_mapping/controllers/frame_mapping_controller.py:297-422` (import_mesen_capture, complete_capture_import)
- `ui/frame_mapping/dialog_coordinator.py:160-205` (queue management)

---

### d. Injection Flow

User injects one or more mapped frames into ROM.

```
User Action: Click "Inject All" / "Inject Selected" / "Inject to ROM"
    │
    ├─→ [Workspace] _on_inject_all()
    ├─→ [Workspace] _on_inject_selected()
    └─→ [MappingPanel] inject_mapping_requested.emit(ai_id)
            └─→ [Workspace] _on_inject_single(ai_id)

[Workspace] Injection Handler
    ├─→ Validate ROM path
    ├─→ Check reuse ROM option
    ├─→ Show confirmation dialog
    ├─→ Create/reuse injection ROM copy
    └─→ [Controller] inject_mapping(ai_id, rom_path, output_path)

[Controller] inject_mapping()
    ├─→ Build InjectionRequest
    ├─→ [InjectionOrchestrator] execute(request, project, debug_ctx)
    │       ├─→ Load AI frame image
    │       ├─→ Load game frame capture
    │       ├─→ Apply palette mapping
    │       ├─→ Composite AI onto game frame
    │       ├─→ Sample tiles from composite
    │       ├─→ Compress tiles (HAL or RAW)
    │       ├─→ Inject into ROM at offsets
    │       └─→ Return InjectionResult
    │
    ├─→ If stale entries detected:
    │       └─→ [Controller] stale_entries_warning.emit(frame_id)
    │               └─→ [Workspace] _on_stale_entries_warning()
    │                       ├─→ Track for retry option
    │                       └─→ [Canvas] show warning label
    │
    ├─→ If successful:
    │       ├─→ Update mapping status to "injected"
    │       ├─→ [Controller] mapping_injected.emit(ai_id, message)
    │       │       └─→ [Workspace] _on_mapping_injected()
    │       │               ├─→ Show success dialog
    │       │               └─→ Refresh UI
    │       │
    │       ├─→ [Controller] project_changed.emit()
    │       └─→ [Controller] save_requested.emit()
    │               └─→ [Workspace] _auto_save_after_injection()
    │
    └─→ If failed:
            └─→ [Controller] error_occurred.emit(message)
                    └─→ [Workspace] _on_error()
                            └─→ Show error dialog
```

**Key Files:**
- `ui/workspaces/frame_mapping_workspace.py:1059-1313` (injection handlers)
- `ui/frame_mapping/controllers/frame_mapping_controller.py:946-1054` (inject_mapping)
- `core/services/injection_orchestrator.py` (injection pipeline)

---

### e. Preview Generation Flow

Preview pixmap needed for thumbnail display, cache miss triggers regeneration.

```
Request: Get Preview for Game Frame
    │
    └─→ [Controller] get_game_frame_preview(frame_id)
            └─→ [PreviewService] get_preview(frame_id, project)
                    ├─→ Check cache: (pixmap, mtime, entry_ids)
                    │       └─→ If cache valid → return cached pixmap
                    │
                    ├─→ Cache invalid or missing:
                    │       ├─→ [PreviewService] get_capture_result_for_game_frame()
                    │       │       ├─→ Parse capture file
                    │       │       ├─→ Filter by selected_entry_ids
                    │       │       └─→ If stale entries:
                    │       │               ├─→ [PreviewService] stale_entries_warning.emit()
                    │       │               │       └─→ [Controller] (forwards to Workspace)
                    │       │               └─→ Fallback to rom_offset filtering
                    │       │
                    │       ├─→ [CaptureRenderer] render_selection()
                    │       ├─→ Convert PIL Image → QPixmap
                    │       └─→ Cache with (pixmap, mtime, entry_ids)
                    │
                    └─→ Return new pixmap

Preview Cache Invalidation Triggers:
    ├─→ Capture file mtime changed
    ├─→ selected_entry_ids changed
    └─→ Manual invalidation via invalidate(frame_id)
```

**Key Files:**
- `ui/frame_mapping/services/preview_service.py:48-124` (get_preview)

---

### f. Palette Copy Flow

User copies a palette from a game frame to the sheet palette.

```
User Action: Right-click AI Frames Palette → "Extract from Capture..."
    │
    └─→ [AIFramesPane] palette_extract_requested.emit()
            └─→ [Workspace] _on_palette_extract_requested()
                    └─→ [Controller] extract_sheet_colors()
                    │       └─→ [PaletteService] extract_sheet_colors(project)
                    │               └─→ Loop all AI frames
                    │                       └─→ Extract unique RGB colors
                    │
                    └─→ [Controller] generate_sheet_palette_from_colors(colors)
                            └─→ [PaletteService] generate_sheet_palette_from_colors()
                                    ├─→ Quantize to 16 colors
                                    ├─→ Auto-map AI colors → palette indices
                                    └─→ Return SheetPalette

Alternative: Copy from Game Frame
    │
    └─→ [AIFramesPane] palette_edit_requested.emit()
            └─→ [Workspace] _on_palette_edit_requested()
                    └─→ Show SheetPaletteMappingDialog
                            └─→ User selects game frame
                                    └─→ [Controller] copy_game_palette_to_sheet(game_id)
                                            └─→ [PaletteService] copy_game_palette_to_sheet()

[Controller] set_sheet_palette(palette)
    └─→ [PaletteService] set_sheet_palette(project, palette)
            ├─→ [Project] sheet_palette = palette
            └─→ [PaletteService] sheet_palette_changed.emit()
                    └─→ [Controller] (forwards signal)
                            └─→ [Workspace] _on_sheet_palette_changed()
                                    ├─→ [AIFramesPane] set_sheet_palette()
                                    └─→ [Canvas] set_sheet_palette()
```

**Key Files:**
- `ui/workspaces/frame_mapping_workspace.py:1376-1446` (palette handlers)
- `ui/frame_mapping/services/palette_service.py:58-239` (palette operations)

---

### g. Frame Rename Flow

User renames an AI frame or game frame (display name only, not file).

```
User Action: Right-click AI Frame → Rename
    │
    └─→ [AIFramesPane] frame_rename_requested.emit(frame_id, display_name)
            └─→ [Workspace] _on_frame_rename_requested()
                    └─→ [Controller] rename_frame(frame_id, display_name)
                            └─→ [OrganizationService] rename_frame()
                                    ├─→ [UndoStack] push(RenameAIFrameCommand)
                                    ├─→ [Project] set_frame_display_name()
                                    └─→ [OrganizationService] frame_renamed.emit(frame_id)
                                            └─→ [Controller] (forwards signal)
                                                    └─→ [Workspace] _on_frame_organization_changed()
                                                            └─→ [AIFramesPane] refresh_frame(frame_id)

User Action: Right-click Capture → Rename
    │
    └─→ [CapturesPane] capture_rename_requested.emit(frame_id, new_name)
            └─→ [Workspace] _on_capture_rename_requested()
                    └─→ [Controller] rename_capture(frame_id, new_name)
                            └─→ [OrganizationService] rename_capture()
                                    ├─→ [UndoStack] push(RenameCaptureCommand)
                                    ├─→ [Project] set_capture_display_name()
                                    └─→ [OrganizationService] capture_renamed.emit(frame_id)
                                            └─→ [Controller] (forwards signal)
                                                    └─→ [Workspace] _on_capture_organization_changed()
                                                            └─→ [CapturesPane] refresh_frame(frame_id)
```

**Key Files:**
- `ui/workspaces/frame_mapping_workspace.py:1786-1829` (rename handlers)
- `ui/frame_mapping/services/organization_service.py:46-309` (rename operations)

---

### h. Project Load Flow

User loads a saved project file, triggering full UI refresh.

```
User Action: Click "Load" → Select Project File
    │
    └─→ [Workspace] _on_load_project()
            └─→ [Controller] load_project(path)
                    ├─→ [Repository] load(path)
                    │       └─→ Deserialize JSON → FrameMappingProject
                    │
                    ├─→ [PreviewService] invalidate_all()
                    ├─→ [UndoStack] clear()
                    └─→ [Controller] project_changed.emit()
                            └─→ [Workspace] _on_project_changed()
                                    ├─→ Clear canvas (if project identity changed)
                                    ├─→ [AIFramesPane] set_ai_frames(project.ai_frames)
                                    ├─→ [AIFramesPane] set_sheet_palette(project.sheet_palette)
                                    ├─→ [Canvas] set_sheet_palette(project.sheet_palette)
                                    ├─→ [CapturesPane] set_game_frames(project.game_frames)
                                    ├─→ [MappingPanel] set_project(project)
                                    ├─→ _refresh_mapping_status()
                                    │       └─→ [AIFramesPane] set_mapping_status(status_map)
                                    ├─→ _refresh_game_frame_link_status()
                                    │       └─→ [CapturesPane] set_link_status(link_status)
                                    └─→ _update_mapping_panel_previews()
                                            ├─→ Generate previews for all game frames
                                            ├─→ [MappingPanel] set_game_frame_previews()
                                            ├─→ [MappingPanel] refresh()
                                            └─→ [CapturesPane] set_game_frame_previews()
```

**Key Files:**
- `ui/workspaces/frame_mapping_workspace.py:1863-1876` (_on_load_project)
- `ui/frame_mapping/controllers/frame_mapping_controller.py:200-219` (load_project)
- `ui/workspaces/frame_mapping_workspace.py:417-458` (_on_project_changed)

---

### i. Undo/Redo Flow

User triggers undo/redo via keyboard shortcut (Ctrl+Z / Ctrl+Y).

```
User Action: Press Ctrl+Z (Undo)
    │
    └─→ [Workspace] QShortcut → _on_undo()
            └─→ [Controller] undo()
                    ├─→ [UndoStack] undo()
                    │       ├─→ Pop command from undo stack
                    │       ├─→ [Command] undo() (calls service _no_history methods via CommandContext)
                    │       └─→ Return command description
                    │
                    ├─→ [Controller] project_changed.emit()
                    │       └─→ [Workspace] Full UI refresh
                    │
                    ├─→ [Controller] save_requested.emit()
                    │       └─→ Auto-save project
                    │
                    └─→ [Workspace] Show "Undo: <description>" in status bar
                            ├─→ _refresh_mapping_status()
                            ├─→ _refresh_game_frame_link_status()
                            └─→ _update_mapping_panel_previews()

User Action: Press Ctrl+Y (Redo)
    │
    └─→ [Workspace] QShortcut → _on_redo()
            └─→ [Controller] redo()
                    └─→ Same flow as undo, but pushes command back onto stack

Undo/Redo Availability Updates
    │
    └─→ [UndoStack] can_undo_changed.emit(bool)
    │       └─→ [Controller] (forwards signal)
    │               └─→ (Future: enable/disable undo button)
    │
    └─→ [UndoStack] can_redo_changed.emit(bool)
            └─→ [Controller] (forwards signal)
                    └─→ (Future: enable/disable redo button)

Supported Undoable Operations:
    ├─→ CreateMappingCommand (mapping creation)
    ├─→ RemoveMappingCommand (mapping removal)
    ├─→ UpdateAlignmentCommand (alignment/scale changes)
    ├─→ RenameAIFrameCommand (frame renaming)
    ├─→ RenameCaptureCommand (capture renaming)
    └─→ ToggleFrameTagCommand (tag toggling)
```

**Key Files:**
- `ui/workspaces/frame_mapping_workspace.py:382-406` (_on_undo, _on_redo)
- `ui/frame_mapping/controllers/frame_mapping_controller.py:125-161` (undo/redo API)
- `ui/frame_mapping/undo.py` (command classes)

---

### j. Auto-Advance Flow

After creating a mapping with auto-advance enabled, automatically select the next unmapped frame.

```
[Workspace] _attempt_link() → Mapping Created
    │
    └─→ If auto_advance_enabled:
            ├─→ _find_next_unmapped_ai_frame(current_index)
            │       └─→ Search project.ai_frames for next unmapped frame
            │
            └─→ If next_unmapped_id found:
                    ├─→ [AIFramesPane] select_frame(next_frame.index)
                    │       └─→ ai_frame_selected.emit(next_unmapped_id)
                    │               └─→ [Workspace] _on_ai_frame_selected()
                    │
                    └─→ Canvas/Drawer sync as per Frame Selection Flow (b)

Auto-Advance Toggle:
    │
    └─→ [AIFramesPane] QCheckBox toggled
            └─→ auto_advance_changed.emit(enabled)
                    └─→ [Workspace] _on_auto_advance_changed()
                            └─→ self._state.auto_advance_enabled = enabled
```

**Key Files:**
- `ui/workspaces/frame_mapping_workspace.py:1574-1610` (auto-advance logic)
- `ui/workspaces/frame_mapping_workspace.py:412-415` (_on_auto_advance_changed)

---

## 3. Causality Chains

### Mapping Creation → Full UI Update Cascade

**Order of Signals:**

1. `[Controller] mapping_created.emit(ai_id, game_id)` - Controller:515
2. `[Controller] project_changed.emit()` - Controller:516
3. `[Controller] save_requested.emit()` - Controller:517

**UI Update Cascade:**

1. `[Workspace] _on_project_changed()` - Workspace:417
   - Refresh AI frames pane status
   - Refresh captures library link status
   - Refresh mapping panel table
   - Update canvas with alignment
2. Auto-advance (if enabled) - Workspace:1574
   - Find next unmapped frame
   - Emit `ai_frame_selected` signal
   - Trigger Frame Selection Flow (see §2b)

---

### Project Load → Initialization Cascade

**Order of Operations:**

1. `[Controller] load_project(path)` - Controller:200
2. `[Repository] load(path)` - deserialize JSON
3. `[PreviewService] invalidate_all()` - Controller:211
4. `[UndoStack] clear()` - Controller:212
5. `[Controller] project_changed.emit()` - Controller:213

**UI Refresh Cascade:**

1. `[Workspace] _on_project_changed()` - Workspace:417
   - Clear canvas if project identity changed (line 432)
   - Load AI frames into pane (line 447)
   - Load sheet palette (line 451-452)
   - Load game frames into pane (line 453)
   - Set project in mapping panel (line 454)
   - Refresh status indicators (line 456-458)

---

### Alignment Update → Targeted Refresh

**Non-Structural Update:**

When user adjusts alignment, avoid full `project_changed` refresh (which would blank canvas):

1. `[Canvas] alignment_changed.emit(x, y, flip_h, flip_v, scale)` - Canvas:200+
2. `[Workspace] _on_alignment_changed()` - Workspace:640
3. `[Controller] update_mapping_alignment()` - Controller:603
4. `[Controller] alignment_updated.emit(ai_frame_id)` - **Targeted signal** - Controller:659
5. `[Workspace] _on_alignment_updated()` - Workspace:1352
   - Update mapping panel row only (line 1364-1368)
   - Update status column (line 1369)
   - Refresh status indicators (line 1370)

**Why not `project_changed`?**
- Full refresh would clear canvas state
- User is actively editing alignment on canvas
- Only mapping panel row needs update

---

### Injection Success → Save + Refresh Cascade

**Order of Signals:**

1. `[InjectionOrchestrator] InjectionResult(success=True)` - Orchestrator:execute()
2. Update mapping status to "injected" - Controller:1038-1040
3. `[Controller] mapping_injected.emit(ai_id, message)` - Controller:1042
4. `[Controller] project_changed.emit()` (if emit_project_changed=True) - Controller:1046
5. `[Controller] save_requested.emit()` - Controller:1047

**Workspace Handlers:**

1. `[Workspace] _on_mapping_injected()` - Workspace:1306
   - Show status message (line 1309)
   - Refresh mapping status (line 1311)
   - Refresh mapping panel (line 1312)
   - Show success dialog (line 1313)
2. `[Workspace] _auto_save_after_injection()` - Workspace:1315
   - Save project to disk (line 1325)
   - Show "Project auto-saved" message (line 1327)

---

### Stale Entries Warning → User Decision Flow

**Detection:**

1. `[PreviewService] get_capture_result_for_game_frame()` - PreviewService:126
2. Stored entry IDs not found in current capture file (line 173)
3. `[PreviewService] stale_entries_warning.emit(frame_id)` - PreviewService:180

**Signal Cascade:**

1. `[Controller]` (forwards signal) - Controller:97
2. `[Workspace] _on_stale_entries_warning()` - Workspace:1337
   - Track frame_id for potential retry (line 1346)
   - If frame currently selected: show warning on canvas (line 1349-1350)

**During Injection:**

1. `[InjectionOrchestrator]` detects stale entries
2. `[Controller] stale_entries_warning.emit(frame_id)` - Controller:1033
3. Injection aborts by default (allow_fallback=False)
4. `[Workspace]` offers retry dialog with fallback option (line 1123-1139)
5. User accepts → retry with `allow_fallback=True`

---

### Frame Organization → Refresh Single Item

**Frame Rename:**

1. `[AIFramesPane] frame_rename_requested.emit(frame_id, name)` - AIFramesPane:98
2. `[Controller] rename_frame()` → `[OrganizationService]` - Controller:1058
3. `[UndoStack] push(RenameAIFrameCommand)` - OrganizationService:80
4. `[OrganizationService] frame_renamed.emit(frame_id)` - OrganizationService:83
5. `[Controller]` (forwards signal) - Controller:103
6. `[Workspace] _on_frame_organization_changed()` - Workspace:1806
7. `[AIFramesPane] refresh_frame(frame_id)` - Workspace:1812
   - **Only updates single list item** (no full refresh)

**Tag Toggle:**

Similar flow via `frame_tag_toggled` → `frame_tags_changed` signals.

---

### Sheet Palette Change → Multi-Component Sync

**Order of Updates:**

1. `[PaletteService] set_sheet_palette()` - PaletteService:58
2. Update `project.sheet_palette` (line 73)
3. `[PaletteService] sheet_palette_changed.emit()` - PaletteService:74
4. `[Controller]` (forwards signal) - Controller:100
5. `[Workspace] _on_sheet_palette_changed()` - Workspace:1447
   - Get palette from controller (line 1449)
   - `[AIFramesPane] set_sheet_palette()` - Workspace:1450
   - `[Canvas] set_sheet_palette()` - Workspace:1452

**Bidirectional Highlighting:**

- Canvas pixel hover → `pixel_hovered.emit()` → AI Pane highlights swatch
- AI Pane swatch hover → `palette_swatch_hovered.emit()` → Canvas highlights pixels
- Canvas eyedropper pick → `eyedropper_picked.emit()` → AI Pane selects swatch

---

### Batch Capture Import → Sequential Dialog Processing

**Queue Processing:**

1. `[Controller] import_capture_directory()` - Controller:424
2. For each JSON file: `import_mesen_capture()` → `capture_import_requested.emit()`
3. `[Workspace] _on_capture_import_requested()` - Workspace:1703
4. `[DialogCoordinator] queue_capture_import()` - DialogCoordinator:160
5. If queue size == 1: `process_capture_import_queue()` - DialogCoordinator:172

**Recursive Processing:**

1. Pop next capture from queue
2. Show SpriteSelectionDialog (blocks until user accepts/cancels)
3. If accepted: `[Controller] complete_capture_import()` → increment count
4. Recursive call to process next capture (line 205)
5. When queue empty: `queue_processing_finished.emit(count)` - DialogCoordinator:184
6. `[Workspace] _on_capture_queue_finished()` - Workspace:1723

**Why Sequential?**

- Each capture needs user input via dialog
- Modal dialogs must be shown one at a time
- User can cancel mid-process

---

## Summary

The Frame Mapping subsystem uses a hub-and-spoke signal architecture:

- **Controller** acts as the central hub, forwarding service signals to the workspace
- **Workspace** coordinates UI updates by connecting controller signals to pane/canvas methods
- **Services** (Preview, Palette, Organization) emit signals forwarded by the controller
- **Panes** (AI Frames, Captures, Mapping) emit user action signals to the workspace
- **Canvas** emits interactive manipulation signals (alignment, compression, hover)

**Key Design Patterns:**

1. **Signal Forwarding:** Controller forwards service signals to avoid direct service→workspace coupling
2. **ID-Based Signals:** Use frame IDs instead of indices for stability across reorders
3. **Targeted Updates:** `alignment_updated` avoids full refresh for non-structural changes
4. **Deferred Batch Updates:** Batch injection uses `emit_project_changed=False` to avoid N signals
5. **Queue Processing:** Capture imports use sequential modal dialogs via DialogCoordinator
6. **Bidirectional Highlighting:** Canvas↔AI Pane palette swatch hover synchronization

**Signal Count:** 40+ signals across 10 components (Controller, Services, Workspace, Panes, Canvas).

---

## Related Documentation

- **Workspace Connection Logic:** `ui/workspaces/frame_mapping_workspace.py:269-334` (_connect_signals)
- **Controller Signals:** `ui/frame_mapping/controllers/frame_mapping_controller.py:55-89`
- **Service Signals:** See individual service files in `ui/frame_mapping/services/`
- **Undo/Redo Commands:** `ui/frame_mapping/undo.py`
