# Lua Script vs SpritePal ROM Offset Validation Guide

This guide explains how to validate that ROM offsets found by Mesen2 Lua scripts match the actual sprite data detected by SpritePal's manual offset functionality.

## Overview

The validation system compares two different approaches to sprite detection in SNES ROMs:

1. **Lua Scripts (Runtime Detection)**: Monitor DMA transfers during gameplay to find ROM offsets where sprites are loaded
2. **SpritePal (Static Analysis)**: Test specific ROM offsets to validate if they contain decompressible sprite data

## Quick Start

### 1. Collect Lua Script Data

#### Option A: Fixed Offsets Script
```bash
# Load mesen2_sprite_finder_fixed_offsets.lua in Mesen2
# Play the game for a few minutes
# Press '3' to export data
# This creates sprite_capture_TIMESTAMP.json
```

#### Option B: Precise Offsets Script  
```bash
# Load mesen2_sprite_finder_precise.lua in Mesen2
# Press '7' to enable debug mode for more detailed logging
# Play the game for a few minutes  
# Press '3' to export data
# This creates sprite_capture_precise_TIMESTAMP.json
```

### 2. Run Validation

```bash
# Basic validation
python validate_lua_vs_spritepal_offsets.py \
    --rom /path/to/game.smc \
    --lua-json sprite_capture_20250120_143022.json

# Verbose output with detailed logging
python validate_lua_vs_spritepal_offsets.py \
    --rom /path/to/game.smc \
    --lua-json sprite_capture_precise_20250120_143022.json \
    --verbose \
    --output-dir results/
```

### 3. Review Results

The validation generates two output files:
- `validation_report_FILENAME.txt` - Human-readable summary
- `detailed_results_FILENAME.json` - Complete data for analysis

## Lua Scripts Explained

### Fixed Offsets Script (`mesen2_sprite_finder_fixed_offsets.lua`)

**How it works:**
- Monitors DMA channel writes to track sprite data transfers
- Records the base ROM offset for each DMA transfer to VRAM
- All sprites within a DMA transfer get the same ROM offset
- Exports offsets with hit counts (frequency of access)

**Best for:**
- Finding general sprite regions in ROM
- Understanding sprite loading patterns
- Identifying frequently accessed sprite data

**Controls:**
- `1` - Start/Resume capture
- `2` - Pause capture  
- `3` - Export data to JSON
- `4` - Reset capture data
- `5` - Toggle HUD display
- `6` - Toggle ROM offset display on sprites

### Precise Offsets Script (`mesen2_sprite_finder_precise.lua`)

**How it works:**
- Same DMA monitoring as fixed script
- Calculates exact ROM offset for each individual sprite
- Uses sprite VRAM position within DMA transfer to determine precise offset
- Exports unique sprite-specific offsets

**Best for:**
- Finding exact sprite data locations  
- Validating individual sprite extraction
- Higher precision sprite-to-ROM mapping

**Additional Controls:**
- `7` - Toggle debug logging for detailed offset calculations

**Debug Output Example:**
```
Sprite 12: Tile 4A at VRAM $6000 -> ROM $240040 (DMA base $240000 + $0040)
```

## Understanding Validation Results

### Accuracy Rates

| Rate | Interpretation | Action |
|------|----------------|---------|
| >80% | Excellent - Lua script very reliable | Use results with confidence |
| 60-80% | Good - Minor false positives | Review medium/low confidence matches |
| 40-60% | Fair - Moderate accuracy | Check script configuration, game timing |
| <40% | Poor - Many false positives | Investigate script issues, ROM format |

### Confidence Levels

**High Confidence (≥0.7)**
- Very likely to be actual sprite data
- SpritePal successfully decompressed and validated the data
- Safe to use for sprite extraction

**Medium Confidence (0.4-0.7)**  
- Possible sprite data that passed basic validation
- May need manual review or different extraction settings
- Could be valid sprites with unusual characteristics

**Low Confidence (<0.4)**
- Unlikely to be sprite data
- Failed SpritePal's visual validation tests
- Possibly compressed data that isn't sprite-related

## Example Validation Report

```
=== Lua Script vs SpritePal Validation Report ===

ROM File: /roms/game.smc
Analysis Date: 1737417600

SUMMARY STATISTICS:
- Total Lua Offsets: 25
- Valid Sprites Found: 22
- Invalid Offsets: 3  
- Accuracy Rate: 88.0%

CONFIDENCE BREAKDOWN:
- High Confidence (≥0.7): 18 sprites
- Medium Confidence (0.4-0.7): 4 sprites
- Low Confidence (<0.4): 0 sprites

HIGH CONFIDENCE SPRITES:
  0x240040: confidence=0.847, tiles=16
  0x260020: confidence=0.792, tiles=12
  0x280060: confidence=0.734, tiles=8

ANALYSIS:
The Lua script accuracy of 88.0% indicates:
- EXCELLENT: Lua script very accurately identifies sprite locations
- High confidence matches: 18/25 (72.0%)
```

## Troubleshooting

### Common Issues

**Low Accuracy Rates (<60%)**

Possible causes:
- Game not actively displaying sprites during capture
- ROM uses non-standard compression or format
- DMA timing issues in the Lua script
- SpritePal extraction settings don't match ROM format

Solutions:
1. Capture during active gameplay (character movement, animations)
2. Try both Lua scripts to compare results
3. Check ROM format compatibility with SpritePal
4. Adjust SpritePal's HAL compression settings

**No Valid Sprites Found**

Possible causes:
- Wrong ROM file format or path
- ROM doesn't use HAL compression
- Offsets point to non-sprite data regions

Solutions:
1. Verify ROM file is the same one used in Mesen2
2. Check if ROM uses different compression format
3. Try manual offset slider in SpritePal to verify sprite extraction works

**High False Positive Rate**

Possible causes:
- Lua script capturing non-sprite DMA transfers
- Game loading other compressed data (music, maps, etc.)
- Script configuration needs refinement

Solutions:
1. Use the Precise script for better accuracy
2. Filter results by hit count (frequent accesses more likely sprites)
3. Focus on high-confidence results only

### Manual Verification

To manually verify results:

1. **Open SpritePal**
2. **Load the same ROM file**
3. **Open Manual Offset Dialog**
4. **Navigate to a high-confidence offset from the report**
5. **Use the slider to go to that exact offset**
6. **Check if sprites appear in the preview**

The manual offset slider value should match the hex offset from the validation report.

## Advanced Usage

### Batch Validation

```bash
# Validate multiple JSON files
for json_file in captures/*.json; do
    python validate_lua_vs_spritepal_offsets.py \
        --rom game.smc \
        --lua-json "$json_file" \
        --output-dir "results/$(basename "$json_file" .json)/"
done
```

### Custom Analysis

```python
from validate_lua_vs_spritepal_offsets import LuaSpritePalValidator

# Load detailed results for custom analysis
validator = LuaSpritePalValidator("game.smc")
lua_offsets = validator.load_lua_results("capture.json")

# Filter by confidence
high_confidence = [r for r in results if r["confidence"] >= 0.8]
print(f"Found {len(high_confidence)} high-confidence sprites")
```

## Integration with SpritePal Workflow

1. **Discovery Phase**: Use Lua scripts to find sprite regions
2. **Validation Phase**: Run this validation system to verify accuracy  
3. **Extraction Phase**: Use high-confidence offsets in SpritePal for sprite extraction
4. **Refinement Phase**: Manually review medium-confidence results

This validation system ensures both the Lua scripts and SpritePal's manual offset functionality are working correctly and producing consistent results for sprite detection.

## File Structure

```
spritepal/
├── validate_lua_vs_spritepal_offsets.py    # Main validation script
├── test_lua_validation_demo.py             # Demo and testing script  
├── mesen2_sprite_finder_fixed_offsets.lua  # Fixed offsets Lua script
├── mesen2_sprite_finder_precise.lua        # Precise offsets Lua script
└── LUA_SPRITEPAL_VALIDATION_GUIDE.md       # This documentation
```

For questions or issues, check the SpritePal logs and ensure both the ROM file and Lua JSON data are accessible and valid.