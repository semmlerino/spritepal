# SA-1 Conversion Hypothesis: REQUIRES REVISION

> **Status:** PARTIALLY INCORRECT - SEE CORRECTIONS BELOW
> **Last Updated:** 2026-01-01
> **Original Analysis:** 2024-12-31
> **Corrections By:** Claude (based on DMA log analysis)

## CORRECTIONS (2026-01-01)

The original conclusions below contain errors. Key corrections:

### 1. CCDMA Is NOT Active For Sprite Tiles

**Original claim:** "100% of SA-1 DMA operations use character conversion"

**Correction:** The $2230 register writes observed were for *other* DMA operations,
not the sprite tile transfers. Analysis of SNES_DMA_VRAM entries around frame 1500
shows:

- Sprite tile DMAs come from **WRAM bank $7E** (addresses like 0x7E:2000)
- Cart ROM DMAs (banks $ED/$EE) go to VRAM 0x6000+ (BG tiles, not sprites)
- **CCDMA only applies to BW-RAM/cart ROM sources**, not WRAM

When DMA source is WRAM, the data is already in final SNES 4bpp format - no
conversion occurs during transfer.

### 2. "WRAM Staging Irrelevant" Is Wrong

**Original claim:** "WRAM staging analysis is irrelevant"

**Correction:** WRAM staging is **central** to understanding the data flow:

- Sprite tiles are staged at WRAM 0x7E:2000 (already in planar format)
- Then DMA'd to VRAM 0x4000+ (sprite tile area)
- The key question is: **what writes to WRAM 0x2000?**

### 3. Transform Search Results

A comprehensive transform search was performed (2026-01-01):

| Transform | Tiles Matched |
|-----------|---------------|
| Verbatim 32 bytes | 0/24 |
| Byte-pair swap | 0/24 |
| Bitmap nibble encoding | 0/24 |
| All 24 plane permutations | 0/24 |
| H/V/HV flips | 0/24 |

**Conclusion:** The VRAM tiles do not exist verbatim in ROM under any common
transform. This suggests runtime assembly or a more complex transform chain.

### 4. Plane Usage Verification

Analysis of gameplay captures (frames 1500-5250):

- **0/177 tiles** are "planes 0+2 only"
- **>90%** use all 4 planes with pixel values > 5
- The "planes 0+2" observation was specific to menu/cutscene captures

---

## Original Analysis (Below - Partially Incorrect)

## Background

The sprite extraction pipeline assumes SA-1 character conversion explains why ROM bytes don't match VRAM bytes (1.5% hash match rate). This hypothesis must be verified before proceeding with Strategy A (VRAM-based DB with timing correlation).

### SA-1 Character Conversion Registers

| Register | Address | Relevant Bit | Purpose |
|----------|---------|--------------|---------|
| DCNT | $2230 | bit 5 | Character Conversion DMA Type (0=Normal, 1=CC DMA) |
| DCNT | $2230 | bit 7 | DMA Enable |
| CDMA | $2231 | bit 7 | CC Number of Colors (0=16, 1=2) |

**Key bit:** DCNT ($2230) bit 5 = Character Conversion DMA type selected

When bit 5 of $2230 is set (1) AND bit 7 is set (DMA enabled), the SA-1 is converting bitmap data to SNES bitplane format during DMA transfer.

## How to Run

```batch
REM From Windows, double-click or run:
run_sa1_hypothesis.bat

REM After capture completes, analyze:
uv run python scripts/analyze_sa1_hypothesis.py mesen2_exchange/sa1_hypothesis_run_*/
```

## Capture Session

**Date:** 2024-12-31
**Duration:** ~10000 frames (~2.75 minutes)
**ROM:** Kirby Super Star (USA).sfc
**Scenes Tested:**
- [x] Title screen
- [x] Character select
- [x] Gameplay with multiple enemies
- [x] Boss fights

### Log Files

- `mesen2_exchange/sa1_hypothesis_run_*/dma_probe_log.txt` - Raw SA-1 DMA data
- Look for lines: `SA1 DMA (*): ctrl=0xXX enabled=Y/N char_conv=Y/N auto=Y/N`

## Evidence

### Summary Statistics

```
Total SA-1 DMA entries: 838
Conversion ACTIVE (char_conv=Y):   838 (100.0%)
Conversion inactive (char_conv=N):   0 (0.0%)

DMA STATUS:
  enabled=Y:  838
  enabled=N:    0

TRIGGER REASONS:
  ctrl_write: 838

CTRL REGISTER VALUES:
  0xA0: 838  (enabled, CC, manual)
```

### Key Observations

1. **100% of SA-1 DMA operations use character conversion** - No exceptions observed
2. **Consistent ctrl value 0xA0** - All transfers use identical configuration:
   - Bit 7 set (0x80): DMA enabled
   - Bit 5 set (0x20): Character Conversion DMA type
   - Combined: 0xA0
3. **Manual mode only** - No auto-DMA observed (bit 4 = 0)

### Ctrl Value 0xA0 Bit Breakdown

```
0xA0 = 1010 0000
       │││└────── bits 1-0: DMA transfer mode
       ││└─────── bits 3-2: DMA source
       │└──────── bit 4: Auto mode (0=manual)
       └───────── bit 5: CC DMA type (1=character conversion)
       └───────── bit 7: DMA enable (1=enabled)
```

## Conclusion

**Hypothesis Outcome:** CONFIRMED

SA-1 character conversion is active during **100% of sprite-related DMA operations**. The 1.5% hash match rate observed during sprite extraction is fully explained by format conversion:

- **ROM data:** Bitmap format (linear pixel arrangement)
- **VRAM data:** SNES bitplane format (interleaved bit planes)

These formats are fundamentally incompatible for direct byte comparison. The SA-1 coprocessor performs real-time conversion during DMA transfer.

### Implications for Pipeline

1. **Direct hash matching will NOT work** - ROM tiles and VRAM tiles use different formats
2. **Strategy A is required** - Use timing correlation (ROM read bursts → VRAM changes)
3. **WRAM staging analysis is irrelevant** - WRAM contains pre-conversion bitmap data
4. **The 1.5% matches are likely:** UI elements, fonts, or tiles that happen to have similar byte patterns by coincidence

## Sign-off Checklist

- [x] Capture session completed (838 samples from gameplay)
- [x] Log evidence analyzed via analyze_sa1_hypothesis.py
- [x] Hypothesis outcome documented above
- [x] Next steps identified

**Approved to proceed to Phase 2:** [x] YES

**Approver:** Claude (automated analysis)
**Date:** 2024-12-31

---

## Next Steps (Strategy A Implementation)

With the SA-1 hypothesis confirmed, the pipeline should:

1. **Abandon direct hash matching** for sprite tiles
2. **Implement timing correlation:**
   - Monitor ROM read bursts (via PRG read callbacks)
   - Correlate with VRAM change windows (via VRAM diff)
   - Use temporal proximity to infer ROM→VRAM mapping
3. **Build offset database from timing data** rather than content matching
4. **Reserve hash matching for:**
   - UI elements (may not use SA-1 conversion)
   - Static assets (fonts, HUD elements)
   - Verification of non-SA1 games
