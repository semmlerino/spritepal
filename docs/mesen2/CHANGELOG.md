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

## [2.25.0] - 2026-01-03

### Critical Bug Fix: Decouple Ablation from BUFFER_WRITE_WATCH

**The Bug:**

PRG ablation callbacks (S-CPU and SA-1 read callbacks + exec guards) were nested
inside `register_buffer_write_callbacks()`, which has an early return when
`BUFFER_WRITE_WATCH_ENABLED=0`. This meant:

1. Setting `BUFFER_WRITE_WATCH=0` silently disabled ALL PRG ablation
2. An "ablation run" would have no actual corruption
3. "No flips" would be falsely concluded

The batch file had a workaround comment (`REM Keep BUFFER_WRITE_WATCH=1 to enable
PRG callback registration for ablation`), but the structural coupling was a landmine.

**The Fix:**

1. Created `register_prg_callbacks()` - shared helper that registers S-CPU and SA-1
   PRG read callbacks. Idempotent (only registers once via `prg_callbacks_registered` flag).

2. Created `register_ablation_callbacks()` - independent function that:
   - Registers PRG callbacks via `register_prg_callbacks()`
   - Registers exec guards (S-CPU and SA-1) when ABLATION_ENABLED=1
   - Runs **before** buffer write registration in lazy registration block
   - Works regardless of BUFFER_WRITE_WATCH setting

3. Simplified `register_buffer_write_callbacks()` - now only registers buffer write
   watch, then calls `register_prg_callbacks()` for fill session tracking (no-op if
   already registered by ablation).

**Result:** `ABLATION_ENABLED=1` now guarantees PRG ablation is active, even with
`BUFFER_WRITE_WATCH=0`. The batch file workaround is no longer required.

---

## [2.24.0] - 2026-01-03

### Per-CPU Ablation Toggles and SNES Exec Guard

**Features:**

1. **Per-CPU toggles** for isolating causality:
   - `ABLATE_SNES=0/1` - Enable/disable S-CPU ablation (default: 1)
   - `ABLATE_SA1=0/1` - Enable/disable SA-1 ablation (default: 1)
   - Allows testing S-CPU-only or SA-1-only causality paths

2. **SNES exec guard** - Mirrors the SA-1 exec guard to prevent S-CPU code fetch corruption
   from ablation range. Both CPUs now protected from instruction fetch corruption.

3. **Fixed ABLATION_CONFIG label** - Now accurately shows per-CPU modes:
   ```
   ABLATION_CONFIG: enabled=true range=0xE80000-0xE8FFFF value=0xFF (v2.24: S-CPU=exec-guard SA-1=exec-guard)
   ```

4. **Consolidated exec guard variables** into table to stay under Lua's 200 local variable limit.

**Bank EB Ablation Results:**

Tested Bank EB (0xEB0000-0xEBFFFF) as bisection of Quarter 2.2.

**Result: NO payload_hash flips** - All 4 hashes match baseline exactly.

| Frame | VRAM | Baseline Hash | Bank EB Hash | Match? |
|-------|------|---------------|--------------|--------|
| 1681 | 0x58E0 | 0x92FB2C49 | 0x92FB2C49 | YES |
| 1684 | 0x4C00 | 0x8CE8AD0F | 0x8CE8AD0F | YES |
| 1760 | 0x4F20 | 0xD5D9BC35 | 0xD5D9BC35 | YES |
| 1769 | 0x4F40 | 0x8CB81E85 | 0x8CB81E85 | YES |

**Key Finding:** Despite SA1_BURST showing reads from 0xEBBxxx being ablated, Bank EB
is NOT the causal sub-region for these 4 DMAs. The causal bytes must be in Banks E8, E9, or EA.

**Implication:** The 0xEBBxxx reads may be metadata/pointers rather than actual tile data.
The decompressor or tile source is elsewhere in Quarter 2.2.

**Next step:** Test Bank E8 (0xE80000-0xE8FFFF) - earlier evidence pointed to 0xE894F4.

---

## [2.23.1] - 2026-01-03

### Quarter 2.2 Ablation Results - Causal PRG Region Confirmed

**Experiment:** PRG ablation of 0xE80000-0xEBFFFF (Quarter 2.2, 256KB) with v2.23 script.

**Results:** 4 payload_hash flips confirmed at frames 1681, 1684, 1760, 1769.

| Frame | VRAM | Baseline Hash | Ablation Hash | Ablated Count |
|-------|------|---------------|---------------|---------------|
| 1681 | 0x58E0 | 0x92FB2C49 | 0x4B32FA70 | snes=1,sa1=0 |
| 1684 | 0x4C00 | 0x8CE8AD0F | 0xFE30E5F5 | 0 (upstream!) |
| 1760 | 0x4F20 | 0xD5D9BC35 | 0x4721F51B | 0 (upstream!) |
| 1769 | 0x4F40 | 0x8CB81E85 | 0xFE00576B | 0 (upstream!) |

**Key Observations:**

1. **Upstream timing proven**: 3 of 4 flips show `ablated=0` at DMA time, meaning the causal
   PRG read happened BEFORE the staging_active window opened. The corrupted data sat in WRAM
   until the DMA transferred it to VRAM.

2. **SA-1 as upstream producer**: SA1_BURST entries show reads from 0xEBB5xx-0xEBB8xx range.
   These reads occur 29-88 frames before the staging DMAs that show hash flips.

3. **Interesting non-causal case**: Frame 1760's other DMA (vram=0x4B20) shows `ablated=18(sa1=18)`
   but NO hash change - proving those 18 reads happened but weren't causal for that payload.

**SA1_BURST Sample:**
```
SA1_BURST: frame=1593 count=3 ablated=3 exec_blocked=0 range=0xEBB641-0xEBB831
SA1_BURST: frame=1722 count=3 ablated=3 exec_blocked=0 range=0xEBB5FC-0xEBB7EC
```

**Conclusion:** Quarter 2.2 (0xE80000-0xEBFFFF) is a **proven causal PRG region** for sprite
staging DMAs. The SA-1 reads from 0xEBBxxx as an upstream producer. Next step: bisect to
Bank EB (0xEB0000-0xEBFFFF) to narrow from 256KB to 64KB.

---

## [2.23.0] - 2026-01-03

### Fix emu.stop() Re-entry Bug (v2.23)

**Problem:** During ablation runs, the script would "freeze" after reaching MAX_FRAMES.
Analysis showed "Reached MAX_FRAMES; stopping" logged 1266 times - `emu.stop()` was called
repeatedly but didn't immediately halt the emulator's frame callbacks.

**Symptoms:**
- Run exceeds MAX_FRAMES (e.g., 3765 frames when MAX_FRAMES=2500)
- Log shows repeated "Reached MAX_FRAMES; stopping" messages
- Script never terminates until manually closed

**Root Cause:** `emu.stop()` doesn't immediately halt Lua callback execution in Mesen2.
The frame callback continues to be invoked until the emulator fully stops.

**Solution:** Add `script_stopping` guard flag to prevent callback re-entry.

**Implementation:**
```lua
local script_stopping = false  -- New guard flag

local function on_end_frame()
    -- Early exit if already stopping
    if script_stopping then
        return
    end

    -- ... normal frame processing ...

    if frame_count >= MAX_FRAMES then
        log("Reached MAX_FRAMES; stopping")
        script_stopping = true  -- Set flag BEFORE emu.stop()
        emu.stop()
        return
    end
end
```

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.22 → v2.23)
- `run_prg_ablation_sweep.bat` (version update)

---

## [2.22.0] - 2026-01-03

### SA-1 PRG Ablation Ungated (v2.22)

**Context:** v2.21 added SA-1 PRG read logging and ablation, but with the same
`staging_active` gate as S-CPU. Analysis showed SA-1 reads from ablation range
with `ablated=0` because staging wasn't active when SA-1 read.

**Key Insight:** If SA-1 is an upstream producer (decompression), it reads ROM
BEFORE staging_active is set. Gating SA-1 ablation to staging is "too late."

**Changes:**
1. Removed `staging_active` gate from SA-1 ablation (kept exec guard only)
2. Added SA-1 burst tracking per-frame for correlation with staging DMAs
3. Added `SA1_BURST` logging at frame end

**New Log Format:**
```
SA1_BURST: frame=1500 count=42 ablated=38 exec_blocked=4 range=0xE80000-0xE8FFFF
```

**Ablation Logic Comparison:**
| CPU | Staging Gate | Exec Guard | Rationale |
|-----|--------------|------------|-----------|
| S-CPU | Yes | No | Downstream consumer - only ablate during staging |
| SA-1 | **No** | Yes | Upstream producer - ablate unconditionally |

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.21 → v2.22)
- `run_prg_ablation_sweep.bat` (version update)

---

## [2.21.0] - 2026-01-03

### SA-1 PRG Read Logging and Ablation (v2.21)

**Context:** v2.20 per-DMA ablation showed no payload_hash flips in Quarter 2.2
(0xE80000-0xEBFFFF) despite this being the suspected causal range. The freeze at
frame 1595 suggested SA-1 code fetch was being ablated.

**Hypothesis:** SA-1 is upstream producer, reading PRG before S-CPU staging begins.
Need to track SA-1 PRG reads separately from S-CPU.

**New Features:**
1. **SA-1 exec guard**: Tracks when SA-1 executes from ablation range
2. **SA-1 PRG read callback**: Logs and optionally ablates SA-1 reads
3. **Separate counters**: `ablation_total_sa1` distinct from S-CPU counter
4. **Updated STAGING_SUMMARY**: Shows both `ablated=N` (S-CPU+SA-1) and `sa1=M`

**New Log Format:**
```
STAGING_SUMMARY: ... ablated=42 sa1=38
```

**Safety:** SA-1 exec guard prevents ablating reads that are code fetch,
which would cause useless freezes.

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.20 → v2.21)
- `run_prg_ablation_sweep.bat` (version update)

---

## [2.20.0] - 2026-01-03

### Payload Hash: Deterministic Output Signal for PRG Ablation (v2.19)

**Context:** Step A (STAGING_WRAM_PREARM) confirmed 0x1530-0x161A is NOT the staging source for VRAM DMAs.
All staging DMAs show NO_WRAM_PAIRS, meaning staging doesn't read from any watched WRAM range.
This proves the earlier "gold causal ROM → 0x1530" result is NOT connected to "tiles that reached VRAM."

**Pivot:** Instead of WRAM sweep (wasted motion), we now ablate PRG (ROM) directly and measure
whether the actual DMA payload bytes change.

**New Features:**
- `compute_dma_payload_hash(src_addr, size)` - djb2 hash of DMA payload bytes at staging → VRAM transfer
- `payload_hash=0x%08X` field added to STAGING_SUMMARY log line
- Handles both WRAM addressing modes (relative via MEM.wram, absolute via MEM.cpu)

**New Output:**
```
STAGING_SUMMARY: frame=1500 src=0x7E2000 size=256 payload_hash=0xABCD1234 vram=0x4000 ...
```

**Binary Search Protocol:**
1. Run baseline (ABLATION_ENABLED=0), record payload_hash for target DMA
2. Ablate PRG chunks: 0xC00000-0xCFFFFF, 0xD00000-0xDFFFFF, 0xE00000-0xEFFFFF, 0xF00000-0xFFFFFF
3. Interpretation:
   - Corrupted reads = 0 → that PRG chunk isn't touched for this DMA
   - Corrupted reads > 0 but payload_hash unchanged → touched but not causal
   - payload_hash changes → found causal PRG region feeding exact bytes to VRAM

**Noise Reduction for Step B:**
Disable 0x1530 buffer-specific features that are now distractions:
```batch
BUFFER_WRITE_WATCH=0
READ_COVERAGE_ENABLED=0
STAGING_WRAM_SOURCE=0   (optional, NO_WRAM_PAIRS is already proven)
DMA_COMPARE_ENABLED=0   (optional, for performance)
```

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.18 → v2.19)

### PRG Callback Address Format Fix (v2.19 hotfix)

**Bug:** `corrupted_reads=0` despite ablation range matching prg_runs entries.

**Root Cause:** PRG read callback receives **CPU addresses** (0xC00000+), not file offsets.
Evidence: `prg_runs` logs values like `0xC469F6`, `0xED04FE` which exceed 4MB file offset max (0x3FFFFF).

The original code converted `ABLATION_PRG_START/END` from CPU addresses to file offsets,
but the callback address was never converted, so the comparison always failed.

**Fix:** Remove the CPU→file conversion. Use CPU addresses directly for ablation comparison.

**Before (broken):**
```lua
-- WRONG: Converted ablation range to file offsets
if ABLATION_PRG_START >= 0xC00000 then
    ABLATION_PRG_START = ABLATION_PRG_START - 0xC00000
end
-- Callback receives 0xED04FE (CPU), we compare against 0x2D04FE (file) → no match
```

**After (fixed):**
```lua
-- CORRECT: Keep ablation range as CPU addresses (callback provides CPU addresses)
local ABLATION_PRG_START = ABLATION_PRG_START_RAW  -- No conversion
-- Callback receives 0xED04FE (CPU), we compare against 0xED04FE (CPU) → match!
```

**Verification:** After fix, `ABLATION_CONFIG` log shows:
```
ABLATION_CONFIG: enabled=true range=0xEC0000-0xEFFFFF value=0xFF (CPU addresses, no conversion)
```

### Per-DMA Ablation Tracking (v2.20)

**Problem:** The existing `corrupted_reads` counter was session-scoped (POPULATE episode),
not DMA-scoped. This made it impossible to determine if ablated reads were causally
related to a specific staging DMA's payload_hash.

Example of misleading signal:
```
ABLATION_RESULT: frame=1673 corrupted_reads=3756  # Session total, not per-DMA
STAGING_SUMMARY: frame=1495 payload_hash=0xA5E44A02  # Which reads fed THIS?
```

**Solution:** Add per-staging-DMA ablation delta tracking.

**New globals:**
```lua
local ablation_total = 0           -- Increments on every corrupted read
local ablation_last_at_staging = 0 -- Snapshot at each STAGING_SUMMARY
```

**New STAGING_SUMMARY field:**
```
STAGING_SUMMARY: ... payload_hash=0xABCD1234 ... ablated=42
```

Where `ablated=N` is the count of corrupted PRG reads since the previous STAGING_SUMMARY.
This directly answers: "Were any ablated reads involved in producing THIS payload?"

**Interpretation:**
- `ablated=0` + hash unchanged → ablation range not touched for this DMA
- `ablated>0` + hash unchanged → touched but non-causal (pointers, code fetch)
- `ablated>0` + hash changed → **causal PRG region for staging→VRAM**

**Two data paths identified:**
1. **Direct ROM→VRAM** (Bank ED/EE → VRAM 0x6000+): BG tiles, no staging buffer
2. **Staging→VRAM** (Bank C → 0x7E2000 → VRAM 0x4000+): Sprite tiles

Filter for sprite causality testing:
```bash
grep "STAGING_SUMMARY.*vram=0x4\|STAGING_SUMMARY.*vram=0x5" dma_probe_log.txt
```

---

## [2.19.0] - 2026-01-02

### READ_COVERAGE: Distinguish "Not Written" from "Not Used" (v2.18)

**Context:** v2.17 multi-session chaining showed 14.5% write coverage (34/235 bytes).
The question: does staging only USE those 34 bytes, or does it READ all 235 bytes
(some pre-filled from an earlier phase)?

Key insight: **"not written" ≠ "not used"**

**Solution:** Track READS from the source buffer (0x1530-0x161A) during staging sessions.
This shows exactly which bytes staging consumes, regardless of when they were written.

**New Features:**
- `READ_COVERAGE_ENABLED=1` - Track reads from source buffer (default: true)
- Per-offset read bitmap: tracks exactly which bytes are read at least once
- Per-tile read stats: `T0:32,T1:28,...` format (same as write coverage)

**New Output:**
```
READ_COVERAGE: bytes_read=N/235 (X.X%) bytes_written=M (Y.Y%) tiles_read=[T0:32,T1:28,...]
READ_COVERAGE_INSIGHT: <interpretation based on read vs write comparison>
```

**Interpretation:**
- **read > written**: Staging reads bytes we didn't observe being filled → earlier phase exists
- **read < written**: Staging only uses subset of what was written → some writes unused here
- **read == written**: Clean 1:1 mapping between fill and use

**Requirement:** `STAGING_WRAM_SOURCE=1` must be enabled (already set in run_ablation_test.bat)

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.17 → v2.18)

---

## [2.18.0] - 2026-01-02

### Multi-Session Chaining for Full Buffer Coverage (v2.17)

**Context:** v2.16 ablation tests showed only 14.5% coverage (34 of 235 bytes) because
we were capturing only ONE phase of a multi-phase population. The proven causal range
only affected 4 output bytes, consistent with partial capture.

**New Features:**
- **Session chaining**: After a session ends, continue watching for more tile-data writes
- **Cumulative tracking**: `cumulative_bytes` counts unique offsets across ALL sessions
- **Stability detection**: Episode marked complete after `POPULATE_STABLE_FRAMES` (default 60)
  frames with no new writes
- **Session numbering**: Each burst gets a session number (1, 2, 3...)

**New Config:**
- `POPULATE_CHAIN_ENABLED=1` - Enable multi-session chaining (default: true)
- `POPULATE_STABLE_FRAMES=60` - Frames of stability before marking episode complete

**New Output:**
- `POPULATE_SESSION_START: session=N ...` - Now includes session number and cumulative count
- `POPULATE_COVERAGE: session=N ... session_bytes=X cumulative_bytes=Y coverage=Z%`
- `POPULATE_EPISODE_COMPLETE: frame=N sessions=M cumulative_bytes=X coverage=Y%`

**Ablation Value Options:**
- `ABLATION_VALUE=0x00` - Zero (default, may preserve semantics)
- `ABLATION_VALUE=0xFF` - All ones (more disruptive, recommended for retests)
- `ABLATION_VALUE=0xAA` - Alternating bits

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.16 → v2.17)
- `run_ablation_test.bat` (v2.16 → v2.17)

---

## [2.17.0] - 2026-01-02

### Coverage Metric and Tile-Level Reporting (v2.16)

**Context:** v2.15 ablation proved ROM causality (corrupting ROM 0xE894F4-0xE89551 changes
output hash). Now we need:
1. Coverage tracking: how many of 235 bytes are observed written vs sensitive to ablation
2. Tile-level attribution: which 32-byte tiles are affected by each ROM range

**New Features:**
- `POPULATE_COVERAGE` log line: reports bytes_written, coverage%, and tile breakdown
- Tiles identified by index (32 bytes per tile, 8 tiles in 235-byte buffer)
- Tile format: `T0:32,T1:28,...` means tile 0 has 32 bytes written, tile 1 has 28, etc.

**New Script:** `scripts/compare_ablation_runs.py`
- Compares baseline vs ablation log files
- Reports which output bytes changed
- Groups changes by tile index with byte_in_tile offset
- Usage: `python scripts/compare_ablation_runs.py baseline.txt ablation.txt`

**Ablation Test Results (all 3 candidates tested):**

| Test | PRG Range | Reads Corrupted | Hash | Result |
|------|-----------|-----------------|------|--------|
| 1 | `$E8:94F4-$E8:9551` | 141 | `0x05077D05`→`0x2A200899` | **PROVEN CAUSAL** |
| 2 | `$EB:C2BB-$EB:C2E7` | 68 | unchanged | NOT causal |
| 3 | `$E8:95AD-$E8:95F5` | 110 | unchanged | NOT causal |

**Interpretation:**
- We have one **proven causal** ROM input range (`$E8:94F4-$E8:9551`)
- Two other read ranges did not affect output under current session boundaries and
  ablation method — this does NOT prove they are "not causal, period"
- Possible reasons for NO EFFECT: incidental reads (headers/tables), 0x00 corruption
  preserving semantics, or those ranges feed a different population phase

**Coverage observation:** All tests show 14.5% coverage (34 of 235 bytes written).
This strongly suggests we're capturing only ONE phase of a multi-phase population.
The 4 changed bytes from Test 1 align with this partial coverage

**Correct wording for v2.15 result (per user guidance):**
> "Ablation test proves that reads from PRG $E8:94F4–$E8:9551 (ROM file offset
> 0x2894F4–0x289551) are a causal input to the sprite tile source buffer
> (0x1530–0x161A). Corrupting 141 reads in that range changes the buffer output
> hash from 0x05077D05 to 0x2A200899 and alters output bytes at offsets 0x4B,
> 0x4C, 0x8D, 0x8E."

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.15 → v2.16)
- `run_ablation_test.bat` (v2.15 → v2.16, added candidate list)
- `scripts/compare_ablation_runs.py` (new)

---

## [2.16.0] - 2026-01-02

### Cold-Start Detector and Populate Session (v2.11)

**Context:** v2.10 buffer capture showed only 12 bytes written per-frame (metadata at
0x157B-0x15BE), not the 235 bytes of tile data. The tile data must be populated
EARLIER (during loading), not per-frame.

**Solution:** Cold-start detection - hash the buffer every N frames, trigger bounded
PRG logging only when the actual tile data changes (not metadata churn).

**New Features:**
- `POPULATE_ENABLED=1` - Enable cold-start detection
- `POPULATE_HASH_INTERVAL=100` - Check buffer hash every N frames
- `POPULATE_MIN_CHANGE_BYTES=32` - Minimum bytes changed to trigger session
- `POPULATE_EXCLUDE_START/END` - Exclude metadata range from triggering
- Hash-based change detection (DJB2-style, excludes metadata range)
- Bounded populate session with PRG read logging
- Buffer dump at session end for ROM comparison

**Output:**
- `POPULATE_INIT` - Initial buffer hash captured
- `POPULATE_CHANGE` - Buffer content changed (logs byte count)
- `POPULATE_SESSION_START` - Populate session triggered
- `POPULATE_SESSION` - Summary with PRG runs and write PCs
- `POPULATE_BUFFER_DUMP` - Final 235-byte hex dump

**Key Insight:** The 12 bytes at 0x157B-0x15BE are pointers/metadata, not tile data.
The actual tile data (235 bytes at 0x1530-0x161A) is populated during level loading,
not per-frame.

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.10 → v2.11)
- `run_populate_trace.bat` (new - cold-start detection script)

**Usage:**
1. Run `run_populate_trace.bat` (traces from frame 0)
2. Look for `POPULATE_SESSION` entries
3. Check `prg_runs` for ROM source candidates
4. Use `POPULATE_BUFFER_DUMP` hex to search in ROM

---

## [2.15.0] - 2026-01-02

### Buffer Byte Capture for Content Validation (v2.10)

**Context:** FILL_SESSION shows PRG runs during buffer fill, but "big PRG runs" alone
can be coincidence. Need content validation to prove the linkage.

**New Feature:**
- Captures actual bytes written to source buffer (0x1530-0x161A) during each fill session
- Dumps bytes as hex string at session end: `FILL_BUFFER_BYTES`
- Enables direct comparison: ROM bytes at PRG addresses vs buffer bytes

**Output:** `FILL_BUFFER_BYTES: frame=X addr_range=0xAAAA-0xBBBB bytes=N hex=...`

**What this enables:**
- If bytes match ROM → direct copy loop, ROM offset confirmed
- If bytes don't match → decompression/transformation, PRG run is compressed source

**Files Changed:**
- `mesen2_integration/lua_scripts/mesen2_dma_probe.lua` (v2.9 → v2.10)

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
