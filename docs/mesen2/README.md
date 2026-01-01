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

### Find ROM offsets for new sprites
1. Run DMA probe with ROM tracing enabled
2. Summarize: `python3 scripts/summarize_rom_trace.py <run_dir>`
3. Validate seed: `python3 scripts/validate_seed_candidate.py <rom> --seed <addr> --auto-map`
4. See [03 § Candidate Offset Validation](03_GAME_MAPPING_KIRBY_SA1.md#candidate-offset-validation-required)

### Understand address conversions
- Hardware word↔byte: [00 § VRAM Addressing](00_STABLE_SNES_FACTS.md#vram-addressing-ppu)
- API `emu.convertAddress()`: [01 § emu.convertAddress()](01_BUILD_SPECIFIC_CONTRACT.md#emuconvertaddress-current-build)
- SA-1/LoROM/HiROM formulas: [03 § Address Conversion Reference](03_GAME_MAPPING_KIRBY_SA1.md#address-conversion-reference)

## Key Constraints

- **Kirby Super Star: 0% verbatim match rate for gameplay tiles** — Sprite DMAs come from WRAM 0x7E:2000, not cart ROM directly. CCDMA is NOT active for sprites. The transform occurs during WRAM staging (mechanism TBD). See `CHANGELOG.md` entry 2.6.0.
- **Tile data requires byte swap** — extract high byte first for SNES tile format. Verify with `verify_endianness.lua`.
- **ROM trace addresses are seeds, not exact offsets** — always validate via HAL decompression.

## Archived Documentation

Historical exploration notes are in `obsoleteArchive/`. These are superseded by the numbered docs above.
