# 04 Troubleshooting

This is a fail-fast diagnostic flow. **Do not expand the tile DB or relax filters** until
VRAM capture integrity is verified.

---

## Lua Script Timeout (Common Issue)

**Symptom:** `Maximum execution time (1 seconds) exceeded` error, script dies before frame 1.

**Cause:** Mesen2's Lua timeout is cumulative across all callback execution. Heavy callback
activity (DMA logging, staging watch registration) can exceed the 1-second default budget.

**Fix:**

1. **Increase ScriptTimeout in Mesen2:**
   ```
   Tools -> Script Window -> Settings -> Script Timeout -> 5 (or higher)
   ```

2. **Use v2.3+ of mesen2_dma_probe.lua** which defers heavy operations:
   - Lazy registration: Staging callbacks register at frame 1498, not init
   - Deferred logging: DMA/HDMA/SA1 logs start at frame 1490, not frame 0

**Verification:** After increasing timeout, log should show:
```
INFO: Staging watch will be registered lazily at frame=1498
INFO: DMA/HDMA/SA1 logging deferred until frame=1490
```

**Mesen2 Source Reference:** `ScriptingContext.cpp:128-130`, `SettingTypes.h:857`

---

## STAGING_WRAM_SOURCE Shows NO_WRAM_PAIRS (v2.4 Fix Required)

**Symptom:** `STAGING_WRAM_SOURCE` log entries all show `NO_WRAM_PAIRS` even though
you expected WRAM reads to be detected.

**Cause (pre-v2.4):** Bug in `register_wram_source_callbacks()` checked wrong flag
(`STAGING_WRAM_TRACKING_ENABLED` instead of `STAGING_WRAM_SOURCE_ENABLED`), so
WRAM read callbacks were never actually registered.

**Fix:** Update to v2.4 of `mesen2_dma_probe.lua`.

**Verification:** After update, log must show this line at lazy registration time:
```
INFO: WRAM source callback registered (lazy) for S-CPU: 0x7E8000-0x7EFFFF at frame=1498
```

If you only see "Staging watch registered" but NOT "WRAM source callback registered",
WRAM source tracking is not active and all `NO_WRAM_PAIRS` results are meaningless.

---

## FILL_SESSION Not Appearing (v2.9)

**Symptom:** `BUFFER_WRITE_SUMMARY` entries appear with writes, but no `FILL_SESSION`
entries are logged when staging DMA fires.

**Debug steps:**

1. **Check DEBUG_FILL output:**
   ```bash
   grep "DEBUG_FILL" mesen2_exchange/dma_probe_log.txt | head -10
   ```

2. **Expected output:**
   ```
   DEBUG_FILL: frame=1502 BW_ENABLED=true fill_active=true prg_total=1157
   ```

3. **If `fill_active=false`:** Buffer write callback isn't setting the flag. Check that
   `BUFFER_WRITE_WATCH=1` is set and the address range (0x1530-0x161A) overlaps actual writes.

4. **If `fill_active=true` but no FILL_SESSION:** Check `DEBUG_FILL_SUMMARY` for errors:
   ```bash
   grep "DEBUG_FILL_SUMMARY" mesen2_exchange/dma_probe_log.txt
   ```

5. **If compress_prg_runs FAILED:** The ring buffer processing has a bug - check the
   error message for details.

**Verification:** Log should show both:
```
INFO: Buffer write watch registered (lazy) for S-CPU: 0x001530-0x00161A at frame=1498
INFO: Fill session PRG read callback registered: 0x000000-0x3FFFFF at frame=1498
```

---

## Diagnostic Priority (Start Here)

Follow this flowchart **in order**. Fix issues at each step before proceeding.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     STEP 1: CAPTURE INTEGRITY                          │
├─────────────────────────────────────────────────────────────────────────┤
│  1. data_hex length = 64 chars? ────────────────── NO → Fix tile read  │
│  2. >50% tiles have odd bytes ≠ 0? ─────────────── NO → Fix VRAM path │
│  3. Callbacks firing? ───────────────────────────── NO → Run preflight │
│                                                                         │
│  All YES? → Proceed to Step 2                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     STEP 2: OBSEL CONFIGURATION                        │
├─────────────────────────────────────────────────────────────────────────┤
│  4. oam_base_addr / oam_addr_offset logged? ─────── NO → Fix capture   │
│  5. tile_page (attr bit 0) captured? ──────────── NO → Add to capture  │
│  6. Tile address formula matches hardware? ──────── NO → Fix formula   │
│     (See 00_STABLE_SNES_FACTS.md for canonical formula)                │
│                                                                         │
│  All YES? → Proceed to Step 3                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     STEP 3: DATABASE MATCHING                          │
├─────────────────────────────────────────────────────────────────────────┤
│  7. ROM file matches DB metadata? ───────────────── NO → Rebuild DB    │
│  8. DB has offsets for this game state? ─────────── NO → Expand DB     │
│  9. High-info tiles exist in capture? ─────────── NO → Expected if UI  │
│                                                                         │
│  All YES? → Proceed to Step 4                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                     STEP 4: ADVANCED DIAGNOSIS                         │
├─────────────────────────────────────────────────────────────────────────┤
│  10. SA-1 char conversion active? ───────────────── YES → Use Strategy A │
│  11. WRAM staging overlap > 0? ──────────────────── NO → Wrong frame   │
│  12. ROM trace seeds valid? ─────────────────────── NO → Validate seed │
│                                                                         │
│  Still failing? → Open issue with capture + logs                       │
└─────────────────────────────────────────────────────────────────────────┘
```

**Quick commands for each step:**
```bash
# Step 1: Capture integrity
python3 scripts/analyze_capture_quality.py <capture>

# Step 2: OBSEL verification (check capture JSON for obsel.* fields)
cat mesen2_exchange/sprite_capture_*.json | jq '.obsel'

# Step 3: Database matching
python3 scripts/analyze_capture_quality.py <capture> --database <db> --rom <rom>

# Step 4: ROM trace analysis
python3 scripts/summarize_rom_trace.py <run_dir> --bucket-size 0x1000 --top 5
python3 scripts/validate_seed_candidate.py <rom> --seed <addr> --auto-map --png test.png
```

## Minimal Reproduction Checklist

Before opening an issue, verify these basics:

### Environment
- [ ] Mesen2 build matches `01_BUILD_SPECIFIC_CONTRACT.md` tested version
- [ ] ROM file is headerless `.sfc` (not `.smc` with 512-byte header, or zipped)
- [ ] WSL interop working (if applicable): `cmd.exe /c echo hello` succeeds
- [ ] Output directory exists and is writable

### Capture Artifacts
- [ ] `sprite_capture_*.json` files created in `mesen2_exchange/`
- [ ] `data_hex` fields are exactly 64 characters
- [ ] Odd bytes are not all zero (run `analyze_capture_quality.py`)

### Database
- [ ] `tile_hash_database.json` exists and matches ROM (check `metadata.rom_checksum`)
- [ ] Database has entries for the game state being captured

### Scoring
- [ ] `matched_tiles > 0` (tiles found in DB)
- [ ] `scored_tiles > 0` (high-info tiles contributing to score)
- [ ] If both are zero, check for SA-1 character conversion

## Fail-Fast Checks (Required)
1. **Tile bytes complete**: `data_hex` length is 64 hex chars (32 bytes).
2. **Odd bytes non-zero**: if **>50% of tiles** have every odd byte as zero, **investigate
   the VRAM read path** before continuing. This threshold catches systemic byte-lane issues
   while allowing individual low-palette tiles.

   **Next step if triggered:** Run endianness probe in `01_BUILD_SPECIFIC_CONTRACT.md`
   § "Byte-Order Verification" to confirm VRAM read behavior.
3. **Entropy check**: tiles with **<= 2 unique byte values** are low-information and are
   intentionally ignored in scoring.
4. **Callbacks fire**: memory callbacks must fire within a known time window.
5. **VRAM read sanity**: verify a tile read differs from its neighbor (non-zero data in both lanes).

Quick report (recommended):
```
python3 scripts/analyze_capture_quality.py mesen2_exchange/door_transition_capture_run3 \
  --database mesen2_exchange/tile_hash_database.json
```

## Success Criteria (Provisional)

These thresholds are heuristics for evaluating capture quality. Cross-reference with
register logs and game state to interpret results correctly.

| Metric | Non-SA1 Game Expected | SA1 + Conversion Expected |
|--------|----------------------|--------------------------|
| Tile hash hit rate | >70% | <10% |
| Low-info tile % | 10-30% | 10-30% |
| Top ROM bucket concentration | >50% | Variable |
| WRAM/VRAM overlap | >50% | <10% |
| Odd-byte non-zero % | >95% | >95% |

**Interpretation:**
- **High hash hit rate + low ROM bucket concentration**: Many tiles match many offsets
  (collisions), use timing correlation to disambiguate.
- **Low hash hit rate + high WRAM/VRAM overlap**: Tiles changed between capture and DB
  build, or DB offsets incomplete.
- **Low hash hit rate + low WRAM/VRAM overlap + SA-1 game**: Expected when character
  conversion is active. Proceed with Strategy A.

## Timing Correlation Failure Modes

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Low top-bucket count, buckets tied | Multi-region frame (sprites from multiple ROM areas) | Use per-burst bucketing |
| High confidence, wrong ROM region | Hash collision (common tiles match many offsets) | Cross-reference with timing; require top-2 bucket separation |
| Correlation off by 1-2 frames | Double buffering / VBlank timing | Widen correlation window to ±2 frames |
| Hot bucket has no graphics | Pointer table reads, not tile data | Filter by 32-byte alignment; validate via decompression |
| All buckets have similar counts | Heavy ROM access across regions | Increase `ROM_TRACE_MAX_READS`; use per-frame bursts |
| Capture has tiles, trace is empty | ROM trace callback not firing | Check callback registration; verify memory type |

## WARNING: WRAM Staging Analysis Limitations

> **CRITICAL:** WRAM staging analysis (`analyze_wram_staging.py`) is ONLY valid for:
> - Static assets (UI elements, fonts)
> - Non-converted tile data

**When tile conversion/transformation is active:**
- WRAM contains SOURCE data (bitmap or compressed format)
- VRAM contains OUTPUT data (converted bitplane format)
- Hash comparison will show **ZERO OVERLAP**

**This is expected behavior, not a bug.**

| Scenario | Expected WRAM/VRAM Overlap |
|----------|---------------------------|
| SA-1 conversion INACTIVE | >50% (tiles match) |
| SA-1 conversion ACTIVE | <10% (format differs) |
| UI/font-only capture | Variable (depends on game) |

**If you see zero overlap between WRAM and VRAM dumps:**
1. Check if SA-1 conversion is active (see `SA1_HYPOTHESIS_FINDINGS.md`)
2. If conversion active: zero overlap is correct, use Strategy A (timing correlation)
3. If conversion NOT active: investigate other causes:
   - Frame timing (WRAM dump after buffer reuse)
   - Wrong WRAM range (staging buffer elsewhere)
   - Compression variant (not HAL format)

## Common Symptoms

### Symptom: No matches for any tiles
- Likely causes:
  - VRAM read path wrong (odd bytes are zero)
  - OBSEL math wrong (oam_base/oam_offset not applied)
  - Tile page / attr bit 0 mishandled
  - ROM mismatch (headered ROM or different revision) or DB missing relevant offsets
- Fix:
  - Validate odd-byte data first
  - Re-check OBSEL values and `tile_page` usage
  - Confirm ROM header/CRC and expand DB offsets if capture is otherwise valid

### Symptom: All/most even bytes are zero, odd bytes have data
- Cause: Byte extraction order in `read_vram_tile_word()` is wrong for tile data format.
- Example: tile `00D0009A0064...` has zeros at positions 0,2,4,... and data at 1,3,5,...
- Why: SNES 4bpp tile format expects high-byte-first within each word pair. The extraction
  order must match this, regardless of the API's native byte order.
- Fix: Use the byte-swap pattern in `01_BUILD_SPECIFIC_CONTRACT.md` § "VRAM Read Semantics":
  ```lua
  local word = emu.readWord(byte_addr, emu.memType.snesVideoRam)
  local byte0 = (word >> 8) & 0xFF   -- position 0 in tile data
  local byte1 = word & 0xFF          -- position 1 in tile data
  ```
- Verify: Run `verify_endianness.lua` after any Mesen2 upgrade to confirm behavior.

### Symptom: No VRAM DMA observed
- Important: lack of observed DMA **does not prove** VRAM uploads are absent.
  - VRAM can change via CPU writes to $2118/$2119 or via callback blind spots.
- Fix:
  - Rely on VRAM diff (hash-based) to detect changes.
  - Log $2118/$2119 writes and DMA source dumps when possible.

### Symptom: Hash hits exist but no ROM offsets score
- Likely causes:
  - Only low-information tiles matched (weights are zero by design)
  - Tiles match many offsets (collisions) so scores never separate
  - DB coverage mismatch (correct capture, wrong source blocks indexed)
  - SA-1 character conversion active (VRAM tiles not equal to ROM-decompressed bytes)
    - **Kirby Super Star**: only 1.5% hash match rate during gameplay (strongly suggests conversion)
    - See `03_GAME_MAPPING_KIRBY_SA1.md` → "Strongly Suggested: SA-1 Conversion Active"
- Fix:
  - Compare `matched_tiles` vs `scored_tiles`
  - Check unique-byte distribution and odd-byte sanity for the capture
  - Expect zero scores if most tiles are low-info (outlines, UI glyphs, gradients) even if the
    pipeline is otherwise correct; treat this as a **ranking limitation**, not a capture failure.
  - If VRAM diff shows WRAM staging, compare WRAM tiles to VRAM/DB:
    `python3 scripts/analyze_wram_staging.py --capture ... --wram ... --database ... --rom ...`
  - If overlap is still zero, scan for misalignment or substring matches:
    `--wram-start 0x0000` and review the alignment + substring output
  - Expand the tile DB with offsets from the relevant state
  - Verify the ROM header/CRC and capture timing (e.g., later frames)
  - If ROM tracing is enabled, summarize read ranges per burst:
    `python3 scripts/summarize_rom_trace.py mesen2_exchange/<run_dir> --bucket-size 0x1000 --top 5`
  - Treat bucket bases as **ranking only**; use the first-read address (or the **run start**
    in the hot bucket output) as the candidate seed and validate via decompression before indexing.
  - If mixed buckets appear, increase `ROM_TRACE_MAX_READS` temporarily; 500 reads can clip
    bursts and bias the seed toward early pointer/table reads.
  - Validate a seed with decompression + tile metrics:
    `python3 scripts/validate_seed_candidate.py roms/<rom>.sfc --seed 0xFCC455 --auto-map --tiles 256 --png out.png`
  - If `rom_trace_log.txt` lacks `prg_size`/`prg_end`, treat all seeds as ambiguous and
    require `--auto-map` validation before indexing.

### Symptom: VRAM diff fires but WRAM overlap is near zero
- Likely causes:
  - The diff frame is not the upload window (BG-only or reused tiles)
  - WRAM staging window is outside the dump range
  - End-frame dump happens after the staging buffer was reused
- Fix:
  - Rank frames by overlap: `python3 scripts/summarize_wram_overlaps.py mesen2_exchange/<run_dir>`
    (add `--top-only` for noisy runs)
  - Enable `WRAM_DUMP_PREV=1` and compare `wram_prev` vs `wram_curr`
  - Dump full WRAM (`WRAM_DUMP_START=0x0000`, `WRAM_DUMP_SIZE=0x20000`)
  - Use the DMA source dump (`DMA_DUMP_ON_VRAM=1`) to target ranges
  - Scan alignments and substring matches in `analyze_wram_staging.py`
  - Emit a watch range from substring matches:
    `python3 scripts/analyze_wram_staging.py --capture ... --wram ... --emit-range --range-pad 0x200 --range-align`
  - If using WRAM-write-triggered captures, expect some frames to show **zero overlap**
    (buffer fill for later use). Use `analyze_wram_staging.py` to confirm which
    WRAM-write frames actually mirror VRAM tiles.

### Symptom: Callbacks never fire in headless mode
- Likely causes:
  - Callback type value wrong for current build
  - Wrong parameter order / missing cpuType/memType
- Fix:
  - Re-run the probe and log firing counts

### Symptom: Testrunner stalls after `emu.loadSavestate()`
- Likely cause: loadstate must be executed from an exec callback in this build
- Fix: register exec callback, load from there, then re-register frame callbacks

### Symptom: Movie boots but inputs do not play (stays at power-on)
- Likely cause: `.mmo` file was loaded before a ROM was actually running (ROM load is async)
- Fix: start Mesen2 with ROM + Lua, then launch Mesen2 again with the `.mmo` file so it is
  delivered to the running instance (SingleInstance IPC). See `01_BUILD_SPECIFIC_CONTRACT.md`.

### Symptom: Screenshots are black / still show the game selection screen
- Likely causes:
  - `--novideo` used (screenshots will be black)
  - ROM failed to load (bad path or archive instead of `.sfc`/`.smc`)
  - Movie never started (same root as above)
- Fix:
  - Remove `--novideo` if you need visual confirmation
  - Verify ROM path points to an extracted `.sfc`/`.smc`
  - Use the two-step movie launch in `01_BUILD_SPECIFIC_CONTRACT.md`

### Symptom: Captures are mostly intro/title screens
- Likely cause: probes start too early; heavy logging slows playback
- Fix:
  - Use `CAPTURE_START_SECONDS` and `CAPTURE_MIN_INTERVAL_SECONDS`
  - Also gate `VRAM_DIFF_START_SECONDS`, `WRAM_DUMP_START_SECONDS`, `DMA_DUMP_START_SECONDS`
  - Run longer in wall-clock time (minutes, not frames). **3–5 minutes** is typical for
    gameplay with heavy probes enabled.

### Symptom: Matches exist but sprites are mirrored
- Likely cause: flip normalization disabled
- Fix: ensure lookup includes N/H/V/HV flips

### Symptom: Scores drop sharply when flips are enabled
- Likely cause: flip-variant lookups inflate candidate counts and reduce weights
- Fix: keep flip lookup optional and use it only for targeted debugging

## Guardrail
If capture tiles are invalid (half-zero or wrong length), **stop** and fix capture first.
Any downstream matching work is wasted until capture integrity is restored.
