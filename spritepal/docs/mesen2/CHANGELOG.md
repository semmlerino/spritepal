# Mesen2 Sprite Extraction Pipeline Changelog

All notable changes to the sprite extraction pipeline documentation and tooling.

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
