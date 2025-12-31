# 03 Game Mapping: Kirby Super Star (SA-1)

This document is **game-specific**. Do not generalize these assumptions to other SNES titles.

## Cartridge / CPU
- Kirby Super Star uses the **SA-1** coprocessor.
- ROM mapping for banks $C0-$FF commonly maps to ROM space, but **SA-1 mapping registers can
  change behavior**. Treat mapping formulas as conditional unless verified by probes.

### Address Conversion Reference
When ROM trace addresses need conversion to file offsets, use these formulas as starting
points. **SA-1 games can remap banks dynamically**; verify with probes before trusting.

**LoROM (standard, non-SA-1):**
```python
# CPU address → file offset (for banks $00-$7D, $80-$FF)
def lorom_to_file(bank, offset):
    if offset < 0x8000:
        return None  # Not ROM space
    return ((bank & 0x7F) << 15) | (offset & 0x7FFF)
```

**HiROM (standard, non-SA-1):**
```python
# CPU address → file offset (for banks $C0-$FF or $40-$7D)
def hirom_to_file(bank, offset):
    return ((bank & 0x3F) << 16) | offset
```

**SA-1 (Kirby Super Star):**
SA-1 uses configurable bank registers at $2220-$2223. Default power-on mapping:
- Banks $C0-$CF → ROM $000000-$0FFFFF (first 1MB)
- Banks $D0-$DF → ROM $100000-$1FFFFF (second 1MB)
- Banks $E0-$EF → ROM $200000-$2FFFFF (third 1MB)
- Banks $F0-$FF → ROM $300000-$3FFFFF (fourth 1MB)

```python
# SA-1 default mapping (assumes power-on state)
def sa1_to_file(bank, offset):
    if 0xC0 <= bank <= 0xFF:
        return ((bank - 0xC0) << 16) | offset
    return None  # Needs bank register lookup
```

**Important:** For Kirby Super Star, prefer `emu.convertAddress()` in Lua or the
`--auto-map` flag in validation scripts to handle remapped banks correctly.

## Decompression Pipeline (Observed)
```
ROM (HAL compressed) → SA-1 CPU decompresses → WRAM buffer → DMA → VRAM
```
- Main CPU callbacks do **not** see SA-1 decompression.
- DMA typically shows **WRAM→VRAM**, not ROM→VRAM.

## Recent Observations (Movie Probe)
These are **run-derived notes** (not rules) and should be re-validated when scripts or ROMs change.
- VRAM diff confirms uploads during gameplay, but **not every VRAM diff frame** shows
  strong WRAM staging overlap.
- High-overlap frames in recent runs showed staging bytes around **WRAM relative
  0x0051xx–0x005E20**. Use this range as a starting point for WRAM watchers/dumps.
- `analyze_wram_staging.py --emit-range` suggests a broader watch window of roughly
  **0x004E00–0x00603F** (relative) when padding/aligning for gameplay captures.
- WRAM-write-triggered captures can separate **buffer fill** from **VRAM usage**:
  - Frame ~1765: **100% VRAM↔WRAM overlap**, staging range **0x001E20–0x00549F**.
  - Frame ~842: **near-zero overlap** (WRAM writes likely unrelated or prefetch).
- WRAM write CPU samples (S-CPU) show execution in **bank $00** with
  `cpu.pc` in the **$893D–$89E9** range (LoROM offsets **0x00093D–0x0009E9**),
  `cpu.k=0x00`, `cpu.dbr=0x7E`. These are likely the routines filling the staging buffer.
- Frames with near-zero WRAM overlap are likely **non-staging frames** (BG-only, reused tiles,
  or uploads outside the dump window), not necessarily capture failures.
- The current tile DB coverage is small; **high-info VRAM tiles often have zero DB hits**.
  Expand coverage using DMA source dumps or WRAM staging ranges found in the probe.
- Heavy logging slows playback; **time-based gating** and multi-minute runs are expected.

## Graphics Set Variability (Room Headers)
Kirby Super Star uses room/level graphics headers that select **sprite graphics sets** per
room. This means offsets vary by context; a static list of offsets is only a bootstrap
seed, not a complete model. If mapping fails in a new room, assume a different sprite gfx
set and re-discover the source via WRAM/DMA traces.

## SA-1 Character Conversion (Risk)
SA-1 supports a character conversion DMA mode that can transform bitmap data into SNES
bitplane tiles on the fly. If active, **VRAM tile bytes will not match ROM-decompressed
bytes**, and hash mapping will fail until this is detected.

### Character Conversion Registers (from Mesen 2 source)
| Register | Name | Function |
|----------|------|----------|
| `$2230` | DCNT | DMA Control — bit 4: auto mode, bit 5: char conversion enable |
| `$2231` | CDMA | Char conversion params — bits 0-1: format (0=8bpp, 1=4bpp, 2=2bpp), bits 2-4: width |
| `$223F` | BBF | Bitmap format — bit 7: BWRAM 2bpp mode |
| `$2240-$2247` | BRF | Bitmap register file 1 (type 2 conversion source) |
| `$2248-$224F` | BRF | Bitmap register file 2 (type 2 conversion source) |

**Type 1 conversion**: CPU reads from IRAM trigger on-the-fly conversion from BWRAM bitmap.
**Type 2 conversion**: Writing to BRF registers triggers conversion to IRAM.

Operational playbook:
- Detect: log SA-1 DMA control (e.g., $2230) and confirm character conversion is enabled.
- If active: treat ROM→VRAM byte equality as invalid.
- Strategy A: build a database from **post-conversion VRAM tiles** (screen capture based).
- Strategy B: capture the source bitmap + conversion params and reproduce conversion offline
  before hashing.

## Bootstrap Sprite Offsets (Seed Only)
These offsets are **initial seeds** used to populate the tile DB. They are not exhaustive
and will not cover every room or state.
- Source: `TileHashDatabase.KNOWN_SPRITE_OFFSETS`
- 0x1B0000: Kirby sprites
- 0x1A0000: Enemy sprites
- 0x180000: Items/UI graphics
- 0x190000: Background tiles
- 0x1C0000: Background gradients
- 0x280000: Additional sprites
- 0x0E0000: Title screen/fonts

**Discovery method:** These offsets were found via ROM trace probing during gameplay.
The `summarize_rom_trace.py` script bucketed PRG-ROM reads and these addresses appeared
consistently during sprite-heavy frames. Validate with `validate_seed_candidate.py`
before relying on them for new states.

## Injection Strategy (After Mapping)
Once a ROM offset is confirmed, choose the edit path based on the storage pipeline:
- **Raw tiles in ROM**: patch 32-byte tiles directly at the ROM offset.
- **HAL-compressed tiles**: decompress → edit → recompress; update any pointers/tables if size changes.
- **Character conversion active**: patch the **source bitmap** or reproduce conversion offline
  and adjust the upstream data; direct VRAM tile patching will not persist.

## Candidate Offset Validation (Required)
ROM-trace buckets are **ranking signals**, not exact block starts. Before indexing a
candidate offset:
- Prefer the **first-read address** (or the first read within the top bucket) as the seed.
- Seeds may point **into** a structure; if decompression fails, try the longest contiguous
  run start within the hot bucket as an alternate seed.
- Attempt HAL decompression at that seed.
- Only keep candidates that decompress cleanly and yield plausible 4bpp tile data.

Suggested minimum pass criteria (matches `scripts/validate_seed_candidate.py` defaults):
- Decompression succeeds.
- `len(data) % 32 == 0`.
- At least **32 tiles** of output.
- At least **20%** of tiles are high-information (`> 2` unique bytes).

## HAL Compression Format

Kirby Super Star (and other HAL Laboratory games) use a proprietary compression format
for storing graphics data in ROM. Key characteristics:

### Format Overview
- **LZ-style compression**: Uses back-references and run-length encoding
- **Variable-length encoding**: Header indicates decompressed size and compression type
- **Tile-aligned output**: Decompressed data is typically tile-aligned (multiples of 32 bytes for 4bpp)

### Tools
- **exhal**: Decompresses HAL-compressed data from ROM to raw tiles
- **inhal**: Compresses raw tile data back to HAL format for ROM injection
- Source: `archive/obsolete_test_images/ultrathink/{exhal.c,inhal.c,compress.c}`
- Binaries: `tools/exhal[.exe]`, `tools/inhal[.exe]`

### Python Interface
```python
from core.hal_compression import HALCompressor

# Decompress sprite data starting at offset 0x1B0000
compressor = HALCompressor()
tile_data = compressor.decompress(rom_path, offset=0x1B0000)

# tile_data is raw 4bpp bitplane data, 32 bytes per 8x8 tile
tile_count = len(tile_data) // 32
```

### Why This Matters for Mapping
- VRAM tiles are **decompressed** (32-byte 4bpp)
- ROM stores **compressed** data (variable size)
- Hash matching works on decompressed tiles, but injection requires re-compression
- Compressed size may differ from original → may need pointer table updates

### Build Compilers
```bash
python compile_hal_tools.py  # Auto-detect platform and compile
```

## Tooling Assumptions
- Uses HAL decompression via `core/hal_compression.py`.
- Current pipeline assumes **4bpp** sprite tiles (32 bytes).
- ROM offsets assume a **headerless** ROM image. If the file has a 512-byte copier
  header, offsets shift by `0x200` and must be adjusted or stripped.
  - Tile DB build now auto-adjusts for SMC headers and stores the header offset in metadata;
    rebuild the DB if you switch ROM files.

## Caveats
- SA-1 ROM address mapping can vary by configuration; validate against `emu.cpuType.sa1` probes
  before trusting bank-based calculations.
- DMA source addresses may be incomplete if only low 16 bits are captured.
- Verify ROM revision/CRC when results look implausible; offsets are not portable across variants.

## Golden Test (Create Once Mapping Works)
Define a single capture (savestate + frame) that reliably maps to a known offset, and record:
- Capture file path
- Expected ROM offset(s)
- ROM hash (CRC32 or SHA1)
Keep this as a regression sanity check before expanding the DB.
