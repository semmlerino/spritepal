---
paths:
  - "ui/frame_mapping/**"
  - "core/frame_mapping_project.py"
  - "core/repositories/frame_mapping_repository.py"
---

# Frame Mapping — Controller/Facade/Service Architecture

## Mental Model

**Layered architecture**: Controller → Facades → Services → Data Model

**Signal flow**: Controller broadcasts → Workspace relays → Panels consume

The controller is the single entry point for all mutations. Facades group related operations (ai_frames, game_frames, injection, palette). Services handle async work and caching.

## Data Flow

```
User action (UI event)
  → FrameMappingWorkspace handler
  → FrameMappingController method
  → Facade delegates to service(s)
  → Service mutates FrameMappingProject
  → Undo command pushed to undo stack
  → Controller emits targeted signal
  → Workspace routes signal to affected panels
  → Auto-save triggered
```

## Key Types

- **AIFrame**: `path`, `index`, `tags` — AI-generated sprite. ID = filename (stable across sessions)
- **GameFrame**: `id`, `rom_offsets`, `capture_path`, `selected_entry_ids`, `compression_types` — Mesen capture
- **FrameMapping**: `ai_frame_id`, `game_frame_id`, alignment params, `status`, `ingame_edited_path` — links AI↔Game
- **MappingStatus**: unmapped → mapped → edited → injected (state machine)

## Signal Catalog (Controller)

| Signal | Purpose |
|--------|---------|
| `project_changed` | Full reload (use sparingly) |
| `ai_frames_loaded` | After directory load |
| `game_frame_added` / `removed` | Capture import/delete |
| `mapping_created` / `removed` | Link created/deleted |
| `mapping_injected` | Successful ROM injection |
| `alignment_updated` | Targeted — no full refresh |
| `sheet_palette_changed` | Palette modified |
| `error_occurred` | Error display |
| `status_update` | Status bar feedback |
| `save_requested` | Trigger auto-save |
| `stale_entries_warning` | Stale ROM data detected |

## Invariants

- **1:1 mapping**: Creating a new mapping removes any prior mapping for both the AI frame and game frame
- AI frame ID = filename (stable identifier, not UUID)
- Auto-save on all significant mutations
- Undo/redo wraps all project mutations (single undo step per user action)
- Cache invalidation on `version_hash` change (palette-dependent previews)

## InjectionCoordinator

```
Validate ROM path
  → Prepare target (original_modified.smc suffix)
  → Build batch queue (preserve_existing=True skips already-injected)
  → Async worker processes queue
  → Update MappingStatus → injected
  → Emit mapping_injected per frame
  → Trigger save
```

## Non-Goals

- No multi-mapping (one AI frame → one game frame, strictly)
- No nested undo (flat undo stack, one level)
- No live preview during drag operations (debounced)

## Key Files

- `ui/frame_mapping/controllers/` — FrameMappingController (entry point)
- `ui/frame_mapping/facades/` — ai_frames, game_frames, injection, palette facades
- `ui/frame_mapping/services/` — async services, caching, preview rendering
- `ui/frame_mapping/injection_coordinator.py` — batch injection orchestration
- `core/frame_mapping_project.py` — data model, serialization
- `core/repositories/frame_mapping_repository.py` — persistence layer
- `ui/frame_mapping/undo/` — undo command classes
