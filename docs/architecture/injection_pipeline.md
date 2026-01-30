# Injection Pipeline Architecture

The injection pipeline transforms AI-generated sprite frames into SNES-compatible tile data and writes them into ROM at the positions captured from the emulator.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Injection Request Flow                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  User Action                                                                │
│      │                                                                      │
│      ▼                                                                      │
│  FrameMappingController.inject_mapping()                                    │
│      │                                                                      │
│      ▼                                                                      │
│  AsyncInjectionService (optional, for non-blocking)                         │
│      │                                                                      │
│      ▼                                                                      │
│  InjectionOrchestrator.execute()                                            │
│      │                                                                      │
│      ├─→ 1. Validate mapping                                                │
│      ├─→ 2. Prepare images (composite, quantize, mask)                      │
│      ├─→ 3. Create ROM staging copy                                         │
│      ├─→ 4. Inject tile groups                                              │
│      ├─→ 5. Inject palette (if configured)                                  │
│      └─→ 6. Commit or rollback staging                                      │
│                                                                             │
│      ▼                                                                      │
│  InjectionResult                                                            │
│      │                                                                      │
│      ▼                                                                      │
│  UI Update (status, messages, error handling)                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Layer Diagram (13 Layers)

| Layer | Component | File | Responsibility |
|-------|-----------|------|----------------|
| 1 | UI Action | `ui/frame_mapping/views/mapping_panel.py` | User triggers injection |
| 2 | Controller | `ui/frame_mapping/controllers/frame_mapping_controller.py` | Coordinates injection, emits signals |
| 3 | Async Service | `ui/frame_mapping/services/async_injection_service.py` | Non-blocking worker thread |
| 4 | **Orchestrator** | `core/services/injection_orchestrator.py` | Main pipeline coordination |
| 5 | Validation | `injection_orchestrator._validate_mapping()` | Checks mapping integrity |
| 6 | Image Preparation | `injection_orchestrator._prepare_images()` | Composites AI frame onto game canvas |
| 7 | Staging Manager | `core/services/rom_staging_manager.py` | Creates ROM copy for safe writes |
| 8 | Tile Grouping | `injection_orchestrator._group_tiles_by_offset()` | Groups tiles by ROM offset |
| 9 | Tile Injection | `injection_orchestrator._inject_tile_group()` | Converts to 4bpp, compresses, writes |
| 10 | ROM Injector | `core/rom_injector.py` | Low-level ROM write operations |
| 11 | Compressor | `core/hal_compressor.py` | HAL/raw compression |
| 12 | Palette Injector | `core/rom_injector.inject_palette_to_rom()` | Writes palette data |
| 13 | Verification | `core/services/rom_verification_service.py` | Verifies written data |

## Key Components

### InjectionRequest
Immutable dataclass containing all parameters for an injection:
- `ai_frame_id`: ID of the AI frame to inject
- `rom_path`: Source ROM path
- `output_path`: Target ROM path (can be same for in-place)
- `palette_rom_offset`: Optional offset for palette injection
- `allow_fallback`: Whether to proceed with stale capture entries
- `force_raw`: Force raw (uncompressed) injection

### InjectionResult
Result dataclass returned by the orchestrator:
- `success`: Overall success/failure
- `tile_results`: Per-tile injection results
- `output_rom_path`: Path to modified ROM
- `messages`: Human-readable status messages
- `error`: Error message if failed
- `new_mapping_status`: Status to set on mapping ("injected")
- `needs_fallback_confirmation`: True if stale entries detected
- `stale_frame_id`: Frame ID with stale entries

### InjectionDebugContext
Debug mode context for troubleshooting:
- Saves intermediate images to temp directory
- Logs detailed tile information
- Can force raw injection for comparison

## Debug Mode Usage

Enable debug mode by setting environment variable:
```bash
SPRITEPAL_INJECT_DEBUG=1 uv run python launch_spritepal.py
```

This creates a debug directory with:
- `ai_frame.png`: Original AI frame
- `game_frame.png`: Original game frame capture
- `composite.png`: Aligned AI frame on game canvas
- `masked.png`: Final masked image for injection
- `tile_*.png`: Individual tile images
- `injection.log`: Detailed injection log

## Common Failure Modes

### 1. Stale Capture Entries
**Symptom:** `needs_fallback_confirmation=True` in result

**Cause:** The capture JSON references OAM entries that no longer match the current ROM state (e.g., game was patched, wrong game loaded).

**Resolution:**
- Re-capture the frame from the emulator
- Use `allow_fallback=True` to proceed with available entries

### 2. Compression Failure
**Symptom:** `error="HAL compression failed"`

**Cause:** The compressed data exceeds the available slot size in ROM.

**Resolution:**
- Try raw injection (uncompressed)
- Reduce sprite complexity
- Check ROM has enough free space at target offset

### 3. Palette Mismatch
**Symptom:** Sprite looks wrong in-game despite successful injection

**Cause:** Sheet palette doesn't match game palette at runtime.

**Resolution:**
- Verify palette ROM offset is correct
- Ensure palette injection succeeded (check messages)
- Use "Copy Game Palette" to use captured palette

### 4. Tile Alignment Issues
**Symptom:** Sprite appears shifted or clipped

**Cause:** Alignment offset doesn't account for sprite bounding box differences.

**Resolution:**
- Use auto-align on initial mapping
- Adjust offset manually in workbench
- Enable grid overlay to verify tile boundaries

## Error Handling Patterns

### Controller Level
```python
result = controller.inject_mapping(...)
if result.needs_fallback_confirmation:
    # Show confirmation dialog
    if user_confirms:
        result = controller.inject_mapping(..., allow_fallback=True)
elif not result.success:
    # Show error message
    show_error(result.error)
else:
    # Update UI, show success
    show_messages(result.messages)
```

### Async Injection
```python
# Signals for async feedback
async_injection_started = Signal(str)  # ai_frame_id
async_injection_progress = Signal(str)  # progress message
async_injection_finished = Signal(str, object)  # ai_frame_id, InjectionResult
```

## Defensive Patterns (Stale Entry Protection)

The pipeline includes 7 defensive patterns against stale/invalid data:

1. **`_validate_mapping()`**: 6 existence checks for AI frame, game frame, mapping
2. **`StaleEntryDetector`**: Async detection of stale capture entries on project load
3. **Cascading fallback in `filter_capture_entries()`**: Uses available entries if some are stale
4. **ROM verification with spatial consistency**: Verifies written tiles read back correctly
5. **Orphan pruning on frame reload**: Removes mappings for deleted AI frames
6. **`InjectionResult.needs_fallback_confirmation`** flow: Explicit user consent for stale data
7. **Staging/rollback pattern**: Atomic commits prevent partial injection

## File Locations

| Purpose | File |
|---------|------|
| Main orchestrator | `core/services/injection_orchestrator.py` |
| Request/Result types | `core/services/injection_results.py` |
| Debug context | `core/services/injection_debug_context.py` |
| ROM staging | `core/services/rom_staging_manager.py` |
| ROM writing | `core/rom_injector.py` |
| Compression | `core/hal_compressor.py` |
| Controller | `ui/frame_mapping/controllers/frame_mapping_controller.py` |
| Async service | `ui/frame_mapping/services/async_injection_service.py` |
| Verification | `core/services/rom_verification_service.py` |
