# SA-1 Conversion Hypothesis: [PENDING]

> **Status:** Awaiting capture data
> **Last Updated:** [DATE]
> **Captured By:** [NAME]

## Background

The sprite extraction pipeline assumes SA-1 character conversion explains why ROM bytes don't match VRAM bytes (1.5% hash match rate). This hypothesis must be verified before proceeding with Strategy A (VRAM-based DB with timing correlation).

### SA-1 Character Conversion Registers

| Register | Address | Purpose |
|----------|---------|---------|
| DCNT | $2230 | DMA control register |
| CDMA | $2231 | Character conversion DMA control |

**Key bit:** CDMA bit 7 = Character conversion DMA enabled

When bit 7 of $2231 is set (1), the SA-1 is converting bitmap data to SNES bitplane format during DMA transfer.

## Capture Session

**Date:** [DATE]
**Duration:** [FRAMES] frames (~[MINUTES] minutes)
**ROM:** Kirby Super Star (USA).sfc
**Scenes Tested:**
- [ ] Title screen
- [ ] Character select
- [ ] Gameplay with multiple enemies
- [ ] Boss fights

### Log Files

- `mesen2_exchange/sa1_conversion_log.csv` - Raw register data
- `mesen2_exchange/sa1_hypothesis_results.txt` - Auto-generated summary
- `mesen2_exchange/sa1_conversion_debug.txt` - Debug log

## Evidence

### Summary Statistics

```
Total samples: [COUNT]
Conversion ACTIVE:   [COUNT] ([PERCENT]%)
Conversion inactive: [COUNT] ([PERCENT]%)
```

### Key Log Excerpts

```csv
[PASTE RELEVANT EXCERPTS FROM sa1_conversion_log.csv]
```

## Conclusion

**Hypothesis Outcome:** [CONFIRMED / FALSIFIED / PARTIAL]

### If CONFIRMED (>90% active)
SA-1 character conversion is active during sprite loads. The 1.5% hash match rate is explained by format conversion from bitmap to bitplane representation.

**Action:** Proceed with Strategy A (VRAM-based DB with timing correlation).

### If FALSIFIED (<10% active)
SA-1 character conversion is NOT active. The 1.5% hash match rate must have another cause.

**Action:** STOP. Investigate alternatives:
1. **Palette remapping** - Compare tiles with palette swap applied
2. **Runtime tile composition** - Trace tile assembly in disassembly
3. **Compression variant** - Try alternate decompressors (not HAL format)
4. **Interlaced plane storage** - Test alternate bitplane ordering

### If PARTIAL (10-90% active)
SA-1 character conversion is used for SOME sprite types but not others.

**Action:**
1. Analyze CSV patterns to identify which game states use conversion
2. Modify pipeline to route sprites to appropriate strategy based on state
3. Document which sprite categories require which handling

## Sign-off Checklist

- [ ] Capture session completed (5+ minutes gameplay)
- [ ] Log evidence archived to version control
- [ ] Hypothesis outcome documented above
- [ ] Next steps identified

**Approved to proceed to Phase 2:** [ ] YES / [ ] NO

**Approver:** [NAME]
**Date:** [DATE]
