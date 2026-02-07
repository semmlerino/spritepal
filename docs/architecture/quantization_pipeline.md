# Quantization Pipeline

How an AI frame PNG becomes indexed 4bpp tiles for SNES ROM injection.

## Pipeline Overview

```
AI Frame PNG
    │
    ▼
┌─────────────────────────────┐
│ 1. Load & Index Preservation│  injection_orchestrator.py:572-575
│    Extract palette indices   │  load_image_preserving_indices()
│    before RGBA conversion    │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 2. Background Removal       │  injection_orchestrator.py:584-591
│    Chroma-key if             │  sheet_palette.background_color set
│    background_color set      │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 3. Pre-Quantization         │  injection_orchestrator.py:596-623
│    If RGBA + sheet_palette:  │  quantize at full resolution
│    produce index map early   │  before any scaling
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 4. Sprite Compositing       │  sprite_compositor.py
│    FLIP → SCALE (NEAREST)   │  composite_frame()
│    → place on canvas         │
│    → mask to tile bounds     │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 5. Tile Extraction          │  injection_orchestrator.py:975-1036
│    8×8 grid per ROM offset  │  _inject_tile_group()
│    Counter-flip OAM entries  │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 6. Quantization Strategy    │  quantization_strategies.py:248-307
│    Select: Passthrough >     │  select_quantization_strategy()
│    PaletteMapping > Standard │
│    > CaptureFallback         │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ 7. 4bpp Encoding            │  png_conversion.py
│    Indexed PNG → 32 bytes    │  convert_png_to_4bpp()
│    per 8×8 tile              │
└─────────────┬───────────────┘
              │
              ▼
         ROM Injection
```

## Step Details

### 1. Load & Index Preservation

**File:** `core/services/injection_orchestrator.py:572-575`

```python
ai_index_map, ai_img = load_image_preserving_indices(ai_frame.path)
```

For indexed PNGs (e.g., output from the palette index editor), palette indices are extracted *before* converting to RGBA. This prevents re-quantization from altering hand-tuned index assignments (BUG-1 FIX).

- Indexed PNG → `ai_index_map` (uint8 ndarray, values 0-15) + RGBA image
- RGBA PNG → `ai_index_map = None` + RGBA image

### 2. Background Removal

**File:** `core/services/injection_orchestrator.py:584-591`

Optional chroma-key removal. If `sheet_palette.background_color` is set, pixels within `background_tolerance` (Euclidean RGB distance) are made transparent.

### 3. Pre-Quantization

**File:** `core/services/injection_orchestrator.py:596-623`

If the source is RGBA (no pre-existing indices) and a `sheet_palette` is defined, quantize at full resolution *before* scaling. This produces a clean index map that survives NEAREST-neighbor downscaling without introducing new colors.

### 4. Sprite Compositing

**File:** `core/services/sprite_compositor.py`

Two paths through `composite_frame()`:

| Path | Condition | Behavior |
|------|-----------|----------|
| **Index-first** | `ai_index_map` + `sheet_palette` | Transform index map with NEAREST, reconstruct RGBA from palette |
| **Legacy** | No index map | Transform RGBA, composite onto canvas |

**Transform order** (matches SNES hardware):
1. **Flip** (H/V) — OAM display-time behavior
2. **Scale** — NEAREST interpolation to preserve indices
3. **Offset** — place on canvas at `(offset_x, offset_y)`

Tile masking clips the result to the bounding box of OAM entries.

### 5. Tile Extraction

**File:** `core/services/injection_orchestrator.py:975-1036`

Tiles sharing a ROM offset are assembled into a grid image. Each 8×8 tile is extracted from the composited canvas, counter-flipped to undo OAM entry flips, and placed in the grid. The corresponding region of the index map is extracted in parallel.

### 6. Quantization Strategy Selection

**File:** `core/services/quantization_strategies.py`

```python
select_quantization_strategy(chunk_index_map, sheet_palette, capture_palette_rgb, ...)
```

Priority order (first match wins):

| Strategy | Condition | Behavior |
|----------|-----------|----------|
| `IndexPassthroughStrategy` | Index map exists, all values 0-15, no gaps (255) | Direct index lookup — no re-quantization |
| `PaletteMappingStrategy` | Sheet palette exists, index map has gaps | Hybrid: use indices where valid, color-match for gaps |
| `StandardQuantizationStrategy` | Sheet palette exists | Full perceptual quantization with color mappings |
| `CapturePaletteFallbackStrategy` | No sheet palette | Perceptual match to Mesen capture palette |

### 6a. Perceptual Quantization Algorithm

**File:** `core/palette_utils.py`

Core function: `quantize_with_mappings(img, palette_rgb, color_mappings, ...)`

1. Convert RGBA → **LAB** color space (perceptual uniformity)
2. Apply **Bayer dithering** (optional, 4×4 ordered matrix on L channel)
3. Compute squared distances to 16 palette colors in LAB
4. **Mask index 0** for opaque pixels (index 0 = SNES transparency)
5. Find nearest with **stable tie-breaking** (JND threshold 5.29 LAB²)
6. Apply explicit **color mappings** (override nearest for mapped colors)
7. Set transparent pixels to index 0

**Key constants:**
- `JND_THRESHOLD_SQ = 5.29` — within "just noticeable difference", pick lowest index
- `SNES_PALETTE_SIZE = 16` — 4-bit indexed (0-15)
- `QUANTIZATION_TRANSPARENCY_THRESHOLD = 128` — alpha cutoff

### 7. 4bpp Encoding

**File:** `core/services/png_conversion.py`

```python
convert_png_to_4bpp(indexed_image) -> (bytes, tile_count)
```

Pads to tile alignment, reshapes to 8×8 tiles, encodes each as 32 bytes (4 bits × 64 pixels). Uses `core/tile_utils.py:encode_4bpp_tile()`.

## SheetPalette Configuration

**File:** `core/frame_mapping_project.py`

| Attribute | Type | Purpose |
|-----------|------|---------|
| `colors` | `list[tuple[int,int,int]]` | 16 RGB colors; `[0]` = transparent |
| `color_mappings` | `dict[RGB, int]` | Explicit RGB → palette index overrides |
| `background_color` | `RGB \| None` | Chroma-key color for removal |
| `background_tolerance` | `int` | Euclidean RGB distance for removal (default 30) |
| `alpha_threshold` | `int` | Alpha cutoff 0-255 (default 128) |
| `dither_mode` | `str` | `"none"` or `"bayer"` |
| `dither_strength` | `float` | 0.0-1.0 dither intensity |

## Key Design Decisions

**Index preservation over re-quantization:** The palette index editor lets users hand-assign indices. The pipeline preserves these through compositing by transforming the index map with NEAREST interpolation, avoiding any color-space round-trip.

**Pre-quantization before scaling:** Quantizing at full resolution before downscaling ensures clean index boundaries. Scaling indexed data with NEAREST preserves sharp edges.

**WYSIWYG fidelity:** Preview and injection share the same quantization functions (`palette_utils.py`). The preview path uses identical SheetPalette settings.

**Stable tie-breaking:** When multiple palette colors are perceptually identical (within JND), the lowest index wins. This prevents symmetric pixels from mapping to different indices, avoiding visual noise.
