# 04 Troubleshooting

This is a fail-fast diagnostic flow. **Do not expand the tile DB or relax filters** until
VRAM capture integrity is verified.

## Fail-Fast Checks (Required)
1. **Tile bytes complete**: `data_hex` length is 64 hex chars (32 bytes).
2. **Odd bytes non-zero**: if every odd byte is zero, abort capture (bad VRAM reads).
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

### Symptom: Hash hits exist but no ROM offsets score
- Likely causes:
  - Only low-information tiles matched (weights are zero by design)
  - Tiles match many offsets (collisions) so scores never separate
  - DB coverage mismatch (correct capture, wrong source blocks indexed)
  - SA-1 character conversion active (VRAM tiles not equal to ROM-decompressed bytes)
- Fix:
  - Compare `matched_tiles` vs `scored_tiles`
  - Check unique-byte distribution and odd-byte sanity for the capture
  - Expand the tile DB with offsets from the relevant state
  - Verify the ROM header/CRC and capture timing (e.g., later frames)

### Symptom: Callbacks never fire in headless mode
- Likely causes:
  - Callback type value wrong for current build
  - Wrong parameter order / missing cpuType/memType
- Fix:
  - Re-run the probe and log firing counts

### Symptom: Testrunner stalls after `emu.loadSavestate()`
- Likely cause: loadstate must be executed from an exec callback in this build
- Fix: register exec callback, load from there, then re-register frame callbacks

### Symptom: Matches exist but sprites are mirrored
- Likely cause: flip normalization disabled
- Fix: ensure lookup includes N/H/V/HV flips

## Guardrail
If capture tiles are invalid (half-zero or wrong length), **stop** and fix capture first.
Any downstream matching work is wasted until capture integrity is restored.
