# 02 Data Contracts

This document defines the **canonical schema** for capture and mapping data.

## Global Conventions

### Address Unit Suffix Rule
- `*_addr` or no suffix = **byte address** (ready for API calls)
- `*_word` = **word address** (multiply by 2 for bytes)

**Legacy exceptions** (predating this convention):
- `oam_base_addr`, `oam_addr_offset` are **word addresses** despite `_addr` suffix
- These are documented in the Quick Reference table; new fields must use `_word` suffix

### Byte Array Encoding
All byte arrays in JSON use **list[int]** (0-255 values), never base64.
- `data_hex`: hex string (64 chars = 32 bytes)
- `palettes[n]`: list of 16 ints (15-bit BGR words)
- Future byte arrays: list[int] unless explicitly noted

---

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
  - **Y coordinate nuances**: Y=0 places sprite at top of visible area. Some games use
    224-line mode (overscan default), others use 239/240-line modes. The visibility
    filter assumes 224 lines by default; adjust `VISIBLE_Y_EXCLUDE_*` for extended modes.
- `tile` (int): OAM tile index (0-255)
- `width` (int), `height` (int): sprite size in **pixels**
- `palette` (int): 0-7, selects CGRAM palette (sprite palettes are 128-255)
- `priority` (int): 0-3, higher values render in front of lower priority sprites
  (within sprite priority; BG layer priority interactions are separate)
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
- **Off-screen subtiles**: `tiles[]` includes ALL subtiles of a multi-tile sprite,
  even if some are partially or fully off-screen. The visibility filter operates on
  the sprite's anchor position (x, y), not individual subtiles. This ensures complete
  tile data for hash matching.

### palettes
- Keys: strings "0".."7"
- Values: arrays of 16 ints, **15-bit BGR** words, little-endian `lo | (hi << 8)`
- **Palette endianness**: Values are stored as native ints after conversion from
  SNES CGRAM format. The capture script reads CGRAM and converts to `lo | (hi << 8)`.
  This matches SNES hardware byte order. The emulator's `emu.readWord()` endianness
  quirk (see `01_BUILD_SPECIFIC_CONTRACT.md`) does NOT apply to these values—they
  are already normalized during capture.

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

### Value Ranges

| Field | Type | Range | Notes |
|-------|------|-------|-------|
| `entries[].x` | int | -256..255 | Signed 9-bit |
| `entries[].y` | int | 0..255 | Unsigned 8-bit |
| `entries[].tile` | int | 0..255 | OAM tile index |
| `entries[].palette` | int | 0..7 | CGRAM palette (128-255) |
| `entries[].priority` | int | 0..3 | Higher = in front |
| `entries[].tile_page` | int | 0..1 | Second table select |
| `obsel.name_base` | int | 0..7 | OBJSEL bits 0-2 |
| `obsel.name_select` | int | 0..3 | OBJSEL bits 3-4 |
| `obsel.size_select` | int | 0..7 | OBJSEL bits 5-7 |

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

## Tile Hash Contract (4bpp, OBJ-Only)

**Scope:** This pipeline handles **OBJ sprites only**. BG tiles support 2/4/8bpp
but are outside the current scope.

- Tile size: **32 bytes** (4bpp). SNES OBJ sprites are always 4bpp.
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

## Scoring Algorithm (CaptureToROMMapper)

### Tile Classification
1. **High-information tile**: >2 unique byte values in 32-byte tile data
2. **Low-information tile**: ≤2 unique byte values (ignored in scoring)

### Per-Tile Weight
```python
def tile_weight(tile_data: bytes, hit_count: int) -> float:
    unique_bytes = len(set(tile_data))
    if unique_bytes <= 2:
        return 0.0  # Low-info: ignore
    if hit_count == 0:
        return 0.0  # No match
    # Inverse of collision count: fewer hits = more distinctive
    return 1.0 / hit_count
```

### Offset Scoring
```python
def score_offset(offset: int, tile_weights: dict[str, float]) -> float:
    return sum(
        tile_weights[hash]
        for hash in tiles_at_offset[offset]
        if hash in tile_weights
    )
```

### Result Fields
- `matched_tiles`: tiles with ≥1 DB hits (includes low-info)
- `scored_tiles`: tiles with positive weight contribution
- `ignored_low_info_tiles`: tiles skipped due to ≤2 unique bytes
- `top_offset`: highest-scoring ROM offset
- `confidence`: ratio of scored_tiles to total high-info tiles

**Caveats:**
- Scores are **relative rankings**, not absolute confidence measures
- High scores with few tiles may be coincidental collisions
- Low scores with many low-info tiles may still indicate correct offset
- Always validate top candidates via decompression before indexing

## tile_hash_database.json
Database files include metadata to guard against ROM/header mismatches.
- `metadata.rom_title` (string | null)
- `metadata.rom_checksum` (int | null)
- `metadata.rom_size` (int)
- `metadata.rom_header_offset` (int): 0 or 512 (SMC header)

## vram_tile_database.json (Strategy A)
For SA-1 games with character conversion active, direct ROM→VRAM hash matching fails.
This database maps VRAM tile hashes to ROM regions via timing correlation instead.

### Top-Level
- `type` (string): `"vram_based"` — identifies this as a Strategy A database
- `description` (string): Human-readable description
- `tiles` (object): Hash → region mapping

### tiles
Keys are MD5 hashes of 32-byte VRAM tiles (same format as `tile_hash_database.json`).

Each value is an object:
- `rom_region` (int): ROM file offset of the region accessed when this tile appeared in VRAM
  (derived from ROM trace timing correlation, not byte-level matching)
- `confidence` (int): Number of captures where this tile correlated with this region
- `alternatives` (int): Number of other regions this tile was seen with (lower = more reliable)

### Usage
```python
import json
with open("mesen2_exchange/vram_tile_database.json") as f:
    db = json.load(f)

# Look up a VRAM tile hash
tile_hash = "3240cdda6d2c4133059aeb2b0c38c2f2"
if tile_hash in db["tiles"]:
    entry = db["tiles"][tile_hash]
    print(f"ROM region: 0x{entry['rom_region']:06X}")
    print(f"Confidence: {entry['confidence']}, Alternatives: {entry['alternatives']}")
```

### Limitations
- `rom_region` is a **correlation**, not a proven source offset
- High `alternatives` values indicate ambiguous mappings
- Works only for tiles captured during the probe runs that built this database
- Does not replace ROM-based database for games without SA-1 conversion

## rom_trace_log.txt

ROM trace logs are line-oriented text files. See `01_BUILD_SPECIFIC_CONTRACT.md`
§ "rom_trace_log.txt Format" for field definitions.

**Key invariants:**
- `addr` values are `snesPrgRom` memType addresses (may need mapping conversion)
- If `prg_size` is present in header, `addr < prg_size` implies linear file offset
- If `prg_size` is absent, treat all addresses as ambiguous
