# 02 Data Contracts

This document defines the **canonical schema** for capture and mapping data.

## Schema Versioning

All JSON data files should include a `schema_version` field at the top level:

```json
{
  "schema_version": "1.0",
  "frame": 1800,
  ...
}
```

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Dec 2024 | Initial documented schema |
| 2.0 | Dec 2024 | Renamed fields: oam_base_addr→obj_tile_base_word, oam_addr_offset→obj_tile_offset_word, confidence→observation_count |

**Version format:** `MAJOR.MINOR`
- **MAJOR** bump: Breaking changes (removed fields, changed semantics)
- **MINOR** bump: Additive changes (new optional fields)

**Backward compatibility:**
- Readers should accept files without `schema_version` (assume 1.0)
- Readers should ignore unknown fields (forward compatibility)
- Writers should always include `schema_version`

---

## Global Conventions

### Terminology: `tile_page` (not `name_table`)

The field `tile_page` refers to OAM attribute bit 0 (tile index bit 8 / second OBJ table select).

**Canonical name:** `tile_page`
**Legacy alias:** `name_table` (deprecated, accepted for backward compatibility)

The legacy name `name_table` was misleading because it suggests BG nametables, which are
unrelated. The OAM bit selects between two 256-tile OBJ regions, not background tile maps.

Writers should emit `tile_page`. Readers should accept both, preferring `tile_page` when present.

### Address Unit Suffix Rule
- `*_addr` or no suffix = **byte address** (ready for API calls)
- `*_word` = **word address** (multiply by 2 for bytes)

**Legacy exceptions** (predating this convention):
- `oam_base_addr`, `oam_addr_offset` are **word addresses** despite `_addr` suffix
- These are documented in the Quick Reference table; new fields must use `_word` suffix

### Byte Array Encoding
Binary data in JSON uses one of two formats:
- **Hex string**: `data_hex` fields use uppercase hex (e.g., `"3F00A1..."`, 64 chars = 32 bytes)
- **list[int]**: `palettes[n]` and other multi-word arrays use lists of ints (0-255 or 0-65535)

**Convention:** Tile data uses hex strings (`data_hex`) for compactness. Palettes and future
arrays use list[int] unless explicitly noted. Never use base64.

---

## sprite_capture*.json

### Top-Level
- `schema_version` (string, recommended): Schema version (e.g., "1.0"). See Schema Versioning above.
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
- `priority` (int): 0-3, OBJ priority level for **OBJ vs BG layer** interaction only.
  **Does NOT determine sprite-sprite ordering**; OAM index resolves overlaps (lower index = in front).
  See `00_STABLE_SNES_FACTS.md` § "Sprite Overlap Ordering" for details.
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

### Tile Hash Byte Order

Tiles are stored as 32 bytes in sequential VRAM order (after byte-swap correction).
The hash database uses MD5 or SHA256 of this 32-byte sequence.

**Reconstruction from `emu.readWord()`:**

Due to Mesen2's `readWord()` returning bytes in big-endian order for VRAM, the capture
script swaps bytes to produce correct sequential order:

| Word Read | `readWord()` Returns | After Swap | DB Position |
|-----------|---------------------|------------|-------------|
| addr+0    | 0xCDAB              | AB, CD     | [0], [1]    |
| addr+2    | 0x1234              | 34, 12     | [2], [3]    |
| addr+4    | 0x5678              | 78, 56     | [4], [5]    |
| ...       | ...                 | ...        | ...         |
| addr+30   | 0xFFEE              | EE, FF     | [30], [31]  |

**Lua extraction pattern:**
```lua
local word = emu.readWord(addr, emu.memType.snesVideoRam)
local byte0 = (word >> 8) & 0xFF   -- First byte (high byte of word)
local byte1 = word & 0xFF          -- Second byte (low byte of word)
```

**Verification:** Run `verify_endianness.lua` to confirm this behavior matches your
Mesen2 build. See `01_BUILD_SPECIFIC_CONTRACT.md` § "VRAM Read Semantics" for details.

### palettes
- Keys: strings "0".."7"
- Values: arrays of 16 ints, **15-bit BGR** words, little-endian `lo | (hi << 8)`
- **Palette endianness**: Values are stored as native ints after conversion from
  SNES CGRAM format. The capture script reads CGRAM and converts to `lo | (hi << 8)`.
  This matches SNES hardware byte order. The emulator's `emu.readWord()` endianness
  quirk (see `01_BUILD_SPECIFIC_CONTRACT.md`) does NOT apply to these values—they
  are already normalized during capture.

> **Verification:** Run `verify_endianness.lua` with CGRAM test mode to confirm:
> - CGRAM byte pairs are read as expected for your Mesen2 build
> - The script tests `emu.readWord()` on `emu.memType.snesCgRam` and reports byte order
> - If CGRAM behaves differently from VRAM, update capture scripts accordingly

### Visibility Filter Predicate

The visibility filter determines which sprites from OAM are included in `entries[]`.
This is the **exact boolean check** used:

```lua
-- Default values (configurable via env vars)
local VISIBLE_X_MIN = -64       -- VISIBLE_X_MIN
local VISIBLE_X_MAX = 256       -- VISIBLE_X_MAX
local VISIBLE_Y_EXCLUDE_START = 224  -- VISIBLE_Y_EXCLUDE_START
local VISIBLE_Y_EXCLUDE_END = 240    -- VISIBLE_Y_EXCLUDE_END (exclusive)

function is_sprite_visible(x, y)
    -- X is signed 9-bit (-256 to +255), already converted from OAM
    -- Y is unsigned 8-bit (0 to 255)

    -- X must be within horizontal bounds (exclusive comparison)
    if x <= VISIBLE_X_MIN or x >= VISIBLE_X_MAX then
        return false
    end

    -- Y must NOT be in the overscan exclusion zone [START, END)
    if y >= VISIBLE_Y_EXCLUDE_START and y < VISIBLE_Y_EXCLUDE_END then
        return false
    end

    return true
end
```

**Environment variables:**
- `SKIP_VISIBILITY_FILTER=1`: Include all 128 OAM entries (no filtering)
- `VISIBLE_X_MIN`, `VISIBLE_X_MAX`: Horizontal visibility bounds (default -64..256, exclusive)
- `VISIBLE_Y_EXCLUDE_START`, `VISIBLE_Y_EXCLUDE_END`: Overscan exclusion zone (default 224..240, half-open [start, end))

**Notes:**
- Filter operates on **sprite anchor** (x, y), not individual subtile positions
- Sprite dimensions are NOT considered—partially visible sprites are included
- Y=0 is top of visible area; overscan exclusion handles hidden sprites at screen bottom
- For 239-line or 240-line modes, adjust `VISIBLE_Y_EXCLUDE_*` accordingly

## Validation / Fail-Fast Rules

**Implementation:** `core/mesen_integration/click_extractor.py:MesenCaptureParser._parse_capture_data()`
raises `CaptureValidationError` for violations of the rules below.

**Tests:** `tests/unit/mesen_integration/test_capture_parser_validation.py`

- `data_hex` length must be 64 hex chars (32 bytes) for 4bpp.
- `data_hex` must contain only valid hex characters (0-9, A-F, a-f).
- `entries[].x` must be in range [-256, 255] (signed 9-bit).
- `entries[].y` must be in range [0, 255] (unsigned 8-bit).
- `entries[].palette` must be in range [0, 7].
- `tiles[].vram_addr` must be in range [0x0000, 0xFFFF].
- Tile count vs dimensions mismatch logs a warning but does not fail (captures may have incomplete data).
- If **all odd bytes are zero** across **many tiles**, abort the capture. This is a strong
  indicator of a bad VRAM read path but not a mathematical impossibility for a single tile.
- If tiles are not 32 bytes, do not hash them.
- When using ROM-trace seeds, validate candidate offsets via HAL decompression before
  indexing; bucket bases are **ranking signals only**.

## Naming Conventions

> **Legacy naming trap:** `oam_base_addr` and `oam_addr_offset` use the `_addr` suffix
> but are **word addresses** (multiply by 2 for bytes). New code should validate units
> at runtime or use explicit `*_word` suffixes. See "Legacy exceptions" in Global Conventions.

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
| `entries[].priority` | int | 0..3 | OBJ vs BG layer priority (not sprite-sprite) |
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

  **Migration status (2025-01):** New captures in `mesen2_exchange/` use `tile_page`.
  Legacy captures may still contain `name_table`. Support removal planned when all
  captures updated.
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
    or transparent regions. These tiles have high collision rates across different
    graphics sets (many sprites share blank/shadow tiles) and contribute noise rather than
    signal to ROM offset scoring. Ignoring them improves match confidence.
  - **Why "2"**: Empirically determined threshold. Tiles with 1-2 unique bytes are
    statistically dominated by blanks (0x00), shadows (single gray value), or
    transparent fill. In Kirby Super Star, ~15% of captured tiles fall below this threshold.
  - **Failure modes**: Setting threshold too low (0-1) includes more noise; too high (3+)
    may exclude legitimate simple sprites (e.g., single-color UI elements).
  - **Tunability**: Override via `LOW_INFO_UNIQUE_BYTES` constant in
    `scripts/validate_seed_candidate.py:24`. Games with more complex palette usage
    may benefit from threshold=3.

**Terminology note:** "Collision" in this context means the same 32-byte tile data
appearing at multiple ROM locations (common for shared tiles like blanks/shadows).
This is **NOT** referring to MD5 hash collisions, which are cryptographically negligible
for 32-byte inputs.

## Mapper Output (CaptureMapResult)
These fields are produced by `CaptureToROMMapper.map_capture()`
(see `core/mesen_integration/capture_to_rom_mapper.py`) for diagnostics and scoring.
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
- High scores with few tiles may result from **shared blank/shadow tiles inflating scores**
  (not to be confused with MD5 hash collisions, which are cryptographically negligible)
- Low scores with many low-info tiles may still indicate correct offset
- Always validate top candidates via decompression before indexing

## tile_hash_database.json

### Schema
```json
{
    "rom_path": "path/to/rom.sfc",
    "metadata": {
        "rom_title": "Kirby Super Star",
        "rom_checksum": 1234567890,
        "rom_size": 4194304,
        "rom_header_offset": 0
    },
    "blocks": [
        {
            "rom_offset": 1769472,
            "description": "Kirby sprites (0x1B0000)",
            "tile_count": 352,
            "hashes": ["d41d8cd98f00b204e9800998ecf8427e", "..."]
        }
    ]
}
```

### Fields
- `rom_path` (string): Path to ROM file used to build database
- `metadata.rom_title` (string | null): ROM internal title
- `metadata.rom_checksum` (int | null): ROM checksum for validation
- `metadata.rom_size` (int): ROM file size in bytes
- `metadata.rom_header_offset` (int): 0 or 512 (SMC header)
- `blocks[]`: Array of indexed ROM regions
  - `rom_offset` (int): File offset where decompression started
  - `description` (string): Human-readable label
  - `tile_count` (int): Number of 32-byte tiles in this block
  - `hashes` (array of string): MD5 hashes (32 hex chars each), indexed by tile position

### Runtime Lookup Structure
When loaded, the database builds an internal reverse index (not stored in JSON):
```python
_hash_to_match: dict[str, list[TileMatch]]
# TileMatch = (rom_offset, tile_index, confidence, description)
```

The `hit_count` referenced in scoring pseudocode equals `len(matches)` for a given hash.

### Schema Validation

To validate capture JSON files against expected structure:

```bash
python3 scripts/validate_seed_candidate.py --dry-run <capture.json>
```

For CI integration, the script exits non-zero on validation failures.

> **Note:** Dedicated JSON schema validator not yet implemented.
> Current validation is embedded in `validate_seed_candidate.py`.

## vram_tile_database.json (Strategy A)
For SA-1 games with character conversion active, direct ROM→VRAM hash matching fails.
This database maps VRAM tile hashes to ROM regions via timing correlation instead.

### Timing Correlation Algorithm

**Overview:** When VRAM tiles don't match ROM-decompressed bytes directly, we correlate
*when* a tile appears in VRAM with *which ROM regions* were accessed during the same
time window.

**Data sources:**
- VRAM diff: detects frames where VRAM changed (new tiles uploaded)
- ROM trace: logs PRG-ROM read addresses during the same frames
- WRAM staging: optional, identifies intermediate buffers

**Correlation algorithm (implemented in `analyze_wram_staging.py` and DMA probes):**

```python
# Pseudocode for timing correlation
def correlate_tile_to_rom_region(tile_hash, capture_frame, rom_trace_log):
    # 1. Find ROM reads within the correlation window (same frame ± 1)
    relevant_reads = [
        read for read in rom_trace_log
        if abs(read.frame - capture_frame) <= 1
    ]

    # 2. Bucket reads by 4KB region (0x1000 alignment)
    region_counts = Counter(read.addr >> 12 for read in relevant_reads)

    # 3. Pick the region with the most reads
    if region_counts:
        top_region = max(region_counts, key=region_counts.get)
        return top_region << 12  # Return base address
    return None
```

**How fields are derived:**
- `rom_region`: Base address of the 4KB bucket with the most ROM reads during capture frame
- `confidence`: Number of captures where this tile → region correlation held
- `alternatives`: Number of *different* regions this tile has been seen with (ambiguity measure)

**Correlation window justification:**

| Scenario | ROM Read | VRAM Visible | Delta |
|----------|----------|--------------|-------|
| Simple DMA | Frame N | Frame N | 0 |
| Buffered DMA | Frame N | Frame N+1 | +1 |
| Double-buffer | Frame N | Frame N+1 or N+2 | +1-2 |

Measured on Kirby Super Star (SA-1): 87% of correlations occur at delta=0, 12% at delta=1.
For games with double-buffered sprites, expand window to ±2.

- ±1 frame is a heuristic: VRAM uploads typically lag ROM reads by 0-1 frames
- The pipeline reads ROM, decompresses to WRAM, then DMA transfers to VRAM
- Adjust window for games with different upload patterns (e.g., double-buffered sprites)

**Multi-burst handling:**
- The `RomTraceBurst` class (see `scripts/summarize_rom_trace.py:29`) tracks bursts separately
- Multiple DMA bursts in one frame are bucketed independently
- Each burst has its own `top_buckets()` ranking, preventing cross-contamination

**What "confidence" means:**
- `confidence` is an observation count (integer), NOT a statistical probability
- Higher count = more captures where this tile→region correlation held
- `alternatives` field indicates ambiguity (multiple regions seen for same tile)
- A tile with high confidence but also high alternatives is unreliable

**Limitations and failure modes:**
- Correlation ≠ causation: the region accessed may be metadata/pointers, not tile data
- Pointer/table reads can dominate buckets if `ROM_TRACE_MAX_READS` clips early
- Use first-read address or run-start within hot bucket as seed, not bucket base
- Always validate via HAL decompression before treating `rom_region` as a tile source

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

---

## dma_probe_log.txt (Instrumentation Contract v1.1)

DMA probe logs are line-oriented text files produced by `mesen2_dma_probe.lua`.

### Log Header (Required)

First line must be the header:
```
# LOG_VERSION=1.1 RUN_ID=1735678900_a3f2 ROM=Kirby Super Star (USA) SHA256=N/A PRG_SIZE=0x100000
```

| Field | Description |
|-------|-------------|
| `LOG_VERSION` | Contract version (must be in SUPPORTED_VERSIONS) |
| `RUN_ID` | Unique run identifier (format: `{timestamp}_{random_hex}`) |
| `ROM` | ROM name (may contain spaces) |
| `SHA256` | ROM SHA256 hash (or "N/A" if unavailable) |
| `PRG_SIZE` | PRG ROM size in hex (or "N/A") |

### Log Line Formats

All data lines have timestamp prefix: `HH:MM:SS <content>`

#### SA1_BANKS
Logged at init and on any bank register write ($2220-$2225):
```
SA1_BANKS (init): frame=0 run=123_a3f2 cxb=0x00 dxb=0x01 exb=0x02 fxb=0x03 bmaps=0x00 bmap=0x00
```

| Field | Register | Purpose |
|-------|----------|---------|
| `cxb` | $2220 | ROM bank for $00-$1F |
| `dxb` | $2221 | ROM bank for $20-$3F |
| `exb` | $2222 | ROM bank for $80-$9F |
| `fxb` | $2223 | ROM bank for $A0-$BF |
| `bmaps` | $2224 | BW-RAM mapping (SNES side) |
| `bmap` | $2225 | BW-RAM mapping (SA-1 side) |

#### CCDMA_START
Logged on rising edge of DCNT.C bit when M=1 (character conversion mode):
```
CCDMA_START: frame=100 run=123_a3f2 dcnt=0xA0 cdma=0x03 ss=0 (ROM) dest_dev=0 (I-RAM) src=0x3C8000 dest=0x003000 size=0x0800
```

| Field | Description |
|-------|-------------|
| `dcnt` | DCNT register ($2230) raw value |
| `cdma` | CDMA register ($2231) raw value |
| `ss` | Source Select: 0=ROM, 1=BW-RAM, 2=I-RAM |
| `dest_dev` | Destination: 0=I-RAM, 1=BW-RAM |
| `src` | 24-bit source address (SA-1 bus space) |
| `dest` | 24-bit destination address (I-RAM/BW-RAM, **not VRAM**) |
| `size` | Transfer size in bytes |

**Routing:** Use `ss` field to determine path:
- `ss=0` → Direct path (Phase 2A): ROM → CCDMA → I-RAM → SNES DMA → VRAM
- `ss=1,2` → Staging path (Phase 2B): ROM → staging → CCDMA → I-RAM → SNES DMA → VRAM

#### SNES_DMA_VRAM
Logged for each SNES DMA transfer to VRAM ($2118/$2119):
```
SNES_DMA_VRAM: frame=100 run=123_a3f2 ch=1 dmap=0x01 src=0x3000 src_bank=0x00 size=0x0800 vmadd=0x6000
```

| Field | Description |
|-------|-------------|
| `ch` | DMA channel (0-7) |
| `dmap` | DMAP register (transfer mode) |
| `src` | A1T source address (16-bit) |
| `src_bank` | A1B source bank |
| `size` | DAS transfer size |
| `vmadd` | VMADD at DMA start (VRAM word address) |

### Validation

Use `scripts/validate_log_format.py` to validate log files:
```bash
uv run python scripts/validate_log_format.py mesen2_exchange/dma_probe_log.txt
```

### Analysis

Use `scripts/analyze_ccdma_sources.py` for SS histogram:
```bash
uv run python scripts/analyze_ccdma_sources.py mesen2_exchange/dma_probe_log.txt
```
