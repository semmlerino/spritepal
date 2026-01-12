# 03 Game Mapping: Kirby Super Star (SA-1)

> **CORRECTION (2026-01-01):** Some sections of this document incorrectly assumed
> SA-1 CCDMA (character conversion) is active for sprite tiles. Analysis shows
> sprite tile DMAs come from **WRAM 0x7E:2000**, not cart ROM, so CCDMA is not
> in play. See `SA1_HYPOTHESIS_FINDINGS.md` for corrections and `CHANGELOG.md`
> entry 2.6.0 for details. The "SA-1 Character Conversion" section below should
> be read with this context.

This document is **game-specific**. Do not generalize these assumptions to other SNES titles.

> **Note on "confidence" terminology:** Throughout SpritePal documentation, "confidence" refers
> to observation count (integer), NOT statistical probability. See
> `02_DATA_CONTRACTS.md#what-confidence-means` for the canonical definition.

## Golden Test ROM

All development and testing was performed with this specific ROM file:

| Property | Value |
|----------|-------|
| **Filename** | `Kirby Super Star (USA).sfc` |
| **Format** | Headerless SFC (no 512-byte copier header) |
| **Size** | 4,194,304 bytes (4 MB) |
| **SHA256** | `4e095fbbdec4a16b075d7140385ff68b259870ca9e3357f076dfff7f3d1c4a62` |

**Verification command:**
```bash
sha256sum "roms/Kirby Super Star (USA).sfc"
```

> **Important:** ROM offsets, database entries, and test results are specific to this ROM.
> Different revisions, regions, or headered ROMs will have different offsets.

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

### Logging SA-1 Bank Register Changes

To understand dynamic bank remapping during gameplay, log writes to $2220-$2223:

```lua
-- SA-1 Bank Register Logger
-- Usage: Run with ROM to see bank remapping during gameplay

local bank_names = { [0x2220] = "CXB", [0x2221] = "DXB", [0x2222] = "EXB", [0x2223] = "FXB" }

local function log_bank_write(addr, value)
    local reg_name = bank_names[addr] or string.format("$%04X", addr)
    local bank_range = ({
        [0x2220] = "$C0-$CF",
        [0x2221] = "$D0-$DF",
        [0x2222] = "$E0-$EF",
        [0x2223] = "$F0-$FF"
    })[addr]

    -- Value bits: 0-2 = ROM block (0-7, each 1MB)
    -- Bit 7: Controls offset mode for LOW banks only ($00-$3F, $80-$BF)
    --        0 = use base offset (LoROM-style), 1 = use block-based offset
    --        Has NO effect on HIGH banks ($C0-$FF) which always use block offset
    -- Source: Mesen2/Core/SNES/Coprocessors/SA1/Sa1.cpp:UpdatePrgRomMappings()
    local rom_block = value & 0x07
    local low_bank_mode = (value & 0x80) ~= 0  -- Only affects low bank mapping
    local rom_start = rom_block * 0x100000

    print(string.format("Frame %d: %s ($%04X) = $%02X → HIGH banks %s map to ROM $%06X-%06X%s",
        emu.getState().ppu.frameCount, reg_name, addr, value,
        bank_range, rom_start, rom_start + 0x0FFFFF,
        low_bank_mode and " (bit7: low-bank offset enabled)" or ""))
end

-- Register callbacks for all 4 bank registers
for addr = 0x2220, 0x2223 do
    emu.addMemoryCallback(function(a, v) log_bank_write(a, v) end,
        emu.callbackType.write, addr, addr, emu.cpuType.snes)
end

print("SA-1 bank register logger active")
```

**What to look for:**
- If banks never change from power-on defaults, the static `sa1_to_file()` formula works
- If banks change mid-game, note the frame and context (level load, boss intro, etc.)
- Use `emu.convertAddress()` instead of manual math when banks are dynamic

**Power-on defaults (CXB=0, DXB=1, EXB=2, FXB=3):**
```
$2220 (CXB) = $00 → $C0-$CF maps to ROM $000000-$0FFFFF
$2221 (DXB) = $01 → $D0-$DF maps to ROM $100000-$1FFFFF
$2222 (EXB) = $02 → $E0-$EF maps to ROM $200000-$2FFFFF
$2223 (FXB) = $03 → $F0-$FF maps to ROM $300000-$3FFFFF
```

## Decompression Pipeline (Observed)
```
ROM (HAL compressed) → SA-1 CPU decompresses → WRAM buffer → DMA → VRAM
```
- **Tooling limitation:** S-CPU (`emu.cpuType.snes`) memory callbacks do **not** see SA-1 work.
  To observe SA-1 activity, use `emu.cpuType.sa1` callbacks or infer from DMA/WRAM staging.
- DMA typically shows **WRAM→VRAM**, not ROM→VRAM.

**What this means for the pipeline:**
- Direct ROM tile hashes → VRAM comparison **will fail** (when SA-1 CC is active)
- Strategy A (VRAM-based DB) required for mapping in this game
- ROM trace correlation provides region hints, not byte-level matches
- Injection must target **pre-conversion source**, not VRAM

## When Does Hash Mapping Work? (Decision Tree)

```
VRAM tile captured
    │
    ├─► Is game using SA-1 character conversion or staging transforms?
    │       YES → Hash mapping FAILS (use Strategy A: VRAM-based DB)
    │       NO  ↓
    │
    ├─► Is tile data direct ROM copy after decompression?
    │       NO (runtime composition, effects, staging transforms)
    │           → Hash mapping FAILS
    │       YES ↓
    │
    ├─► Is correct ROM offset in database?
    │       NO  → Expand DB with validated seeds
    │       YES ↓
    │
    └─► Is tile high-information (>2 unique bytes)?
            NO  → Match exists but score is zero (by design)
            YES → MATCH with positive score
```

**Expected failures (not bugs):**
- SA-1 character conversion or similar staging transform (Kirby Super Star: 1.5% match rate)
- Tiles composed at runtime from multiple sources
- Post-decompression palette remapping or effects
- Low-entropy tiles (solid colors, gradients)

---

<details>
<summary><strong>📋 Exploratory Notes: Movie Probe Observations (Dec 2024)</strong></summary>

> **⚠️ EXPLORATORY DATA — NOT SPECIFICATIONS**
>
> These are **run-derived notes** from specific probe sessions, not stable rules.
> Re-validate when scripts, ROMs, or Mesen 2 builds change. Values are seeds for
> investigation, not guaranteed addresses.

**WRAM Staging Patterns:**
- VRAM diff confirms uploads during gameplay, but **not every VRAM diff frame** shows
  strong WRAM staging overlap.
- High-overlap frames in recent runs showed staging bytes around **WRAM relative
  0x0051xx–0x005E20**. Use this range as a starting point for WRAM watchers/dumps.
- `analyze_wram_staging.py --emit-range` suggests a broader watch window of roughly
  **0x004E00–0x00603F** (relative) when padding/aligning for gameplay captures.

**Frame-Specific Observations:**
- WRAM-write-triggered captures can separate **buffer fill** from **VRAM usage**:
  - Frame ~1765: **100% VRAM↔WRAM overlap**, staging range **0x001E20–0x00549F**.
  - Frame ~842: **near-zero overlap** (WRAM writes likely unrelated or prefetch).
- WRAM write CPU samples (S-CPU) show execution in **bank $00** with
  `cpu.pc` in the **$893D–$89E9** range (LoROM offsets **0x00093D–0x0009E9**),
  `cpu.k=0x00`, `cpu.dbr=0x7E`. These are likely the routines filling the staging buffer.

**Interpretation Notes:**
- Frames with near-zero WRAM overlap are likely **non-staging frames** (BG-only, reused tiles,
  or uploads outside the dump window), not necessarily capture failures.
- The current tile DB coverage is small; **high-info VRAM tiles often have zero DB hits**.
  Expand coverage using DMA source dumps or WRAM staging ranges found in the probe.
- Heavy logging slows playback; **time-based gating** and multi-minute runs are expected.

</details>

---

## Confirmed Data Flow Chain (v2.9)

> **Added 2026-01-02:** Confirmed via STAGING_WRAM_SOURCE and BUFFER_WRITE_WATCH probes.

The sprite tile data flow in Kirby Super Star is:

```
ROM (???) → [01:F724 routine] → source buffer (0x1530-0x161A) → staging (0x2000-0x2FFF) → VRAM
                   ^                        ^                           ^
           BUFFER_WRITE_WATCH       STAGING_WRAM_SOURCE           STAGING_SUMMARY
           pcs=01:F724,01:F729      wram_runs=[0x1530-0x161A]     src=0x7E2000
```

### Confirmed Values

| Component | Address/Value | Confidence |
|-----------|---------------|------------|
| **Primary writer routine** | `$01:F724`, `$01:F729` | 100% (observed across multiple gameplay scenarios) |
| **Source buffer range** | `0x1530-0x161A` (235 bytes) | HIGH (max_run=235 in STAGING_WRAM_SOURCE) |
| **Staging buffer range** | `0x2000-0x2FFF` (4KB) | HIGH (DMA source address) |
| **Staging writer PCs** | `$01:90A6`, `$01:99D5` | HIGH (from STAGING_SUMMARY) |

### What's Still Unknown

- **ROM source addresses** — The `01:F724` routine reads from somewhere (ROM, decompressor output, or another WRAM buffer). FILL_SESSION (v2.9) tracks PRG reads during buffer fill to find this.
- **Decompression involvement** — If HAL compression is used, the ROM addresses will be compressed block pointers, not raw tile data.

### Next Investigation Steps

1. Check `FILL_SESSION` entries for `prg_runs` — these are candidate ROM source regions
2. Disassemble `$01:F724` to see what address it reads from
3. If reads from another WRAM buffer, trace that buffer's writer

---

## Graphics Set Variability (Room Headers)
Kirby Super Star uses room/level graphics headers that select **sprite graphics sets** per
room. This means offsets vary by context; a static list of offsets is only a bootstrap
seed, not a complete model. If mapping fails in a new room, assume a different sprite gfx
set and re-discover the source via WRAM/DMA traces.

## SA-1 Character Conversion (Risk)
SA-1 supports a character conversion DMA mode that can transform bitmap data into SNES
bitplane tiles on the fly. If active, **VRAM tile bytes will not match ROM-decompressed
bytes**, and hash mapping will fail until this is detected.

### Character Conversion Registers
Source: https://wiki.superfamicom.org/sa-1-registers (verify against emulator source if behavior differs)

| Register | Name | Bitfield | Function |
|----------|------|----------|----------|
| `$2230` | DCNT | `CPMT-DSS` | C:DMA enable, P:priority(0=CPU,1=DMA), M:mode(0=normal,1=char), T:type(0=SA1→IRAM,1=BW→IRAM), D:dest(0=IRAM,1=BWRAM), SS:source(00=ROM,01=BWRAM,10=IRAM) |
| `$2231` | CDMA | `E--SSSCC` | E:completion flag (SNES sets), SSS:width(2^n chars), CC:bpp(00=8,01=4,10=2) |
| `$223F` | BBF | `C-------` | C:color mode (0=16-color, 1=4-color) |
| `$2240-$2247` | BRF | data | Bitmap register file 1 (type 2 conversion source) |
| `$2248-$224F` | BRF | data | Bitmap register file 2 (type 2 conversion source) |

**Type 1 conversion**: SA-1 CPU reads from IRAM trigger on-the-fly conversion from BWRAM bitmap.
**Type 2 conversion**: Writing to BRF registers triggers conversion to IRAM.

Operational playbook:
- Detect: log SA-1 DMA control (e.g., $2230) and confirm character conversion is enabled.
- If active: treat ROM→VRAM byte equality as invalid.
- **Strategy A** (implemented): build a database from **post-conversion VRAM tiles** (screen
  capture based). Match VRAM hashes to ROM regions via timing correlation, not byte equality.
- **Strategy B** (NOT IMPLEMENTED): capture the source bitmap + conversion params and reproduce
  conversion offline before hashing. Would require: (1) logging BRF register writes, (2)
  implementing SA-1 character conversion algorithm in Python, (3) matching pre-conversion bitmaps
  to ROM. This is a potential future enhancement but is not currently supported.

> **Pipeline note:** IRAM is used internally by SA-1 character conversion hardware
> but is **not directly read** by this capture/mapping tooling. Our pipeline captures
> VRAM post-conversion. The conversion algorithm discussion above is for understanding
> why direct ROM→VRAM matching may fail, not for implementing IRAM reads.

### Detecting Character Conversion (Operational)

To confirm SA-1 character conversion is active:

1. **Log $2230 writes** (DCNT register):
   - Bit 5 (M) = 1 indicates character conversion mode enabled
   - Use `emu.addMemoryCallback` on write to $2230

2. **Log $2231 writes** (CDMA register):
   - Bits 0-1 (CC) indicate bpp: 00=8bpp, 01=4bpp, 10=2bpp
   - Bit 7 (E) is completion flag (set by SNES, not SA-1)

3. **Compare hash match rates**:
   - <10% match rate strongly suggests conversion is active
   - >80% match rate suggests direct ROM→VRAM copy

```lua
-- Example: Log character conversion enable
emu.addMemoryCallback(function(addr, value)
    local mode_bit = (value >> 5) & 1
    if mode_bit == 1 then
        print("SA-1 character conversion ENABLED")
    end
end, emu.callbackType.write, 0x2230, 0x2230, emu.cpuType.snes)
```

**CPU Context Note:** $2230/$2231 are SA-1 registers written by the **S-CPU** (not SA-1 CPU).
Using `emu.cpuType.snes` is correct for detecting when the S-CPU configures character conversion.
To observe the actual conversion execution by SA-1, use `emu.cpuType.sa1` callbacks on destination
addresses (e.g., IRAM reads that trigger type 1 conversion).

**Dual-CPU Logging Pattern:**
```lua
-- S-CPU writes to $2230 (config)
emu.addMemoryCallback(log_config, emu.callbackType.write, 0x2230, 0x2230, emu.cpuType.snes)
-- SA-1 reads from BRF registers (type 2 conversion source)
emu.addMemoryCallback(log_sa1_read, emu.callbackType.read, 0x2240, 0x224F, emu.cpuType.sa1)
```

### Working Hypothesis: SA-1 Conversion Active in Kirby Super Star

> **Status:** Unconfirmed. Evidence is correlational (1.5% hash match rate).
> **Required for confirmation:** $2230/$2231 register logging showing char conversion mode bit set during sprite decompression.
>
> SA-1 character conversion (or similar staging transform) appears **active during gameplay**.
> To **confirm the mechanism**, log $2230/$2231 register writes and verify the mode bit. See "Detecting Character Conversion" above.

| Test | Result |
|------|--------|
| ROM tiles (HAL-decompressed 0x1B0000) | 352 tiles, clear Kirby sprites visible |
| VRAM capture (frame 2012, gameplay) | 66 tiles, character sprites visible |
| Hash match rate | **1.5%** (only blank/trivial tiles matched) |
| ROM trace hot regions | 0x160000 (175K reads), 0x1B0000 (78K reads) |

**Visual inspection** shows both ROM and VRAM contain recognizable sprites, but byte-level
hashes do not match. This indicates VRAM tile bytes are not a direct copy of decompressed
ROM data. Possible causes include:
- SA-1 character conversion (bitmap→bitplane transformation)
- Post-decompression processing (palette remapping, effects)
- Dynamic tile composition from multiple sources
- Decompression into a staging format different from final 4bpp layout

The pipeline's low match rate (1.5%) is consistent with character conversion being active,
but this is a working hypothesis, not a confirmed mechanism.

**ROM regions accessed during gameplay:**
- `0x160000` (175K reads) - NOT in bootstrap DB, likely level-specific graphics
- `0x1B0000` (78K reads) - IN DB but tiles don't hash-match due to conversion
- `0x210000`, `0x2D0000` - Additional graphics sets

**Recommended approach:** Strategy A (VRAM-based database) with ROM offset correlation via
timing/DMA traces. Direct ROM→VRAM hash matching will not work for this game.

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

The `compile_hal_tools.py` script builds exhal/inhal binaries for HAL compression:

```bash
python compile_hal_tools.py          # Build for current platform
python compile_hal_tools.py --check  # Check if tools exist
python compile_hal_tools.py --clean  # Remove compiled binaries
python compile_hal_tools.py --force  # Rebuild even if tools exist
```

**What it builds:**
- `exhal` / `exhal.exe` - HAL decompression (ROM extraction)
- `inhal` / `inhal.exe` - HAL compression (ROM injection)

**Platform requirements:**
- Linux/macOS: gcc or clang, make (`sudo apt-get install build-essential`)
- Windows: MinGW-w64 (gcc) or Visual Studio

**Expected outputs:** Binaries are placed in `tools/` directory with a `.platform_*` marker file.

**Failure modes:**
- Exit 1: Compiler not found
- Exit 2: Source files not found
- Exit 3: Compilation failed (check error output)

**Source location:** `../archive/obsolete_test_images/ultrathink/`

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

### Common Misconceptions

**"If I can see a sprite, its tiles should exist verbatim in ROM"**
- FALSE for: SA-1 character conversion, runtime composition, palette effects
- TRUE for: Direct decompression without post-processing (rare in SA-1 games)

**"A high hash match score proves correct ROM offset"**
- FALSE if: Low-entropy tiles dominate, or collisions inflate scores
- TRUE if: Multiple high-info tiles consistently map to same offset

## Golden Test (Regression Baseline)

A golden test is a reproducible capture that validates the pipeline end-to-end. The baseline
file below should be validated before major changes. Update it when mapping reliability improves.

### Golden Test Specification

The golden test file is at `mesen2_exchange/golden_test.json`:
```json
{
  "name": "kirby_spring_breeze_gameplay",
  "description": "Kirby visible in Spring Breeze, frame ~1800",
  "rom": {
    "filename": "Kirby Super Star (USA).sfc",
    "sha256": "<rom_sha256_hash>",
    "header_offset": 0
  },
  "capture": {
    "script": "gameplay_capture.lua",
    "savestate": null,
    "target_frame": 1800
  },
  "expectations": {
    "min_visible_sprites": 5,
    "min_high_info_tiles": 10,
    "known_rom_regions": ["0x1B0000", "0x160000"],
    "min_match_rate": 0.01
  }
}
```

### Running the Golden Test

```bash
# 1. Capture (from Windows or via WSL interop)
.\tools\mesen2\Mesen2.exe --testrunner "roms\Kirby Super Star (USA).sfc" \
    "mesen2_integration\lua_scripts\gameplay_capture.lua"

# 2. Validate capture integrity
python3 scripts/analyze_capture_quality.py mesen2_exchange/sprite_capture_*.json

# 3. Check expectations (manual for now)
#    - visible_count >= min_visible_sprites
#    - High-info tiles >= min_high_info_tiles
#    - ROM trace regions include known_rom_regions

# 4. If all pass, the pipeline is healthy
```

### When to Run
- Before expanding the tile database
- After upgrading Mesen 2 builds
- After modifying capture scripts
- Before releasing changes to the mapping pipeline

## PRG Ablation: Causal ROM Regions for Sprite Staging

PRG ablation (v2.25) identifies which ROM regions causally feed sprite staging DMAs
by corrupting reads and measuring payload_hash changes. This section documents
proven causal regions for gameplay sprite tiles.

### Methodology

1. **Baseline run** (ABLATION_ENABLED=0): Record payload_hash for each STAGING_SUMMARY
2. **Ablation run**: Corrupt reads from a PRG range, compare payload_hash
3. **Causality criteria**: DMA identity matches (frame, src, size, vram, seq, pcs, range, pattern)
   but payload_hash differs → that PRG range is causal for that DMA

### Proven Causal Regions (Gameplay Frames 1500+)

| ROM Range | Size | Flips | Hit Addresses | Notes |
|-----------|------|-------|---------------|-------|
| 0xE90000-0xE93FFF | 16KB | 5 | 0xE93AEB | First hit @ frame 1680, first flip @ 1681 |
| 0xE94000-0xE97FFF | 16KB | 15 | 0xE9677F, 0xE94D0A | Signature DMAs: 1793, 2003, 2007, 2011, 2015, 2357 |
| 0xE98000-0xE9BFFF | 16KB | 1 | 0xE98DDF | Isolated hit @ frame 1861 → flip 1862 |
| 0xE9C000-0xE9FFFF | 16KB | 17 | 0xE9E667 | Dominant cluster, every-4-frame pattern @ 0x58E0 |

### Non-Causal Regions (Tested)

| ROM Range | Size | Result |
|-----------|------|--------|
| 0xC00000-0xCFFFFF | 1MB | No flips (Bank C not on sprite path) |
| 0xEB0000-0xEBFFFF | 64KB | No flips despite SA1_BURST reads |

### Key Observations

1. **S-CPU reads dominate**: All ABLATION_HITs in E9 were `cpu=snes`, not SA-1
2. **Timing consistency**: First flip appears exactly one frame after first ABLATION_HIT
3. **Data substitution**: Flips produce different valid payload states, not random corruption
4. **Four independent clusters**: E9 bisected to 16KB resolution (lower-lower, lower-upper, upper-lower, upper-upper)

### Signature DMAs for Validation

When testing new PRG ranges, check for flips in these signature DMAs:

| Frame | VRAM | Size | Description |
|-------|------|------|-------------|
| 1681 | 0x58E0 | 640 | First flip after E93AEB hit |
| 1793 | 0x5A20 | 640 | First flip after E9677F hit |
| 1795 | 0x58E0 | 640 | First flip after E9E667 hit (E9 upper) |
| 2003, 2007, 2011, 2015 | 0x58E0 | 640 | Periodic after E94D0A hits |
| 2357 | 0x58E0 | 640 | Late-game signature |

### Ablation Test Files

- `prg_sweep_baseline_v225.txt` - Baseline (306 sprite VRAM entries)
- `prg_sweep_E9_lower_lower.txt` - 0xE90000-0xE93FFF (5 flips)
- `prg_sweep_E9_lower_upper.txt` - 0xE94000-0xE97FFF (15 flips)
- `prg_sweep_E9_upper.txt` - 0xE98000-0xE9FFFF (18 flips)

### Minimal Causal Read Addresses (Bisected to 1 Byte)

Full binary search from 16KB to 1 byte identifies the smallest ROM region where
ablating reads is sufficient to cause payload_hash flips.

| Address | Flips | Reduction | Interpretation |
|---------|-------|-----------|----------------|
| **0xE9E667** | 17 | 8KB → 1B | Compressed stream block start |
| **0xE93AEB** | 5 | 16KB → 1B | Compressed stream block start |

### PRG Read Trace Analysis (v2.34)

The "killer experiment" logged ROM reads following each causal byte read.
**Result: Both are sequential stream starts, not control/selector bytes.**

**0xE9E667 Trace:**
```
TRIGGER: frame=1794 addr=0xE9E667 value=0xE0
  [  1] CPU:00:841F (file:0x00841F) = 0x3B   ← code/polling
  [  2] CPU:E9:E668 (file:0x29E668) = 0x49   ← sequential +1
  [  3] CPU:E9:E669 (file:0x29E669) = 0x98   ← sequential +2
  [  4] CPU:E9:E66A (file:0x29E66A) = 0x90   ← sequential +3
  ...continues sequentially to E9:E6B9 (100 reads)
```
- **Cadence:** Every 4 frames (1794, 1798, 1802...) - 17 triggers total
- **Pattern:** Pure sequential streaming with periodic 00:841F reads interspersed

**0xE93AEB Trace:**
```
TRIGGER: frame=1284 addr=0xE93AEB value=0xE0
  [  1] CPU:E9:3AEC (file:0x293AEC) = 0x33   ← sequential +1
  [  2] CPU:E9:3AED (file:0x293AED) = 0x00   ← sequential +2
  [  3] CPU:E9:3AEE (file:0x293AEE) = 0x7F   ← sequential +3
  ...continues sequentially to E9:3B3C (100 reads)
```
- **Cadence:** Irregular (1284→1288→1293→1298→1680) - sparse with 382-frame gap
- **Pattern:** Same sequential streaming as E9E667

### Confirmed Findings

| Property | 0xE9E667 | 0xE93AEB |
|----------|----------|----------|
| **Role** | Stream block start | Stream block start |
| **Header byte** | 0xE0 | 0xE0 |
| **Read pattern** | Sequential (E668, E669...) | Sequential (3AEC, 3AED...) |
| **CPU** | SA-1 | SA-1 |
| **Cadence** | 4-frame regular (animation) | Irregular/sparse (on-demand) |
| **Triggers** | 17 in test window | 5 in test window |

**Key insight:** Both addresses are the **first byte of compressed/structured data streams**.
`0xE0` appears to be a stream header byte for the game's sprite/asset compression format.

Ablating the first byte corrupts the stream header, causing the decoder to produce
different output → different WRAM staging → payload_hash flip.

### Why WRAM Diff Patterns Differ

The earlier WRAM diff showed:
- 0xE9E667: 85 ranges, 139B largest
- 0xE93AEB: 35 ranges, 384B largest

This reflects **different compressed content** in each stream, not a hierarchy:
- Different source data → different decoder outputs
- Different patterns of zeros/FFs in resulting buffer
- Different asset sizes/structures

### Cadence Interpretation

| Address | Cadence | Likely Purpose |
|---------|---------|----------------|
| 0xE9E667 | +4 frames exactly | Animation batch refresh / periodic streaming |
| 0xE93AEB | Sparse with gaps | Loaded on demand (scene transition / asset swap) |

### Block Boundary Analysis (v2.35)

Measured contiguous read spans by filtering same-bank reads only:

| Block | Start | End | Size | Next Asset |
|-------|-------|-----|------|------------|
| **0xE9E667** | 0xE9E667 | 0xE9E84E | **488 bytes (0x1E8)** | → 0xE98DDF |
| **0xE93AEB** | 0xE93AEB | 0xE93D33 | **585 bytes (0x249)** | → 0xE9677F |

**Observations:**
- Both blocks are **medium sprite chunks** (~500 bytes compressed)
- Block sizes are **consistent across all frames** (not variable-length streaming)
- The "next asset" addresses (0xE98DDF, 0xE9677F) were in the pending bisection list
- Decoder reads from bank 00 (0x00841F) interspersed with data reads (lookup table)

**Block classification:**
- ~500 bytes compressed → likely decompresses to 1-2KB of tile data
- Consistent with single sprite animation frame or small sprite sheet
- Not tiny per-frame patches, not large scene packs

### Header Analysis (v2.35.1)

Examined block headers and adjacency:

```
E9E667: E0 49 98 90 4C 48 26 24 13 12 89 89 E4 24 F8 88
E93AEB: E0 33 00 7F A0 1F 00 7F 82 7D 10 ED 02 F5 02 F8
```

**Findings:**
- Both start with `E0` but no obvious length field matches block sizes (488, 585)
- `E0` is NOT a unique block marker - 888 occurrences in bank E9 alone
- After E93AEB block ends (0x293D33), next byte is `E0 3F...` (another block!)
- But decoder JUMPS to 0xE9677F (10KB away) - **pointer-based selection**

**Adjacency test:**
| Block End | Next Read | Gap | Has E0? |
|-----------|-----------|-----|---------|
| E9E84E | E98DDF | -23KB (backwards!) | NO |
| E93D33 | E9677F | +10KB | NO |

The "next read" addresses (E9677F, E98DDF) are **NOT** asset blocks - they're
decoder lookup tables (no E0 header). The decoder uses a pointer table to
select which blocks to decompress.

### Asset Pointer Table Discovery (v2.36)

**Critical correction:** The 0x00841F addresses seen in traces are SNES CPU addresses,
not file offsets. For LoROM: `file_offset = (bank & 0x7F) * 0x8000 + (addr & 0x7FFF)`.

Instead of analyzing 0x00841F directly, we searched the ROM for **pointers TO our
known causal addresses** (little-endian 24-bit: `67 E6 E9` and `EB 3A E9`).

**Result: Asset pointer table at CPU 0xC0FE52 (file 0x00FE52)**

The table contains packed 24-bit little-endian pointers spanning banks E8, E9, EA, EF:

```
File 0x00FE52:  53 65 E9  C8 53 E9  99 DE E9  0D 92 E9 ...
                ↑         ↑         ↑         ↑
              ptr[0]    ptr[1]    ptr[2]    ptr[3]
```

**Key entries in the pointer table:**

| Index | Table Offset | Pointer | Notes |
|-------|--------------|---------|-------|
| 6 | 0xFE64 | **0xE93AEB** | Causal byte #1 |
| 19 | 0xFE8B | 0xE98DDF | "Next read" after E9E667 decoded |
| 40 | 0xFECA | **0xE9E667** | Causal byte #2 |

**Implications:**
1. The decoder uses **table indices** (not raw addresses) to select compressed assets
2. Ablating a causal byte corrupts **one specific asset** (the one at that table index)
3. The "jump backwards" behavior (-23KB from E9E667→E98DDF) is explained: decoder
   reads entry 40, then entry 19 - they're just non-adjacent in ROM
4. Table extends from 0xFE52 through at least 0xFFFF (~100+ entries total)

**All remaining bisection targets found in table:**
| Target | Table Offset | Index | Status |
|--------|--------------|-------|--------|
| E94D0A | 0xFE61 | 5 | In main table |
| E98DDF | 0xFE8B | 19 | In main table |
| E9677F | 0xFF2A | 72 | In extended table |

**Table structure analysis:**
- **0xFE00-0xFE4E**: Different format (not 24-bit pointers)
- **0xFE52-0xFF51**: Main pointer table (indices 0-85 are clean E8/E9/EA/EF)
- **0xFF54-0xFF5F**: Anomalous entries including `0x7E2000` (WRAM staging!)
- **0xFF60-0xFFE4**: More valid pointers + transitions
- **0xFFE7-0xFFFF**: Filler (0xFFFFFF)

**Verified: Pointers point DIRECTLY to record starts** (no secondary indirection):
```
idx  6 → 0xE93AEB: read starts at 0xE93AEB ✓
idx 40 → 0xE9E667: read starts at 0xE9E667 ✓
```

**Record types vary by first byte** (don't classify by E0 alone):
| First Byte | Example Indices | Notes |
|------------|-----------------|-------|
| `E0` | 6, 40 | Our measured compressed blocks |
| `02` | 1 | Different format |
| `03` | 19 | Different format |
| `1F` | 72 | Different format |
| `23` | 0 | Different format |
| `25` | 5 | Different format |

### Pointer Table Access Pipeline (v2.37)

**Key discovery:** The ROM pointer table is accessed directly via LoROM mapping, not
cached in WRAM. The backtrace tracer captured the complete fetch sequence:

**Pipeline:**
```
Index → ROM[01:FE52 + idx*3] → DP[00:0002-0004] → PRG Stream
```

**Trace evidence (frame 1284, E9:3AEB load):**
```
01:FE64 = 0xEB (lo)   ← ROM table read (idx 6 = 0xFE52 + 6*3 = 0xFE64)
01:FE65 = 0x3A (hi)
01:FE66 = 0xE9 (bank)

00:0002 = 0xEB (lo)   ← Direct page cache (pointer copied here)
00:0003 = 0x3A (hi)
00:0004 = 0xE9 (bank)

E9:3AEB PRG read      ← Asset streaming begins
```

**Address mapping clarified:**
- File offset `0x00FE64` = CPU address `01:FE64` (LoROM bank 01)
- The earlier "0 reads from C0:FE52" was watching wrong address space
- Table is accessed via bank 01 mirror, not bank C0

**Direct page pointer cache:**
- Location: `00:0002-00:0004` (lo, hi, bank bytes)
- Updated immediately before PRG stream starts
- Potential additional slots at `00:0005-0007`, `00:0008-000A`, etc.

**CPU split pattern:**
- S-CPU likely computes index and reads table
- SA-1 performs streaming decode
- Both CPUs involved in different pipeline stages

**Implications for extraction:**
1. Watch ROM table reads at `01:FE52-01:FFFF` to capture all index→pointer mappings
2. Monitor DP writes to detect pointer cache updates
3. Link PRG stream starts to preceding DP pointer for full attribution
4. Each unique (index, pointer) pair = one selectable asset

### Next Steps

**1) ~~Find the pointer/index table~~ DONE (v2.36)**
Found at 0xC0FE52 / 01:FE52. Causal bytes are at table indices 6 and 40.

**2) ~~Trace pointer access pipeline~~ DONE (v2.37)**
Complete pipeline: idx → ROM table → DP cache → PRG stream.

**3) Mid-block ablation test:**
Ablate byte at E9E667+0x80 (inside block, not header) to confirm content
drives output, not just header corruption.

**3) Map blocks to staging regions:**
Capture staging buffer before/after decode to see which $7E2000-$27FF
region each block fills

**Remaining targets for bisection:**
| Address | Flips | Status |
|---------|-------|--------|
| 0xE94D0A | 4 | Pending |
| 0xE9677F | 1 | Pending |
| 0xE98DDF | 1 | Pending |

### Automated Bisection Tool

For faster bisection, use the automation tools (v2.28):

```batch
REM From Windows:
cd C:\CustomScripts\KirbyMax\workshop\exhal-master\spritepal

REM Preview bisection plan:
python scripts\auto_bisect.py 0xE9E667 0xE9E000 0xE9FFFF --dry-run

REM Run automated bisection (~10 min for 8KB→1B):
python scripts\auto_bisect.py 0xE9E667 0xE9E000 0xE9FFFF
```

Files: `run_ablation_range.bat` (parameterized runner), `scripts/auto_bisect.py` (orchestrator)

---

## Per-idx Ablation Proof (v3.0) — CAUSAL CHAIN PROVEN

> **Status: PROVEN** — The idx→ROM[ptr]→staging→VRAM pipeline is causally verified.

### What This Proves

Corrupting ROM data at a pointer target **changes the staging output**. This is definitive
proof that the sprite editor can reliably inject modified sprites by targeting pointer addresses.

### Proof Methodology

1. **Baseline run**: Capture staging payload hash for each idx session
2. **Ablation run**: Corrupt ROM byte at ptr target, capture same DMA identity
3. **Comparison**: Same DMA identity (wram + size) with different hash = causal

### Results: idx=6 (E9:3AEB)

| Metric | Baseline | Ablation (Mode A) | Ablation (Mode B) |
|--------|----------|-------------------|-------------------|
| Record type | 0xE0 | 0xFF (corrupted) | 0xE0 (preserved) |
| WRAM start | 7E2000 | 7E2000 | 7E2000 |
| Size | 640 | — | 640 |
| Staging captures | 5 | **0** (bail) | 5 |
| Hash | B5143253 | — | **31204703** |

**Mode A** (corrupt first byte at ptr): Decoder doesn't recognize 0xFF as valid record
type and bails — no staging output. Proves header byte is critical.

**Mode B** (corrupt byte at ptr+0x10): Decoder runs normally but produces different
output — hash changes from B5143253 to 31204703. Proves data content drives output.

### Interpretation

```
idx=6 → ROM[01:FE64] → ptr=E9:3AEB → decode → staging @ 7E2000 → VRAM
                              ↑
                    corrupt here = output changes
```

- **Same DMA identity** (wram=7E2000, size=640) proves we're measuring the same transfer
- **Different hash** proves the ROM data at that address determines the output
- **Causality established**: modify ROM at ptr → VRAM content changes

### Per-idx Database

Captured via `asset_selector_tracer_v3.lua` with movie playback (3000 frames):

| idx | ptr | record | sessions | staging | hash | status |
|-----|-----|--------|----------|---------|------|--------|
| 5 | E9:4D0A | 0x25 | 5 | 4 | 5F0BB905 | stable |
| **6** | **E9:3AEB** | **0xE0** | **5** | **5** | **B5143253** | **PROVEN** |
| 19 | E9:8DDF | 0x03 | 2 | 2 | B254A8E4 | stable |
| 40 | E9:E667 | 0xE0 | 17 | 17 | EC8FF37F | stable |
| 43 | E9:FB06 | 0x00 | 1 | 1 | 232EE368 | stable |
| 72 | E9:677F | 0x1F | 2 | 2 | 42AEE372, 5F0BB905 | 2 variants |

### Running Ablation Tests

```batch
REM 1. Edit per_idx_ablation_v1.lua:
REM    ABLATION_TARGET_IDX = 6 (or other idx)
REM    ABLATION_ENABLED = false (baseline) or true (ablation)
REM    ABLATION_MODE = "A" (header) or "B" (data)

REM 2. Run baseline:
run_idx_ablation.bat
REM Output: mesen2_exchange/ablation_idx6_baseline.log

REM 3. Edit: ABLATION_ENABLED = true

REM 4. Run ablation:
run_idx_ablation.bat
REM Output: mesen2_exchange/ablation_idx6_ablation.log

REM 5. Compare hash values in the PROOF DATA sections
```

### Implications for Sprite Injection

1. **Injection point**: Modify ROM data starting at `ptr` address
2. **Control point**: The idx→ptr table at 01:FE52 determines which asset loads
3. **Size constraint**: Injected data must fit within original block or pointer table needs update
4. **Format**: Data must match expected record type (0xE0, 0x25, etc.) for decoder to process

### Files

- `mesen2_integration/lua_scripts/asset_selector_tracer_v3.lua` — Full pipeline tracer
- `mesen2_integration/lua_scripts/per_idx_ablation_v1.lua` — Per-idx ablation test
- `run_asset_selector_v3.bat` — Run v3 tracer with movie
- `run_idx_ablation.bat` — Run ablation test

---

## HAL-Compressed Asset Header Bytes (2026-01-12)

> **Added 2026-01-12:** Discovery and fix for tile alignment issues in HAL-decompressed assets.

### Problem

When HAL-decompressing sprite assets from Kirby Super Star, the decompressed data often
contains **leading header bytes** that cause tile misalignment. This results in corrupted
sprite rendering because the 4bpp bitplane decoding starts at the wrong byte offset.

### Observed Cases

| ROM Offset | Decompressed Size | Extra Bytes | Header Value |
|------------|-------------------|-------------|--------------|
| 0x25AD84 | 2209 bytes | 1 | `0x02` |
| 0x25B000 | 2546 bytes | 18 | varies |
| 0x25C000 | 2223 bytes | 15 | varies |
| 0x200000 | 7744 bytes | 0 | (aligned) |

### Root Cause

HAL-compressed assets in Kirby games may include metadata/header bytes at the start:
- **Asset type/ID byte** — e.g., `0x02` indicating sprite data
- **Length prefixes** — For variable-size assets
- **Palette hints** — Which palette index to use
- **Unknown metadata** — Game-specific flags

These bytes are NOT tile data but were being decoded as such, causing:
1. **Bitplane corruption** — First tile has wrong pixel values
2. **Cascading misalignment** — All subsequent tiles are off by N bytes
3. **Wrong colors** — Palette indices don't map to intended colors

### Solution

SpritePal now automatically aligns HAL-decompressed tile data to 32-byte boundaries:

```python
from core.tile_utils import align_tile_data

# After HAL decompression
raw_data = hal.decompress_from_rom(rom_path, offset)  # 2209 bytes
aligned_data = align_tile_data(raw_data)               # 2208 bytes (69 tiles)
```

The `align_tile_data()` function:
1. Checks if data size is a multiple of 32 (BYTES_PER_TILE)
2. If not, strips leading bytes to achieve alignment
3. Assumes header bytes are at the START, not end

### Verification

After alignment, sprite tiles from HAL decompression match VRAM tiles byte-for-byte:

```
VRAM tile $6C @ $CD80:  00 00 FF FF BB C7 FE 01 ED 03 D2 17 B4 3F A0 2F ...
Aligned tile 17:        00 00 FF FF BB C7 FE 01 ED 03 D2 17 B4 3F A0 2F ...
                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                        EXACT MATCH (confirmed via VRAM dump comparison)
```

### Files

- `core/tile_utils.py` — `align_tile_data()`, `get_tile_alignment_info()` functions
- `ui/common/preview_worker_pool.py` — Applies alignment after HAL decompression
- `ui/workers/batch_thumbnail_worker.py` — Applies alignment for thumbnails
- `tests/unit/test_tile_alignment.py` — Unit tests for alignment functions

### Implications for Future Work

1. **Header byte semantics** — The `0x02` header at 0x25AD84 may indicate asset type.
   Investigating this could enable automatic palette selection.
2. **Variable header sizes** — Different assets have 1, 15, or 18 extra bytes.
   A more sophisticated parser could use the first bytes to determine header length.
3. **Injection consideration** — When re-injecting modified sprites, the header bytes
   must be preserved or the game may fail to load the asset.
