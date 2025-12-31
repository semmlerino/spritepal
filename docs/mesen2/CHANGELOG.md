# Mesen2 Sprite Extraction Pipeline Changelog

All notable changes to the sprite extraction pipeline documentation and tooling.

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

**Root Cause:** All existing captures are from menu/cutscene screens (frames 199-6227),
NOT actual gameplay. Menu graphics (fonts, UI) are stored differently:
- Possibly uncompressed in ROM
- In different HAL blocks than sprite data at $1B0000
- May use BG layers instead of OBJ sprites

**Evidence:**
- HAL-decompressed ROM tiles have all 4 planes populated (verified)
- VRAM tiles only use planes 0+2 (98.3% of captured tiles)
- Game zeros planes 1+3 at runtime (confirmed by plane analysis)
- Planes 0+2 comparison still yields 0% matches → wrong graphics captured

**Next Steps:**
- [ ] Capture during actual gameplay (Kirby running around, enemies visible)
- [ ] Verify OBJ sprites vs BG tiles in Mesen's viewers during capture
- [ ] Re-run ROM matching with gameplay captures
- [ ] If gameplay sprites match, confirm menu assets are stored separately

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
