---
paths:
  - "core/palette_manager.py"
  - "core/palette_utils.py"
  - "core/frame_mapping_project.py"
  - "ui/**/palette*"
  - "ui/**/sheet_palette*"
---

# Palette — Two Separate Systems

## Mental Model

Two palette systems exist — they are **not interchangeable**:

- **PaletteManager**: Extracts palettes from CGRAM dumps. Used to display game sprites with correct colors.
- **SheetPalette**: User-defined palette for quantizing AI-generated frames. Stored in the frame mapping project.

## CGRAM Extraction Flow (PaletteManager)

```
CGRAM dump (512 bytes, from Mesen capture)
  → Parse BGR555 format → Convert to RGB
  → Palettes 8-15 = sprite palettes (SNES convention)
  → Store as dict[int, list[tuple[int,int,int]]]
```

## AI Quantization Flow (SheetPalette)

```
AI RGBA image
  → Background removal (alpha_threshold + background_color/tolerance)
  → SNES color snapping (snap_to_snes_color: round to 5-bit per channel)
  → Color mapping overrides (user-defined source→target remaps)
  → Dithering (optional: Floyd-Steinberg, ordered, etc.)
  → Index assignment (nearest RGB match in palette)
```

## Key Types

- **PaletteManager**: `cgram_data: bytes`, `palettes: dict[int, list[tuple[int,int,int]]]`
- **SheetPalette**: `colors`, `color_mappings`, `background_color`, `background_tolerance`, `alpha_threshold`, `dither_mode`, `dither_strength`, `version_hash`

## Invariants

- Index 0 = transparent (SNES convention, both systems)
- Exactly 16 colors per palette (4bpp SNES tiles)
- `sheet_palette` takes priority over capture palette when both available
- SNES color precision enforced via `snap_to_snes_color()` (5 bits per channel)
- `version_hash` is constrained to 32-bit signed int range
- Cache invalidation triggered by version_hash change

## Known Limitation

Duplicate palette colors → map to same index (first match wins during quantization). Workaround: ensure all palette colors are unique.

## Non-Goals

- No multi-palette sprites (single 16-color palette per sprite)
- No palette interpolation or blending
- No dynamic/automatic palette generation

## Key Files

- `core/palette_manager.py` — CGRAM extraction, game palette management
- `core/frame_mapping_project.py` — SheetPalette data model, serialization
- `core/palette_utils.py` — SNES color snapping, RGB↔BGR555 conversion
