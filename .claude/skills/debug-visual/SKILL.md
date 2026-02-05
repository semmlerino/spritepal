---
name: debug-visual
description: "Step-by-step investigation of visual/rendering discrepancies (preview vs injection, color errors, alignment bugs)"
argument-hint: "[symptom description]"
disable-model-invocation: true
---

# Visual Bug Investigation Playbook

Symptom: **$ARGUMENTS**

Follow these steps in order. Stop when the root cause is identified.

## Step 1: Check Logs
Read the last 50 lines of `logs/spritepal.log`. Look for errors, warnings, or unexpected path selection.

## Step 2: Identify Rendering Path
Search logs or code for which compositor path was used:
- **INDEX-FIRST**: transforms index map with NEAREST interpolation (preferred, no artifacts)
- **LEGACY**: transforms RGBA then quantizes (Lanczos can cause fringe colors)

If the symptom is fringe/wrong colors, INDEX-FIRST path likely wasn't used — check if index_map and sheet_palette are both present.

## Step 3: Compare Pipeline Stages
For "preview doesn't match injection" bugs:
1. Verify both use the same `TransformParams` (flip, scale, offset order: Flip → Scale → Offset)
2. Check resampling mode (NEAREST for index maps, Lanczos for RGBA)
3. Verify uncovered pixel policy matches ("transparent" vs "original")

## Step 4: Capture Debug Images
Set `SPRITEPAL_INJECT_DEBUG=1` and re-run. Compare pipeline stage outputs in temp directory.

## Step 5: Verify Palette Precision
- Is `snap_to_snes_color()` applied? (5-bit per channel)
- Is `version_hash` fresh? (stale hash = stale cached previews)
- Are there duplicate palette colors? (first-match-wins during quantization)

## Step 6: Isolate with Scripts
Run standalone scripts to separate UI from compositor:
```bash
uv run python scripts/capture_quantized_preview.py      # Palette quantization
uv run python scripts/capture_sheet_palette_preview.py   # Sheet palette pipeline
uv run python scripts/render_workbench.py --use-saved    # Alignment overlay
```

## Step 7: Check Cache Invalidation
- Preview cache keyed by `(capture_id, frozenset(entry_ids))`
- Palette change should bump `version_hash` → invalidate cache
- If preview is stale, check `preview_cache_invalidated` signal emission

## Common Issues Quick Reference

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Fringe colors around edges | LEGACY path (Lanczos on RGBA) | Ensure index_map + sheet_palette available for INDEX-FIRST |
| Stale preview after palette edit | version_hash not bumped | Check `sheet_palette_changed` signal chain |
| Alignment off by pixels | Transform order wrong | Must be Flip → Scale → Offset |
| Colors slightly wrong | Missing SNES snap | Verify `snap_to_snes_color()` in quantization path |
| Preview OK but injection wrong | Different compositor params | Compare TransformParams between preview and injection calls |
| Black/missing tiles | Uncovered policy mismatch | Check "transparent" vs "original" policy setting |
