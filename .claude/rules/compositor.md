---
paths:
  - "core/services/sprite_compositor.py"
  - "core/palette_utils.py"
  - "ui/**/preview*"
  - "ui/**/workbench*"
---

# Compositor — Rendering Pipeline

## Mental Model

Two rendering paths exist:

- **INDEX-FIRST** (preferred): Transform index map → render from indices. No Lanczos artifacts. Used when both index map AND sheet_palette are available.
- **LEGACY** (fallback): Transform RGBA → quantize to palette. Used when index map or sheet_palette is missing.

Path selection happens once per render call. The compositor never mixes paths.

## Data Flow

```
INPUT (AI frame + GameFrame capture)
  │
  ├─ Has index_map + sheet_palette? ──→ INDEX-FIRST PATH
  │     Transform index map (NEAREST) → Render pixels from palette indices
  │
  └─ Missing either? ──→ LEGACY PATH
        Transform RGBA (Lanczos) → Quantize to palette → Index assignment
  │
  ▼
UNCOVERED PIXEL POLICY ("transparent" or "original")
  │
  ▼
OUTPUT (CompositeResult: final_image, tile_data)
```

## Transform Order

**Flip → Scale → Offset** — matches SNES hardware sprite transform order. Non-negotiable.

Sharpen is applied before scale (operates on source resolution).

## Key Types

- `TransformParams` — flip_h, flip_v, scale, offset_x, offset_y, sharpen, resampling
- `CompositeResult` — final composited image + per-tile data
- `SheetPalette` — user-defined palette for AI frame quantization (see palette rule)

## Invariants

- **WYSIWYG**: Preview output = injection output (same compositor, same params)
- Tile masking applies on "transparent" uncovered policy
- Index 0 = transparent (SNES convention)
- NEAREST interpolation on index maps (never Lanczos — destroys indices)
- Preview cache keyed by `(capture_id, frozenset(entry_ids))`

## Non-Goals

- No pixel-perfect alpha blending (SNES has binary alpha only)
- No custom transform orders
- No sub-tile masking granularity

## Key Files

- `core/services/sprite_compositor.py` — main compositor logic
- `core/palette_utils.py` — palette conversion, SNES color snapping
- `core/mesen_integration/capture_renderer.py` — game frame rendering
