# Dedede Split Injection Bug Investigation

**Date:** 2026-01-29
**Status:** In Progress
**Affected:** King Dedede RAW sprites (capture_1769108991 - beak closed)

## Problem Summary

When injecting an AI frame into King Dedede's "beak closed" capture, the sprite appears **split/fragmented** in-game:
- Some tiles show the new AI art
- Other tiles show the original game art
- Result: scrambled appearance mixing old and new graphics

## Visual Evidence

| File | Description |
|------|-------------|
| `split_1.png` | In-game result showing mixed old/new tiles (upper portion) |
| `split_2.png` | In-game result showing mixed old/new tiles (lower portion) |
| `Closed.png` | Original game sprite (beak closed) with tile grid |
| `Open.png` | Original game sprite (beak open) with tile grid |

## Test ROMs

| ROM | Result |
|-----|--------|
| `_injected_2.sfc` | BROKEN - One sprite half replaced, one fully replaced |
| `_injected_3.sfc` | WORKING - Dedede beak closed fully replaced cleanly |
| `_injected_4.sfc` | Unknown |
| `_injected_5.sfc` | Unknown |

## Key Finding: ROM Offset Mismatch

### Capture Data vs ROM Reality

The Mesen capture reports tile offsets around `0x282xxx` (SA-1 CPU addresses), but:

1. **ROM at `0x282xxx` contains DIFFERENT data** than capture tiles
2. **Verification's `.find()` locates tiles elsewhere** - scattered across `0x17xxx` range
3. **Tiles have DUPLICATE occurrences** in ROM at different addresses

### Tile Location Analysis

```
Entry 6-9 tiles (upper sprite):
  - Found at TWO locations each (e.g., 0x17601 AND 0x17A01)
  - First occurrence is in 0x173xx-0x175xx range

Entry 10-13 tiles (lower sprite):
  - Found at ONE location each
  - Only occurrence is in 0x176xx-0x179xx range
```

### Working vs Broken Injection Comparison

**Working injection (`_injected_3.sfc`) wrote to:**
- `0x017285 - 0x017421` (412 bytes)
- `0x017481 - 0x01761B` (410 bytes)
- Did NOT touch `0x17700-0x179FF`

**Verification "corrects" to:**
- 12 offsets in 0x173xx-0x175xx (CORRECT - inside working range)
- 14 offsets in 0x176xx-0x179xx (WRONG - outside working range)

## Root Cause Theories

### Theory 1: Verification Mis-Attribution (Confirmed Partial)

The `_search_raw_tile()` method uses `.find()` which returns the **first** occurrence of tile bytes. When duplicate tile data exists:

- Upper tiles: first occurrence is correct (0x173xx-0x175xx)
- Lower tiles: first (and only) occurrence is WRONG (0x176xx-0x179xx)

**Evidence:** Tiles for entries 10-13 only exist at 0x176xx-0x179xx, not where they "should" be based on delta calculations.

### Theory 2: Capture Tile Data Mismatch

The capture's tile data for entries 10-13 may not represent the actual Dedede sprite tiles:

- The tile data exists at 0x176xx-0x179xx in ROM
- But the working injection wrote to 0x172xx-0x175xx (different tile data)
- The game displays correctly after modifying 0x172xx-0x175xx

**Implication:** The capture may have recorded wrong tiles (perhaps from a different animation state or different character).

### Theory 3: SA-1 Address Mapping Issues

Kirby Super Star uses the SA-1 chip with complex address mapping:

- Capture offset `0x282xxx` appears to be a CPU address, not a file offset
- The mapping from CPU address to ROM file offset may be incorrect
- Need to verify how Mesen's Lua scripts perform ROM attribution

### Theory 4: VRAM Timing/DMA Confusion

The VRAM capture may have occurred at a moment when:

- DMA was copying tiles between VRAM locations
- Animation was transitioning between frames
- Tiles were partially updated

## Delta Analysis

Calculated delta from capture offset to ROM offset:

```
Capture offset - ROM offset = Delta

Tiles with delta 0x26AD97 (2,534,807): 12 tiles → CORRECT locations
Tiles with delta 0x26A997 (2,533,783): 14 tiles → WRONG locations

Difference: 0x400 (1,024 bytes = 32 tiles)
```

The 1,024 byte offset suggests tiles are being found in an adjacent sprite block.

## Attempted Fixes

### Fix 1: Verify Capture Offset First

Added `_verify_tile_at_offset()` to check if tile data exists at capture's original offset before searching.

**Result:** Still fails - capture offsets don't contain expected tile data.

### Fix 2: Contiguous Block Search

Added `_search_raw_tile_contiguous()` to prefer matches that maintain spatial consistency with already-found tiles using delta voting.

**Result:** Partial improvement - works for tiles with multiple occurrences, but entries 10-13 only have one occurrence (at wrong location).

## Open Questions

1. **How was `_injected_3.sfc` created?** What settings/method produced the working injection?

2. **Why do entries 10-13 tiles only exist at 0x176xx-0x179xx?** Are they:
   - From a different sprite/character?
   - From a different animation frame?
   - Incorrectly attributed by Mesen?

3. **What tiles SHOULD be at 0x172xx-0x175xx?** The working injection modified this range successfully.

4. **Is the capture file (`capture_1769108991.json`) accurate?** The tile data it contains doesn't match the expected ROM locations.

## Files Involved

### Capture Files
- `mesen2_exchange/capture_1769108991.json` - Beak closed (problematic)
- `mesen2_exchange/capture_1769108997.json` - Beak open

### Code Files
- `core/services/rom_verification_service.py` - Offset verification logic
- `core/services/injection_orchestrator.py` - Tile injection pipeline
- `scripts/verify_frame_injection.py` - Diagnostic visualization tool

### Mapping Project
- `mapping.spritepal-mapping.json` - Contains frame mappings and ROM offsets

## ROM Address Ranges

| Range | Contents |
|-------|----------|
| `0x007FDC-0x007FE0` | ROM checksum |
| `0x017280-0x017620` | Dedede sprite tiles (where working injection wrote) |
| `0x017680-0x017A00` | Related/similar tiles (where verification finds entries 10-13) |
| `0x144037-0x144057` | Palette data |
| `0x282xxx` | Capture-reported offsets (SA-1 CPU addresses, not file offsets) |

## Next Steps

1. [ ] Add detailed injection debug logging
2. [ ] Compare capture data between working and broken injections
3. [ ] Investigate how `_injected_3.sfc` was created
4. [ ] Consider skipping verification for RAW tiles entirely
5. [ ] Investigate Mesen Lua script ROM attribution logic
