# Mesen2 Sprite Extraction Pipeline Changelog

All notable changes to the sprite extraction pipeline documentation and tooling.

---

## Reconciliation of Contradictory Findings (2026-01-01)

Earlier changelog entries contain contradictions due to over-generalization from
single captures. This section clarifies the correct, scoped interpretations.

### 1. "100% HAL-compressed / no uncompressed assets" (v2.4.0) — FALSE

**v2.4.0 claimed:** "There are NO uncompressed sprite assets in the ROM."

**v2.5.2 found:** Tiles exist as raw uncompressed data around ROM 0x3CA000, with
65 strong matches and 1 perfect 32/32 match.

**Correct statement:** ROM contains a **mix** of HAL-compressed blocks and raw
uncompressed tile data. Raw byte searches are unreliable without verification,
but not "always wrong."

### 2. "Planes 0+2 only" (v2.4.0) — SCENE-SPECIFIC, NOT GENERAL

**v2.4.0 claimed:** 98.3% of tiles use only planes 0+2.

**v2.6.0 found:** Gameplay captures show 0/177 "planes 0+2 only"; >90% use all 4 planes.

**Correct statement:** Menu/cutscene captures show planes 0+2 dominance. Gameplay
sprites use full 4bpp. Always tag findings by scene type (menu vs gameplay).

### 3. "CCDMA drives sprite tiles" (SA1_HYPOTHESIS_FINDINGS) — MISATTRIBUTION

**Earlier claimed:** SA-1 character conversion explains sprite upload bytes.

**Corrected:** CCDMA events were for other transfers. Sprite DMAs are WRAM→VRAM
(plain SNES DMA). CCDMA only applies to BW-RAM/cart ROM sources.

### 4. "0/24 transforms" (v2.6.0) vs "65 tiles match well" (v2.5.2)

These are different tile sets from different captures. Neither is universal.
The "0/24" was from frame 1500 gameplay; the "65 matches" were from earlier
captures with different tile content.

**Correct statement:** Match rates vary by scene, tile class, and ROM region.
No single rate applies to "all Kirby tiles."

### 5. Technical Wording Error (v2.4.0)

**v2.4.0 said:** "values 0, 1, 4, 5 - the low 2 bits of the 4-bit palette index"

**Correct:** These values mean bits 1 and 3 are zero (only bits 0 and 2 vary).
Not "low 2 bits." The 4-color conclusion is correct; the bit description was wrong.

### 6. "No $2230 writes → no CCDMA" — WEAK INFERENCE

Not seeing register writes may be an instrumentation gap. The valid logic is:
WRAM→VRAM sprite DMAs imply no CCDMA **on that transfer** (CCDMA doesn't apply
to WRAM sources).

---

**Guidance for future findings:** Tag every observation by:
- **Scene type:** menu, cutscene, gameplay, boss, etc.
- **Tile class:** OBJ (sprite), BG (background), UI
- **Evidence strength:** observed (direct measurement) vs inferred (reasoning)

---

## [2.14.1] - 2026-01-02

### FILL_SESSION Bug Fix and Initial Findings

**Bug Fixed:** Lua forward reference error prevented FILL_SESSION from logging.
- `log_fill_session_summary()`, `reset_fill_session()`, `compress_prg_runs()` were
  called before their definitions (Lua requires forward declarations)
- Added forward declarations at line 410-413
- Changed function definitions to assignment syntax (`func = function()`)

**Initial Trace Results (41 fill sessions captured):**

| PRG Range | Size | SA-1 Bank | Quality |
|-----------|------|-----------|---------|
| `0xE13CA7-0xE13D81` | 219 | $E1 | HIGH (max_run=219) |
| `0xEB3D4B-0xEB3E24` | 218 | $EB | HIGH (max_run=218) |
| `0xE7DF31-0xE7DFFA` | 202 | $E7 | HIGH (max_run=202) |
| `0xE98F3B-0xE98FF5` | 187 | $E9 | HIGH (max_run=187) |
| `0xE9E7B8-0xE9E84E` | 151 | $E9 | HIGH (recurring) |

**Interpretation:** These are SA-1 ROM regions (`$E0-$EF` banks) read during the
buffer fill window. Large contiguous runs (>64 bytes) are likely compressed sprite
data sources. Small runs (<10 bytes) are code/vector fetches (noise).

**Next step:** Convert PRG addresses to file offsets, validate with HAL decompression.

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (forward reference fix)

---

## [2.14.0] - 2026-01-02

### FILL_SESSION - Bounded PRG Read Logging (v2.9)

**Context:** v2.8 confirmed primary writer code at `01:F724` and `01:F729` writes
to source buffer `0x1530-0x161A`. Now we need to trace what ROM regions feed that code.

**Key insight:** Full PRG read logging is prohibitively expensive (causes timeout).
But we only need PRG reads during the **buffer fill window** (from first write to
source buffer until staging DMA fires). This bounded window is safe.

**New Feature:**
- Session starts automatically on first write to source buffer (0x1530-0x161A)
- During session: PRG/ROM reads are logged into ring buffer (256 entries)
- Session ends when staging DMA fires (same trigger as STAGING_SUMMARY)
- Summary logged as `FILL_SESSION` with PRG runs compressed

**Output:** `FILL_SESSION: frame=X vram=0xYYYY dma_size=N prg_total=T prg_unique=U runs=R max_run=M prg_runs=[...]`

**What the runs mean:**
- `prg_runs=[0x123456-0x123478(35)]` = ROM addresses read during buffer fill
- These are candidate ROM source regions for the sprite data
- Convert to file offset using SA-1 bank mapping

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.8 → v2.9)
- `run_staging_trace.bat` (added FILL_SESSION documentation)

**Usage:**
1. Keep BUFFER_WRITE_WATCH=1 (enables fill session tracking)
2. Run the trace
3. Look for `FILL_SESSION` entries with `prg_runs`
4. The PRG runs are your candidate ROM source addresses

---

## [2.13.0] - 2026-01-02

### BUFFER_WRITE_WATCH - Trace Source Buffer Writers (v2.8)

**Context:** v2.7 confirmed STAGING_WRAM_SOURCE works (110 entries, 0 NO_WRAM_PAIRS,
HIGH quality). Discovered primary source buffer: `0x01530-0x0161A` (235 bytes).

**Next rung:** To find the ROM→source buffer link, we need to trace what code
WRITES to `0x01530-0x0161A`. This is the missing link in the data flow:
```
ROM (???) -> source buffer (0x01530) -> staging (0x2000) -> VRAM
      ^           BUFFER_WRITE_WATCH reveals this
```

**New Feature:**
- `BUFFER_WRITE_WATCH=1` - Enable buffer write tracing
- `BUFFER_WRITE_START=0x1530` - Start of source buffer (default from v2.7 discovery)
- `BUFFER_WRITE_END=0x161A` - End of source buffer
- `BUFFER_WRITE_PC_SAMPLES=8` - PC samples to capture per frame

**Output:** `BUFFER_WRITE_SUMMARY: frame=X writes=N range=0xAAAA-0xBBBB pcs=[K:PC,...]`

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.7 → v2.8)
- `run_staging_trace.bat` (added BUFFER_WRITE_WATCH section, disabled by default)

**Usage:**
1. Keep STAGING_WRAM_SOURCE=1 to confirm source region
2. Set BUFFER_WRITE_WATCH=1 to trace writers
3. Look for `BUFFER_WRITE_SUMMARY` in logs
4. The `pcs=[]` values tell you which code writes to the source buffer

---

## [2.12.0] - 2026-01-02

### Full 128KB WRAM Coverage (v2.7)

**Problem:** Previous range `$0000-$FFFF` only covered 64KB (bank $7E). The code normalizes
WRAM to `0x00000-0x1FFFF` (128KB), so we were missing bank $7F entirely.

**Fix:** Extended `STAGING_WRAM_SRC_END` to `0x1FFFF` (full 128KB).

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.6 → v2.7)
- `run_staging_trace.bat` (STAGING_WRAM_SRC_END=0x1FFFF)

---

## [2.11.0] - 2026-01-02

### PC Gating Disabled - Write PCs ≠ Read PCs (v2.6)

**Problem:** v2.5 enabled PC gating using staging write PCs (`01:8FA9`, `00:8952`, `00:893D`),
but the WRAM source reader fires on READ instructions which are 1-3 bytes earlier in copy loops.
Result: only 3 garbage entries vs 107 NO_WRAM_PAIRS (worse than v2.4).

**Fix:** Disabled PC gating until read PCs are discovered. To enable gating later, either:
- Use PC "slop" window (accept ±8 bytes of known PCs), or
- Discover actual read PCs first (log top read PCs with gating off)

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.5 → v2.6)
- `run_staging_trace.bat` (STAGING_PC_GATING=0 with explanation)

---

## [2.10.0] - 2026-01-02

### Improved WRAM Source Coverage (v2.5)

**Run Config Changes** (in `run_staging_trace.bat`, not Lua defaults):
1. **Expanded range**: `STAGING_WRAM_SRC_START/END` set to `$0000-$FFFF` (was `$8000-$FFFF`)
2. **PC gating enabled**: `STAGING_PC_GATING=1` to filter reads by known staging writer PCs
3. **Ring buffer increased**: `STAGING_RING_SIZE=256` (was 32) so 64-byte runs can reach HIGH quality
4. **Quality threshold notes**: Added Lua comments explaining ring buffer size / quality relationship

**Why NO_WRAM_PAIRS was expected (until this fix):**

The log message `NO_WRAM_PAIRS (source not in 0x0000-0xFFFF or not WRAM)` directly tells you:
reads outside your configured `STAGING_WRAM_SRC_START/END` range are invisible.

The Lua normalizes WRAM addresses to `0x00000-0x1FFFF` (128KB). With `STAGING_WRAM_SRC_END=0xFFFF`,
anything in bank $7F (`0x10000-0x1FFFF`) was missed. **Most NO_WRAM_PAIRS are expected while
the watched range is truncated.**

**Note:** v2.5 still only covers 64KB. See v2.12 for full 128KB fix.

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.4 → v2.5)
- `run_staging_trace.bat` (updated range, ring size, PC gating)

---

## [2.9.0] - 2026-01-02

### Critical Bug Fix: WRAM Source Tracking Never Activated (v2.4)

**Problem:** `STAGING_WRAM_SOURCE=1` setting was ignored. All `STAGING_WRAM_SOURCE` log
entries showed `NO_WRAM_PAIRS` even when WRAM reads should have been detected.

**Root Cause:** In `register_wram_source_callbacks()`, line 1602 checked the wrong flag:

```lua
-- BUG (v2.3): Checked wrong flag
if not STAGING_WRAM_TRACKING_ENABLED then return end

-- FIX (v2.4): Check correct flag
if not STAGING_WRAM_SOURCE_ENABLED then return end
```

`STAGING_WRAM_TRACKING_ENABLED` is for a different debug-wide WRAM tracker, not the
staging source tracker. This meant WRAM read callbacks were never registered.

Additionally, `wram_source_callbacks_registered` was set to `true` unconditionally after
calling the function, even when registration failed. This prevented retry on subsequent frames.

**Fix:**
1. Changed guard from `STAGING_WRAM_TRACKING_ENABLED` to `STAGING_WRAM_SOURCE_ENABLED`
2. Function now returns `true`/`false` to indicate success
3. Caller only marks registered if function returned `true`
4. If registration fails, logs warning and retries next frame

**Verification:** After v2.4, log must show a line like one of these (depends on WRAM addressing mode):
```
# Relative mode (common):
INFO: WRAM source callback registered (lazy) for S-CPU: 0x000000-0x00FFFF at frame=1498

# Absolute mode:
INFO: WRAM source callback registered (lazy) for S-CPU: 0x7E0000-0x7EFFFF at frame=1498
```

The range values depend on your `STAGING_WRAM_SRC_START/END` config. If you don't see
this line at all, WRAM source tracking is not active.

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.3 → v2.4)
- `run_staging_trace.bat` (updated WRAM range to $8000-$FFFF)

---

## [2.8.0] - 2026-01-02

### Lua Script Timeout Fixes (v2.2 + v2.3)

**Problem:** `mesen2_dma_probe.lua` was timing out with "Maximum execution time (1 seconds) exceeded" before reaching frame 1.

**Root Cause Analysis:**

Mesen2's Lua timeout (`ScriptTimeout`) is cumulative across all callback execution within a batch, not per-callback. At init and frame 0, the script was:
1. Registering thousands of memory callbacks (staging watch)
2. Logging hundreds of DMA operations

Both operations consumed the entire 1-second budget before frame 1 could start.

**Solution (Two-Part):**

**v2.2 - Lazy Registration:**
- Staging and WRAM source callbacks now registered at frame `STAGING_START_FRAME - 2` (not at init)
- Added `register_staging_callbacks()` and `register_wram_source_callbacks()` functions
- New log message: `INFO: Staging watch will be registered lazily at frame=1498`

**v2.3 - Deferred DMA Logging:**
- Added `CFG.dma_log_start_frame` (defaults to `STAGING_START_FRAME - 10`)
- `log_dma_channel()`, `on_hdma_enable()`, `log_sa1_banks()` skip logging until that frame
- New log message: `INFO: DMA/HDMA/SA1 logging deferred until frame=1490`

**User Action Required:**

Even with v2.3 fixes, heavy callback activity may still timeout. Increase Mesen2's script timeout:

```
Tools -> Script Window -> Settings -> Script Timeout -> 5 (or higher)
```

**Mesen2 Source Reference:**
- `ScriptingContext.cpp:128-130` - Timeout check in `ExecutionCountHook`
- `SettingTypes.h:857` - Default `ScriptTimeout = 1`
- Timer resets at callback batch start, not per-callback

**New Environment Variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `DMA_LOG_START_FRAME` | STAGING_START_FRAME - 10 | Skip DMA logging until this frame |

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.2 → v2.3)
- `run_staging_trace.bat` (updated comments)

---

## [2.7.1] - 2026-01-01

### Lua Script API Alignment Fix

**Fixed:** `mesen2_dma_probe.lua` MEM table and CPU type definitions now use verified Mesen2 API names.

**Problem:** The script used incorrect fallback names that don't exist in Mesen2's Lua API:
- `emu.memType.prgRom` → doesn't exist (correct: `snesPrgRom`)
- `emu.memType.snesVram` → doesn't exist (correct: `snesVideoRam`)
- `emu.cpuType.cpu` → doesn't exist (correct: `snes`)
- `emu.cpuType.SA1` → doesn't exist (correct: `sa1`)

**Root Cause:** Mesen2 exposes C++ enums to Lua with the first letter lowercased
(see `LuaApi.cpp:170-171`). The script had invalid fallbacks that would never match.

**Verification:** Confirmed against Mesen2 source:
- `Mesen2/Core/Shared/MemoryType.h` - Complete MemoryType enum
- `Mesen2/Core/Shared/CpuType.h` - Complete CpuType enum
- `Mesen2/Core/Debugger/LuaApi.cpp` - Enum-to-Lua lowercasing logic

**Changes:**
1. Simplified MEM table to use only verified names (removed invalid fallbacks)
2. Added `sa1_iram` field for SA-1 internal RAM access
3. Removed duplicate `sa1_cpu_type` definition with incorrect fallbacks
4. Added diagnostic logging at startup to show resolved type values

**New Startup Log (example, values vary by Mesen2 build):**
```
MEM types resolved: cpu=0 prg=20 vram=23 wram=21 oam=24 cgram=25 sa1_iram=33
CPU types resolved: snes=0 sa1=3
```

Numbers indicate enum values resolved at runtime (or `nil` if resolution failed).
**Note:** These numbers can change between Mesen2 versions. The script resolves them
dynamically; don't hardcode these values.

---

## [2.7.0] - 2026-01-01

### Staging Buffer Write Tracking System

**New Feature: STAGING_CAUSAL Tracking**

Added comprehensive staging buffer write tracking to answer "What writes to WRAM 0x2000?"

**New Batch File:** `run_staging_trace.bat`
- Traces S-CPU code that writes to WRAM $7E:2000-$2FFF (sprite staging area)
- Captures causal PRG read → staging write pairs
- Reports quality metrics for credibility assessment

**New Environment Variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `STAGING_WATCH_ENABLED` | 0 | Enable staging buffer write monitoring |
| `STAGING_WATCH_START` | 0x2000 | Start of staging buffer region |
| `STAGING_WATCH_END` | 0x2FFF | End of staging buffer region |
| `STAGING_CAUSAL_ENABLED` | 0 | Track PRG read → staging write pairs |
| `STAGING_PC_GATING` | 0 | Only count reads from known copy routine PCs |
| `STAGING_WRAM_TRACKING` | 0 | Track WRAM reads (expensive, opt-in) |

**New Log Formats:**

```
STAGING_SUMMARY: frame=X src=0x7E2000 size=N vram=0xNNNN pattern=SEQUENTIAL_BURST writes=N pcs=[...]
STAGING_CAUSAL: frame=X vram_word=0xNNNN size=N pairs=N quality=HIGH unique_prg=N max_run=N coverage=0.XX prg_runs=[...] cpus={...} read->write_pcs=[...]
```

**Quality Metrics (new):**

- `unique_prg` - Number of unique PRG addresses read
- `max_run` - Longest contiguous PRG run (indicates real data vs code)
- `coverage` - unique_prg / dma_size (high = direct copy, low = decompression)
- `quality=HIGH/MED/LOW` - Assessment of data credibility

**Quality Thresholds:**
- `HIGH`: max_run >= 64 AND coverage > 0.5 (likely real tile data)
- `MED`: max_run >= 32 OR coverage > 0.3
- `LOW`: everything else (likely code/noise or decompression)

**Technical Improvements:**

1. **Session-based pairing** - Pairs PRG reads with staging writes across frame boundaries
   (fixes false NO_PAIRS when read is frame N, write is frame N+1)

2. **Bank $01 PC support** - Added gameplay-discovered copy routine PCs:
   - `$01:8FA9` - Most common gameplay staging writer
   - `$01:9927` - Secondary gameplay routine
   - `$01:E409` - Additional gameplay routine

3. **Instruction-fetch filter** - Rejects PRG reads that are opcode fetches (within 4 bytes of PC)
   to prevent false positives from copy loop code being "matched"

4. **SNES→PRG mapping** - Added `snes_to_prg_offset()` for LoROM address conversion

**Initial Findings (Gameplay Frames 1500+):**

| Metric | Value |
|--------|-------|
| Total STAGING_CAUSAL entries | 165 |
| WITH pairs | 46 (28%) |
| NO_PAIRS | 119 (72%) |

The high NO_PAIRS rate suggests staging writes are NOT fed by direct PRG reads.
Likely data flow: `PRG → SA-1 decompression → WRAM buffer → staging $2000 → VRAM`

**Known Limitation:** WRAM read tracking (to find intermediate buffers) is expensive
(~120KB callback coverage) and disabled by default. Enable with `STAGING_WRAM_TRACKING=1`
only when investigating intermediate buffer patterns.

---

## [2.6.0] - 2026-01-01

### Major Corrections: DMA Source Analysis and Transform Search

**Key Finding: Sprite DMAs Come From WRAM, Not Cart ROM**

Analysis of DMA log around frame 1500 revealed:

| DMA Target | Source | Purpose |
|------------|--------|---------|
| VRAM 0x4000+ (sprites) | WRAM 0x7E:2000 | Sprite tiles |
| VRAM 0x6000+ (BG) | Cart ROM $ED:xxxx, $EE:xxxx | Background tiles |

**Implication:** CCDMA (SA-1 character conversion) is NOT in play for sprite tiles.
CCDMA only applies to BW-RAM/cart ROM sources. WRAM→VRAM is plain SNES DMA copying
already-final planar bytes.

**Transform Search (Frame 1500 Gameplay OBJ Tiles):**

Tested 24 non-empty tiles from frame 1500 gameplay capture:

| Transform | Result |
|-----------|--------|
| Verbatim 32 bytes | 0/24 |
| Byte-pair swap (word endianness) | 0/24 |
| Bitmap nibble encoding (both orders) | 0/24 |
| All 24 plane permutations | 0/24 |
| H/V/HV flips | 0/24 |
| Half-tiles in DMA source regions | 0/24 |

*Note: This does not contradict v2.5.2's 65 partial matches—those were different
tiles from different captures. Match rates are scene-dependent.*

**Plane Usage Verification (Gameplay Captures):**

Analyzed 177 unique tiles across frames 1500-5250:

| Metric | Value |
|--------|-------|
| Tiles using all 4 planes | >90% |
| Tiles "planes 0+2 only" | 0/177 |
| Tiles with pixel values > 5 | 177/177 |

**Conclusion:** The "planes 0+2 only" observation was specific to menu/cutscene
captures. Gameplay sprites use full 4bpp with all planes active.

**OAM→VRAM Math Verified:**

```
vram_addr = tile_index * 32 + (tile_page * 0x2000)
```

All tiles in frame 1500 capture obey this formula with no exceptions.

**Revised Data Flow (Gameplay OBJ Tiles, Frame 1500):**

```
ROM (mix: HAL blocks + raw regions like 0x3CA000)
    ↓ (decompression/copy - unknown location)
    ↓ (transform - unknown, possibly runtime assembly)
WRAM 0x7E:2000 (final planar format)
    ↓ (plain SNES DMA, no conversion)
VRAM 0x4000+ (sprite tiles)
```

**Scope note:** The "0/24 transforms" result is for 24 tiles from frame 1500
gameplay capture. Earlier captures (v2.5.2) showed 65 tiles with strong ROM
matches. Match rates are scene-dependent, not universal.

**Open Question:** What code writes to WRAM 0x2000? This is the missing link.

**Documentation Updated:**
- SA1_HYPOTHESIS_FINDINGS.md: Added corrections section at top

---

## [2.5.2] - 2024-12-31

### Discovery: Byte-Swap Bug in Capture Script + Corrected Analysis

**Bug Found:** The Lua capture script was reading VRAM with byte-swapped order:
- Capture data: `FD 3E FD 3F FE 3F...`
- Actual VRAM:  `3E FD 3F FD 3F FE...`

All previous ROM searches used the incorrect byte order.

**Corrected Search Results:**

With correct byte order (from VRAM dump, not capture):
- VRAM 0x0020 → ROM 0x3CA5AB (16-byte match)
- VRAM 0x0040 → ROM 0x3CA5CB (16-byte match)

**But these are still false positives:**

| ROM Offset | HAL Decompress | First Tile | Matches VRAM? |
|------------|----------------|------------|---------------|
| 0x3CA5AB | 1,277 bytes (39 tiles) | All zeros | **No** |
| 0x3CA5CB | 23,289 bytes (727 tiles) | All zeros | **No** |

The VRAM tile bytes happen to coincide with valid HAL block headers, but the
decompressed content (zeros) doesn't match the actual VRAM sprite data.

**CORRECTION: Tiles Found in Raw ROM (Not HAL Compressed):**

After discovering the byte-swap bug, searched raw ROM with correct byte order:

| Metric | Value |
|--------|-------|
| VRAM tiles with planes 0+1 ROM match | **65** |
| Average byte match (32 bytes) | **25.8/32 (80.8%)** |
| High matches (≥28/32 bytes) | **35/65** |
| Perfect 32/32 matches | **1** (VRAM 0x0980 → ROM 0x3CAC03) |

**Key Finding:** Tiles exist as **raw uncompressed data** around ROM 0x3CA000,
NOT inside HAL blocks. The HAL decompressor was a red herring for these tiles.

**Remaining byte differences (planes 2+3 only):**

Example VRAM 0x0020 vs ROM 0x3CA5AB:
- Bytes 0-15 (planes 0+1): 16/16 exact match
- Bytes 16-19 (planes 2+3 row 0): `23 FF E0 26` → `FF FF FF FF`
- Bytes 20-31 (planes 2+3 rows 1-7): 12/12 exact match

The first row of planes 2+3 is modified at runtime (set to 0xFF).

**Next Step (per user guidance):** Stop reasoning from ROM matches.
Trace the actual DMA source buffer to localize where transformation occurs.

---

## [2.5.1] - 2024-12-31

### Observation: 0% Verbatim Match for Non-Trivial Sprite Tiles

**Confirmed Observation:** For capture frame 2000, **38/38 non-trivial VRAM tiles
have 0 verbatim matches** in:
- (a) Raw ROM scan (4MB)
- (b) Outputs produced by our current HAL decompressor pipeline

**Analysis of gameplay capture (frame 2000):**

| Category | Count | Result |
|----------|-------|--------|
| Total VRAM tiles | 52 | - |
| Trivial patterns (≤2 unique bytes) | 14 | False positive matches only |
| Non-trivial sprite tiles | 38 | **0% verbatim match** |

**False Positive Verification:**

Initial raw ROM search found 3 "matches" at:
- ROM $034D3F → Pattern: `01 01 01 01 01 01...` (trivial fill)
- ROM $034BBF → Pattern: `80 80 80 80 80 80...` (trivial fill)
- ROM $3CA5AB → Inside HAL compressed data stream (coincidental bytes)

All were trivial repeating patterns or coincidental byte sequences—NOT actual
sprite graphics.

**Falsified Hypothesis:**

Tested whether VRAM planes 2+3 = ROM planes 2+3 OR ROM planes 0+1:
- Result: **FAILS** on all test cases
- Byte differences: 14-16/16 bytes differ from prediction
- This specific simple OR mapping is not the transformation used

Note: This only rules out one specific mapping. Other possibilities remain:
- Different plane ordering or interleaving
- 2bpp ↔ 4bpp packing
- Per-row/per-tile shuffles, XOR, or masks
- Byte/bit endianness transforms

**Leading Hypotheses (Not Yet Proven):**

The final VRAM tiles are likely produced via one of:
1. **Runtime transformation** in WRAM/BW-RAM staging buffers
2. **Component assembly** from multiple smaller source pieces (metatiles)
3. **Different compression path** not covered by our current HAL decoder
4. **Format permutation** (bitplane swizzle, bit reversal, etc.) we haven't tested

**WRAM Staging Buffer Analysis:**

Searched WRAM staging buffers for ROM patterns:

| Buffer | Address | Content | ROM Match |
|--------|---------|---------|-----------|
| Kirby sprite staging | $7E:2000 | 87% non-zero, 188 unique values | Inside HAL compressed stream (false positive) |
| Sparkle staging | $7E:3400 | 79% non-zero, 27 unique values | None |
| Primary DMA staging | $7E:F382 | 99% non-zero, 223 unique values | None |

Note: This shows staging buffers don't match raw ROM, but does not prove where
the transformation occurs.

**Next Steps (Actionable):**

1. **Trace DMA source → VRAM** - Capture WRAM staging buffer at DMA trigger time
   and diff against VRAM. If they match, transformation is before staging.

2. **Test additional format permutations** - Bitplane swizzles, 2bpp modes, XOR masks

3. **Search for metatile tables** - Look for pointer tables that reference tile
   components to assemble into final sprites

**Path Forward for SpritePal:**

Current verbatim ROM-matching approach does not work for this capture. Options:

1. **Visual perceptual matching** - Image similarity against rendered screenshots
2. **Metatile reverse-engineering** - Find OAM assembly tables
3. **Test simpler games** - Games without SA-1 may use direct HAL → VRAM paths
4. **BG tile focus** - The 2.5% HAL matches were BG tiles, which may be extractable

---

## [2.5.0] - 2024-12-31

### Critical Finding: Runtime-Generated Sprite Tiles

**Problem:** Even with 188,920 unique tiles indexed from HAL blocks, only 2.5% of
gameplay VRAM tiles match. Sprite tiles are NOT stored directly in ROM.

**Evidence:**

| Metric | Value |
|--------|-------|
| Unique HAL tiles indexed | 188,920 |
| Non-empty VRAM tiles | 511 |
| Tiles matching HAL | 13 (2.5%) |
| Tiles NOT matching | 498 (97.5%) |

**Matched tiles** (mostly BG, not sprites):
- VRAM $04A0 → HAL $006800
- VRAM $0560 → HAL $370000
- VRAM $0740 → HAL $368000

**Unmatched tiles** (sprite data at low VRAM addresses):
- VRAM $0020-$00C0 contain sprite graphics
- None match any HAL block output
- None match raw ROM bytes either (searched 4MB)

**Root Cause Analysis:**

Kirby Super Star's sprite system is more complex than assumed:

1. **Component-based rendering** - Sprites may be assembled from smaller pieces
2. **Runtime palette manipulation** - SA-1 may modify tile data during transfer
3. **Animation compositing** - Multiple source tiles blended to create frames
4. **Dynamic effects** - Star/sparkle effects are procedurally generated

**Verified by exhaustive search:**
- Searched all HAL blocks (3,247 valid blocks)
- Searched raw ROM (4MB) for 32-byte patterns
- Best partial matches only 13-19/32 bytes (coincidental similarity)

**Implication:** Direct ROM → VRAM tile correlation is NOT possible for Kirby
Super Star sprites. Alternative approaches needed:
- Capture sprite component pieces before SA-1 processing
- Trace ROM read patterns during sprite decompression
- Use visual matching against rendered screenshots

---

## [2.4.0] - 2024-12-31

### Finding: Two-Plane 4bpp Tiles (All Graphics HAL-Compressed)

**Problem:** ROM tile matching showed 0% match rate despite 358K+ tiles indexed.

**Investigation:**
- Timing correlation works correctly (87% match rate: 181/208 tiles correlated)
- VRAM capture data matches VRAM dumps exactly (verified)
- SA-1 character conversion round-trip test passes
- BUT: ROM tiles after HAL+SA-1 conversion don't match VRAM tiles

**Verified Findings:**
Many captured VRAM tiles are 4bpp but effectively 2-plane (two bitplanes are all-zero).

Analysis (verified with comprehensive plane analysis):
- Bitplanes 0 and 2 contain data (even byte positions: 0,2,4,...,14,16,18,...,30)
- Bitplanes 1 and 3 are all-zero (odd byte positions: 1,3,5,...,15,17,19,...,31)

**Statistics from sprite_capture_1766968130.json:**
- 134 total tiles, 16 empty, 118 non-empty
- 116 tiles (98.3%) are two-plane tiles using planes 0+2
- Only 2 tiles use all 4 planes

**Raw ROM Pattern Search Results (FALSE POSITIVES):**
- Searched raw ROM for 16-byte patterns (planes 0+2 extracted from VRAM)
- Initial search found 18 of 116 tiles (15.5%) with byte-sequence matches
- **CRITICAL:** All 18 "matches" were FALSE POSITIVES - coincidental byte sequences within HAL-compressed blocks

**Verification of False Positives:**
| Pattern Offset | HAL Block Start | Decompressed Size | Verdict |
|----------------|-----------------|-------------------|---------|
| $3A7F2D | $3A7B2D | 22,108 bytes | Inside compressed data |
| $3A8410 | $3A7D10 | 21,364 bytes | Inside compressed data |
| $3A7E08 | $3A7C08 | 21,689 bytes | Inside compressed data |
| $209255 | $208E55 | 2,784 bytes | Inside compressed data |
| $15691A | $15521A | 12,968 bytes | Inside compressed data |

**Conclusion:** Kirby Super Star uses 100% HAL-compressed graphics. There are NO
uncompressed sprite assets in the ROM. Raw byte pattern searches will always
produce false positives (coincidental matches within compressed streams).

**Technical Note:**
Planes 0+2 being used implies pixels only use palette indices where bits 1 and 3
are zero (i.e., values 0, 1, 4, 5 - the low 2 bits of the 4-bit palette index).
This suggests these sprites use a 4-color subset of the 16-color sprite palette.

### ROM Scanner Improvements
- [x] Added `scan_rom_for_blocks()` method to ROMTileMatcher
- [x] Comprehensive ROM scan: 3,011 HAL blocks, 703K+ tiles
- [x] Updated CLI with `--scan-rom`, `--scan-step`, `--scan-min-tiles` flags
- [x] Created `scripts/discover_rom_offsets.py` for ROM exploration

### Two-Plane Tooling (Completed)
- [x] Implemented flexible two-plane extraction for all 6 plane combinations
- [x] Added `analyze_tile_planes()` for per-tile plane analysis
- [x] Built two-plane ROM index (raw 16-byte patterns at every offset)
- [x] Verified 98.3% of VRAM tiles use planes 0+2

### Key Finding: Capture Timing Critical

**Problem:** 0% ROM match rate across all captures despite comprehensive scanning.

**Root Cause:** All existing captures were from menu/cutscene screens (frames 199-6227),
NOT actual gameplay. Menu graphics (fonts, UI) are stored differently:
- Possibly uncompressed in ROM
- In different HAL blocks than sprite data at $1B0000
- May use BG layers instead of OBJ sprites

**Evidence:**
- HAL-decompressed ROM tiles have all 4 planes populated (verified)
- Menu/cutscene VRAM tiles only use planes 0+2 (98.3% of captured tiles)
- Gameplay VRAM tiles use ALL 4 planes (verified at frame 2000)

### Unified Capture Workflow (Implemented)

**Solution:** Integrated periodic sprite capture into `mesen2_dma_probe.lua`:

| Environment Variable | Default | Purpose |
|---------------------|---------|---------|
| `PERIODIC_CAPTURE_ENABLED` | 0 | Set to "1" to enable |
| `PERIODIC_CAPTURE_START` | 2000 | Frame to start captures |
| `PERIODIC_CAPTURE_INTERVAL` | 1800 | Frames between captures (30s @ 60fps) |

**Single batch file workflow:** `run_sa1_hypothesis.bat` now captures both:
1. DMA events (`dma_probe_log.txt`) for timing correlation
2. Periodic sprite snapshots (`test_capture_gameplay_*.json`) for ROM matching

**Gameplay Capture Results (frame 2000):**
- 44 visible sprites captured
- Tile data uses ALL 4 bitplanes (unlike menu captures)
- Example tile: `FD3EFD3FFE3FFE3F...` (non-zero odd bytes = planes 1+3 active)
- Kirby with Cutter ability, Waddle Doo enemy, Spring Breeze level

**Next Steps:**
- [ ] Run ROM correlation with gameplay captures
- [ ] Verify match rate improvement with full 4-plane tiles
- [ ] If successful, document the menu vs gameplay graphics difference

---

## [2.3.0] - 2024-12-31

### Address Space Bridge
- [x] Created core/mesen_integration/address_space_bridge.py
- [x] Normalizes SA-1 and S-CPU bus addresses to canonical form
- [x] Handles WRAM ($7E/$7F), I-RAM, BW-RAM, ROM address spaces
- [x] CanonicalAddress dataclass with region + offset
- [x] BankRegisters parser for SA1_BANKS log lines
- [x] CanonicalRange for tracking DMA transfer ranges

### Timing Correlator Engine
- [x] Created core/mesen_integration/timing_correlator.py
- [x] Two-stage correlation: VRAM tiles → DMA events → staging buffers
- [x] TimingCorrelator class with load_dma_log() and load_capture()
- [x] TileCorrelation dataclass linking tiles to DMA events
- [x] CorrelationResults with match statistics and staging summaries
- [x] format_correlation_report() for human-readable output
- [x] generate_correlation_json() for machine-readable output

### CLI Tooling
- [x] Created scripts/run_timing_correlation.py
- [x] Unified interface for running timing correlation
- [x] Supports glob patterns for multiple captures
- [x] JSON and text output modes

### ROM Tile Matcher with SA-1 Conversion
- [x] Created core/mesen_integration/rom_tile_matcher.py
- [x] Applies SA-1 character conversion (bitmap → SNES 4bpp) during indexing
- [x] Bridges format gap between ROM and VRAM captures
- [x] Indexes flipped tile variants (H, V, HV) for better matching
- [x] Database save/load for persistent caching

### Full Correlation Pipeline
- [x] Created core/mesen_integration/full_correlation_pipeline.py
- [x] Unified pipeline: VRAM → DMA → staging → ROM
- [x] CorrelationPipeline class combines TimingCorrelator + ROMTileMatcher
- [x] Tracks staging buffer → ROM offset mappings
- [x] Created scripts/run_full_correlation.py CLI

---

## [2.2.0] - 2024-12-31

### Critical Finding: Mesen2 Lua API Limitation
- [x] **BLOCKED:** SA-1 CPU write callbacks cannot intercept SA-1 register writes
- [x] Verified via Mesen2 source code: $2230 (DCNT) only written by SA-1 CPU
- [x] DCNT polling at frame end fails: DMA completes within cycles (DCNT=0)
- [x] CharConvIrqFlag ($2300 bit 5) only set when DmaCharConvAuto=true

### WRAM Staging Pattern Discovery
- [x] Captured 34,329 SNES_DMA_VRAM events
- [x] 98.7% of DMA transfers source from WRAM ($7E bank)
- [x] Primary staging buffer: $7E:F382 (94.7% of WRAM transfers)
- [x] Game uses WRAM staging, NOT I-RAM ($00:3000-$37FF)
- [x] Created scripts/analyze_snes_dma_staging.py for staging analysis

### Pivot Strategy: SNES DMA Correlation
- [x] Pivoted from CCDMA_START to SNES_DMA_VRAM correlation
- [x] New correlation path: ROM → SA-1 CCDMA → WRAM → SNES DMA → VRAM
- [x] Track staging buffer addresses for sprite data flow

### VRAM Region Analysis
- [x] Enhanced scripts/analyze_snes_dma_staging.py with 2KB region bucketing
- [x] Classify "hot" vs "stable" regions by update frequency
- [x] Source-to-region mapping (which staging buffers feed which VRAM regions)

### SA-1 Character Conversion Algorithm
- [x] Created core/mesen_integration/sa1_character_conversion.py
- [x] bitmap_to_snes_4bpp() - forward conversion for ROM matching
- [x] snes_4bpp_to_bitmap() - reverse conversion for ROM search
- [x] Round-trip verified with random data tests

### OAM ↔ DMA Cross-Reference
- [x] Created scripts/cross_reference_oam_dma.py
- [x] Links sprite tiles to DMA transfers that populated their VRAM
- [x] 92.6% match rate across 14 captures (1,485 of 1,603 tiles)
- [x] Primary staging buffer: $7E:F382 (61% of matched tiles)

---

## [2.1.0] - 2024-12-31

### Phase 0: Instrumentation Contract v1.1
- [x] Added LOG_VERSION and RUN_ID to mesen2_dma_probe.lua
- [x] Added collision-resistant RUN_ID format (timestamp + random hex suffix)
- [x] Added `get_canonical_frame()` function for consistent frame tracking
- [x] Log header written on first log() call with ROM info
- [x] Added SA-1 bank register logging ($2220-$2225) at startup + on change
- [x] Created scripts/validate_log_format.py for contract validation

### Phase 1: CCDMA Start Trigger + Enhanced Logging
- [x] Added CCDMA_START log line with C-bit rising edge detection
- [x] SS (Source Select) field for routing: 0=ROM, 1=BW-RAM, 2=I-RAM
- [x] Enhanced SNES_DMA_VRAM log line with frame, run, dmap, vmadd fields
- [x] Created scripts/analyze_ccdma_sources.py for SS histogram analysis

### New Log Formats (Instrumentation Contract v1.1)

**Log Header:**
```
# LOG_VERSION=1.1 RUN_ID=1735678900_a3f2 ROM=Kirby Super Star (USA) SHA256=N/A PRG_SIZE=0x100000
```

**SA1_BANKS:**
```
SA1_BANKS (init): frame=0 run=123_a3f2 cxb=0x00 dxb=0x01 exb=0x02 fxb=0x03 bmaps=0x00 bmap=0x00
```

**CCDMA_START:**
```
CCDMA_START: frame=100 run=123_a3f2 dcnt=0xA0 cdma=0x03 ss=0 (ROM) dest_dev=0 (I-RAM) src=0x3C8000 dest=0x003000 size=0x0800
```

**SNES_DMA_VRAM:**
```
SNES_DMA_VRAM: frame=100 run=123_a3f2 ch=1 dmap=0x01 src=0x3000 src_bank=0x00 size=0x0800 vmadd=0x6000
```

---

## [2.0.0] - 2024-12-31

### Phase 1: SA-1 Hypothesis Verification (COMPLETE - CONFIRMED)
- [x] Created sa1_conversion_logger.lua for focused DCNT/CDMA monitoring
- [x] Created run_sa1_logger.bat for easy execution (testrunner mode)
- [x] Created run_sa1_hypothesis.bat for movie playback mode (alternative approach)
- [x] Created scripts/analyze_sa1_hypothesis.py to parse dma_probe_log.txt output
- [x] Created SA1_HYPOTHESIS_FINDINGS.md template for documenting results
- [x] Fixed SA1_HYPOTHESIS_FINDINGS.md to reference DCNT bit 5 (not CDMA bit 7)
- [x] Captured 838 SA-1 DMA samples via movie playback
- [x] **HYPOTHESIS CONFIRMED:** 100% of SA-1 DMA operations use character conversion (ctrl=0xA0)

### Phase 2: Dangerous Assumption Fixes
- [x] Added prg_size fail-fast validation to test_sprite_capture.lua
- [x] Added prg_size fail-fast validation to gameplay_capture.lua
- [x] Fixed VMAIN remap formulas to match SNESdev canonical definitions
- [x] Added worked example for Mode 01 remapping
- [x] Added WRAM staging warning to 04_TROUBLESHOOTING.md
- [x] Added Success Criteria (Provisional) table
- [x] Added Timing Correlation Failure Modes table

### Phase 3: Schema Migration
- [x] Created migrate_v1_to_v2.py (in-place migration script)
- [x] Created validate_schema.py (schema validation tool)
- [x] Documented field renames in 02_DATA_CONTRACTS.md:
  - oam_base_addr → obj_tile_base_word
  - oam_addr_offset → obj_tile_offset_word
  - confidence → observation_count
- [x] Fixed 128KB VRAM claim in 00_STABLE_SNES_FACTS.md (now documented as undefined behavior)

### Phase 4: Documentation Improvements
- [x] Documented tile hash byte order in 02_DATA_CONTRACTS.md
- [x] Added golden test ROM SHA256 to 03_GAME_MAPPING_KIRBY_SA1.md
- [x] Updated schema version table in 02_DATA_CONTRACTS.md to include v2.0

---

## [1.0.0] - 2024-12-31 (Initial documented state)

### Documentation Created
- 00_STABLE_SNES_FACTS.md - SNES hardware reference
- 01_BUILD_SPECIFIC_CONTRACT.md - Mesen2 API behavior
- 02_DATA_CONTRACTS.md - JSON schemas (v1.0)
- 03_GAME_MAPPING_KIRBY_SA1.md - Kirby Super Star mapping
- 04_TROUBLESHOOTING.md - Diagnostic guide

### Known Issues (addressed in 2.0.0)
- SA-1 character conversion hypothesis unverified → Infrastructure created
- Byte-swap behavior documented but not root-caused → verify_endianness.lua exists
- VMAIN formulas use imprecise "rotate" terminology → Fixed with SNESdev formulas
- Schema uses ambiguous oam_* naming for VRAM addresses → Field renames documented
- 128KB VRAM claim is speculation → Corrected as undefined behavior
