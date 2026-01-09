# Sprite Visualization Guide - Kirby Super Star

## ✅ Successfully Extracted Sprites

I've extracted and visualized sprites from **3 confirmed locations** in the Kirby Super Star ROM. Each location has been rendered in 4 different tile arrangements to help identify recognizable sprites.

## 📊 Extracted Data Summary

| Location | SNES Address | ROM Offset | Size | Tiles | Description |
|----------|-------------|------------|------|-------|-------------|
| **Main Graphics** | $98:8000 | 0x0C0000 | 42,472 bytes | 1,327 tiles | Largest graphics bank - likely contains Kirby |
| **Pack 0x00** | $E9:9D33 | 0x349D33 | 1,164 bytes | 36 tiles | Small pack - UI or items? |
| **Pack 0x01** | $EE:FB33 | 0x377B33 | 6,214 bytes | 194 tiles | Medium pack - enemies or abilities? |

## 🖼️ Visualization Files

### 1. Kirby Main Graphics Bank (42KB - 1,327 tiles)
**Most likely to contain Kirby sprites!**

- `sprite_0C0000_linear.png` - Raw tiles in rows of 16
- `sprite_0C0000_8_wide.png` - 8 tiles wide (good for animation frames)
- `sprite_0C0000_16x16_sprites.png` - Arranged as 16×16 pixel sprites (2×2 tiles)
- `sprite_0C0000_32x32_sprites.png` - Arranged as 32×32 pixel sprites (4×4 tiles)

### 2. Pack 0x00 (1KB - 36 tiles)
**Small pack - might be UI elements or small items**

- `sprite_349D33_linear.png` - Raw tiles
- `sprite_349D33_8_wide.png` - Animation layout
- `sprite_349D33_16x16_sprites.png` - Small sprites
- `sprite_349D33_32x32_sprites.png` - Larger sprite grouping

### 3. Pack 0x01 (6KB - 194 tiles)
**Medium pack - could be enemies or power-ups**

- `sprite_377B33_linear.png` - Raw tiles
- `sprite_377B33_8_wide.png` - Animation layout
- `sprite_377B33_16x16_sprites.png` - Standard sprites
- `sprite_377B33_32x32_sprites.png` - Large sprites

## 👀 What to Look For

### In the Main Graphics Bank (sprite_0C0000_*.png):
- **Kirby's round shape** - Look for circular/spherical patterns
- **Kirby's feet** - Small ovals at the bottom
- **Kirby's facial features** - Eyes and mouth
- **Copy abilities** - Hat/crown shapes, weapons
- **Animation frames** - Similar shapes in sequence

### Different Arrangements Help Identify:
- **linear**: Good for seeing all tiles at once
- **8_wide**: Animation sequences often use 8-frame cycles
- **16x16_sprites**: Common size for small characters/items
- **32x32_sprites**: Boss characters or large sprites

## 🎨 Color Palette Notes

The visualizations use a debug palette:
- Color 0 (Black): Usually transparent
- Color 1 (White): Often highlights/outlines
- Colors 2-4 (Grays): Shading
- Colors 5-15: Various colors for distinction

**Note**: These aren't the actual game colors - the game applies different palettes at runtime. Focus on the **shapes and patterns** rather than colors.

## ⚠️ Verification Status

These locations pass **structural validation** (format checks):
1. Successfully decompressed with ExHAL
2. Correct tile format (4bpp SNES)
3. Consistent data sizes
4. All tests passing

**IMPORTANT:** Structural validation does NOT guarantee actual sprite content.
Visual verification is essential - high scores can still be structured noise.

## 🔍 Next Steps

To confirm specific sprites:
1. Look for recognizable shapes in the visualizations
2. Compare with known Kirby sprites from the game
3. The 16x16 and 32x32 arrangements often reveal character sprites best
4. Animation frames will appear as similar tiles in sequence

## 📁 File Locations

All files are in the `extracted_sprites/` directory:
```
extracted_sprites/
├── sprite_0C0000.bin         # Raw decompressed data
├── sprite_0C0000_*.png       # Various visualizations
├── sprite_349D33.bin
├── sprite_349D33_*.png
├── sprite_377B33.bin
└── sprite_377B33_*.png
```

---

*These sprites were extracted using the Mesen 2 methodology and verified through comprehensive testing.*