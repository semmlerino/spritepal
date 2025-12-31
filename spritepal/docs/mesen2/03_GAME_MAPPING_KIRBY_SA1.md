# 03 Game Mapping: Kirby Super Star (SA-1)

This document is **game-specific**. Do not generalize these assumptions to other SNES titles.

> **Note on "confidence" terminology:** Throughout SpritePal documentation, "confidence" refers
> to observation count (integer), NOT statistical probability. See
> `02_DATA_CONTRACTS.md#what-confidence-means` for the canonical definition.

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

A golden test is a reproducible capture that validates the pipeline end-to-end. Create one once
mapping works reliably, then run it before major changes.

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
