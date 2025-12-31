# 02 Data Contracts

This document defines the **canonical schema** for capture and mapping data.

## sprite_capture*.json

### Top-Level
- `frame` (int): capture frame counter used by the script
- `timestamp` (int, optional): Unix timestamp
- `visible_count` (int): count of entries **included in `entries[]`** after the visibility
  filter (default 224-line overscan exclusion; see `SKIP_VISIBILITY_FILTER` and `VISIBLE_*`)
- `obsel` (object, required)
- `entries` (array, required)
- `palettes` (object, required)

### obsel
- `raw` (int): raw $2101 value
- `name_base` (int)
- `name_select` (int)
- `size_select` (int)
- `tile_base_addr` (int, **byte address** for VRAM reads)
- `oam_base_addr` (int, **word address** used in PPU math)
- `oam_addr_offset` (int, **word address** used in PPU math)
- Invariants (byte/word conversion):
  - `tile_base_addr == oam_base_addr * 2`
  - `oam_offset_bytes == oam_addr_offset * 2` (derive when needed)

### entries[]
- `id` (int)
- `x` (int), `y` (int): pixel coordinates from OAM (x is signed 9-bit, adjusted to
  -256..255; y is raw 0..255)
- `tile` (int): OAM tile index (0-255)
- `width` (int), `height` (int): sprite size in **pixels**
- `palette` (int)
- `priority` (int)
- `flip_h` (bool), `flip_v` (bool)
- `tile_page` (int, required for mapping): OAM attr bit 0 (tile index bit 8 / second table)
- If `tile_page`/`name_table` is missing, assume 0 and treat the capture as **unsafe for mapping**.
- `name_table` (int, legacy): same as `tile_page` for backward compatibility (**not** BG nametables)
- `tiles` (array, required)

### tiles[]
- `tile_index` (int): **per-subtile** index (0-255) after row/column wrap
- `vram_addr` (int, **byte address**)
- `pos_x` (int), `pos_y` (int): **subtile coordinates** in 8×8 tile units, origin at the
  sprite’s top-left before flips (not pixels; not screen-space)
- `data_hex` (string): **exactly 64 hex chars** (32 bytes), uppercase, no separators

Tiles ordering guarantee:
- `tiles[]` is ordered by `pos_y` then `pos_x` (row-major, pre-flip).

### palettes
- Keys: strings "0".."7"
- Values: arrays of 16 ints, **15-bit BGR** words, little-endian `lo | (hi << 8)`

## Validation / Fail-Fast Rules
- `data_hex` length must be 64 hex chars (32 bytes) for 4bpp.
- If **all odd bytes are zero** across **many tiles**, abort the capture. This is a strong
  indicator of a bad VRAM read path but not a mathematical impossibility for a single tile.
- If tiles are not 32 bytes, do not hash them.
- When using ROM-trace seeds, validate candidate offsets via HAL decompression before
  indexing; bucket bases are **ranking signals only**.

## Naming Conventions

### Quick Reference: Address Units
| Field Name | Unit | Notes |
|------------|------|-------|
| `oam_base_addr` | **word** | PPU internal; multiply by 2 for bytes |
| `oam_addr_offset` | **word** | PPU internal; multiply by 2 for bytes |
| `tile_base_addr` | **byte** | Ready for VRAM reads |
| `vram_addr` | **byte** | Ready for VRAM reads |
| `tiles[].vram_addr` | **byte** | Per-subtile VRAM address |

### Rules
- Prefer `tile_page` over `name_table`. Treat `name_table` as legacy input only.
- `tile_page`/`name_table` refer to the **OBJ tile high bit**, not BG nametables.
- **Deprecation (`name_table` → `tile_page`)**: The field `name_table` was poorly named
  (suggests BG nametables). Writers should emit both fields with identical values for
  backward compatibility. Readers should prefer `tile_page` when both are present.
  Remove `name_table` support once all captures in `mesen2_exchange/` use `tile_page`.
- Use `*_addr` units consistently:
  - `*_addr` in **bytes** unless explicitly marked as word address.
  - Word addresses must be labeled explicitly (e.g., `*_word` or in-field doc text).
  - **Legacy exception:** `oam_base_addr`/`oam_addr_offset` are **word** addresses (predates
    this convention). New fields should use `*_word` suffix for word addresses.
  - `tile_base_addr` and `vram_addr` are **byte** addresses (correct naming).

### Conversion Formulas
```python
# Word → Byte
byte_addr = word_addr * 2
tile_base_addr = oam_base_addr * 2  # Example

# Byte → Word (for PPU math)
word_addr = byte_addr // 2
```

## Tile Hash Contract (4bpp)
- Tile size: **32 bytes** (4bpp). Sprites (OBJ) are always 4bpp; other bpp modes apply to BG tiles.
- Hash algorithm: **MD5** over raw 32-byte tile data.
- Flip normalization: optional lookup mode that tests **N/H/V/HV** variants; candidates are
  de-duplicated by `(rom_offset, tile_index)`. Default mapping uses **unflipped** tiles
  because OAM flip bits are applied at render time.
  - **N (Normal)**: No transform, use tile data as-is
  - **H (Horizontal flip)**: Mirror each row of pixels left↔right
  - **V (Vertical flip)**: Reverse row order (top↔bottom)
  - **HV (Both)**: Apply H then V (equivalent to 180° rotation)
- Low-information tiles may be ignored during scoring (**<= 2 unique byte values**).
  - **Rationale**: Tiles with ≤2 unique bytes are typically solid colors, simple gradients,
    or transparent regions. These tiles have high hash collision rates across different
    graphics sets (many sprites share blank/shadow tiles) and contribute noise rather than
    signal to ROM offset scoring. Ignoring them improves match confidence.

## Mapper Output (CaptureMapResult)
These fields are produced by `CaptureToROMMapper.map_capture()` for diagnostics and scoring.
- `matched_tiles`: tiles with any hash hits (including low-info tiles)
- `scored_tiles`: tiles that contributed positive weight to scoring
- `ignored_low_info_tiles`: tiles ignored due to low-information heuristic

## tile_hash_database.json
Database files include metadata to guard against ROM/header mismatches.
- `metadata.rom_title` (string | null)
- `metadata.rom_checksum` (int | null)
- `metadata.rom_size` (int)
- `metadata.rom_header_offset` (int): 0 or 512 (SMC header)
