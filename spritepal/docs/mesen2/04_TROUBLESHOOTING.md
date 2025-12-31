# 04 Troubleshooting

This is a fail-fast diagnostic flow. **Do not expand the tile DB or relax filters** until
VRAM capture integrity is verified.

## Diagnostic Priority (Start Here)

Follow this flowchart **in order**. Fix issues at each step before proceeding.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     STEP 1: CAPTURE INTEGRITY                          │
├─────────────────────────────────────────────────────────────────────────┤
│  1. data_hex length = 64 chars? ────────────────── NO → Fix tile read  │
│  2. Most tiles have odd bytes ≠ 0? ──────────────── NO → Fix VRAM path │
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
│  6. Tile address formula matches Mesen 2? ───────── NO → Fix formula   │
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
│  10. SA-1 char conversion active? ───────────────── YES → Strategy A/B │
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

## Fail-Fast Checks (Required)
1. **Tile bytes complete**: `data_hex` length is 64 hex chars (32 bytes).
2. **Odd bytes non-zero**: if **most/all tiles** have every odd byte as zero, **investigate
   the VRAM read path** before continuing. This is a strong indicator of byte-lane issues but
   is not mathematically impossible for individual low-palette tiles.
3. **Entropy check**: tiles with **<= 2 unique byte values** are low-information and are
   intentionally ignored in scoring.
4. **Callbacks fire**: memory callbacks must fire within a known time window.
5. **VRAM read sanity**: verify a tile read differs from its neighbor (non-zero data in both lanes).

Quick report (recommended):
```
python3 scripts/analyze_capture_quality.py mesen2_exchange/door_transition_capture_run3 \
  --database mesen2_exchange/tile_hash_database.json
```

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
