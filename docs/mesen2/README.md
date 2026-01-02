# Mesen 2 Integration Documentation

This folder documents the Mesen 2 sprite capture and ROM mapping pipeline for SpritePal.

## Quick Navigation

**Start here based on your task:**

| I want to... | Read |
|--------------|------|
| Understand SNES sprite/VRAM/OAM hardware | [00_STABLE_SNES_FACTS.md](00_STABLE_SNES_FACTS.md) |
| Look up Lua API signatures or callbacks | [01_BUILD_SPECIFIC_CONTRACT.md](01_BUILD_SPECIFIC_CONTRACT.md) |
| Understand capture JSON schema | [02_DATA_CONTRACTS.md](02_DATA_CONTRACTS.md) |
| Work with Kirby Super Star specifically | [03_GAME_MAPPING_KIRBY_SA1.md](03_GAME_MAPPING_KIRBY_SA1.md) |
| Debug capture or matching failures | [04_TROUBLESHOOTING.md](04_TROUBLESHOOTING.md) |

## Document Hierarchy

```
00 Stable SNES Facts        ← Universal hardware reference (emulator-agnostic)
    ↓
01 Build-Specific Contract  ← Mesen 2 API behavior and quirks
    ↓
02 Data Contracts           ← JSON schemas for captures and databases
    ↓
03 Game Mapping             ← Kirby Super Star-specific assumptions
    ↓
04 Troubleshooting          ← Diagnostic flowcharts and symptom→fix mapping
```

## Common Tasks

### First-time setup / new Mesen 2 build
1. Run preflight probe: see [01 § mesen2_preflight_probe.lua](01_BUILD_SPECIFIC_CONTRACT.md#mesen2_preflight_probelua)
2. Verify API enums match documented values
3. Test a basic capture before running complex probes

### Capture sprites from gameplay
1. Choose script: [01 § Lua Script Quick Reference](01_BUILD_SPECIFIC_CONTRACT.md#lua-script-quick-reference)
2. Run capture: see [CLAUDE.md § Running Mesen 2 with Lua Scripts](../../CLAUDE.md)
3. Validate output: `python3 scripts/analyze_capture_quality.py <capture>`

### Debug "no matches" or low scores
1. Follow [04 § Diagnostic Priority](04_TROUBLESHOOTING.md#diagnostic-priority-start-here) flowchart
2. Check capture integrity first (odd bytes, data_hex length)
3. For Kirby: expect ~1.5% match rate (suggests SA-1 character conversion or staging transform)

### Trace staging buffer writes (Kirby Super Star)
1. Run: `run_staging_trace.bat` (Windows) or set env vars manually
2. Wait for ~2000 frames to complete
3. Analyze the data flow chain:
   ```bash
   grep "STAGING_WRAM_SOURCE" dma_probe_log.txt   # What WRAM feeds staging
   grep "BUFFER_WRITE_SUMMARY" dma_probe_log.txt  # What code writes to source buffer
   grep "FILL_SESSION" dma_probe_log.txt          # PRG reads during fill (v2.9)
   ```
4. Look for `quality=HIGH` entries with large `max_run` values
5. See [CHANGELOG § 2.14.0](CHANGELOG.md) for v2.9 FILL_SESSION feature

### Current data flow chain (Kirby Super Star)
```
ROM ($E0-$EF banks) → [01:F724 routine] → source buffer (0x1530) → staging (0x2000) → VRAM
        ^                    ^                   ^                      ^
        |               BUFFER_WRITE        STAGING_WRAM_SOURCE    STAGING_SUMMARY
        |               pcs=01:F724         wram_runs=[0x1530-0x161A]
        |
        └── FILL_SESSION prg_runs (v2.9, see CHANGELOG 2.14.1):
            0xE13CA7 (219 bytes), 0xEB3D4B (218 bytes), 0xE7DF31 (202 bytes)
```

### Find ROM offsets for new sprites
1. Enable tracing: `BUFFER_WRITE_WATCH=1` in run_staging_trace.bat
2. Run DMA probe: wait for ~2000 frames
3. Check `FILL_SESSION` entries for `prg_runs` - these are candidate ROM regions
4. Validate seed: `python3 scripts/validate_seed_candidate.py <rom> --seed <addr> --auto-map`
5. See [03 § Candidate Offset Validation](03_GAME_MAPPING_KIRBY_SA1.md#candidate-offset-validation-required)

### Understand address conversions
- Hardware word↔byte: [00 § VRAM Addressing](00_STABLE_SNES_FACTS.md#vram-addressing-ppu)
- API `emu.convertAddress()`: [01 § emu.convertAddress()](01_BUILD_SPECIFIC_CONTRACT.md#emuconvertaddress-current-build)
- SA-1/LoROM/HiROM formulas: [03 § Address Conversion Reference](03_GAME_MAPPING_KIRBY_SA1.md#address-conversion-reference)

## Key Constraints

- **Kirby Super Star: 0% verbatim match rate for gameplay tiles** — Sprite DMAs come from WRAM 0x7E:2000, not cart ROM directly. CCDMA is NOT active for sprites. The transform occurs during WRAM staging. See `CHANGELOG.md` entries 2.6.0 and 2.7.0.
- **Primary writer routine confirmed: `01:F724` / `01:F729`** — 100% stable across different gameplay scenarios. This is THE choke point for tracing ROM→VRAM. See `CHANGELOG.md` entry 2.13.0.
- **Source buffer at `0x1530-0x161A`** — Staging copy reads from this 235-byte region. This is the intermediate buffer between ROM data and staging. See `CHANGELOG.md` entry 2.12.0.
- **Tile data requires byte swap** — extract high byte first for SNES tile format. Verify with `verify_endianness.lua`.
- **ROM trace addresses are seeds, not exact offsets** — always validate via HAL decompression.
- **Quality metrics required** — Only trust `prg_runs` with `quality=HIGH` (max_run >= 64, coverage > 0.5). Low quality matches are likely code fetches.

## Archived Documentation

Historical exploration notes are in `obsoleteArchive/`. These are superseded by the numbered docs above.
