# 03 Game Mapping: Kirby Super Star (SA-1)

This document is **game-specific**. Do not generalize these assumptions to other SNES titles.

## Cartridge / CPU
- Kirby Super Star uses the **SA-1** coprocessor.
- ROM mapping for banks $C0-$FF commonly maps to ROM space, but **SA-1 mapping registers can
  change behavior**. Treat mapping formulas as conditional unless verified by probes.

## Decompression Pipeline (Observed)
```
ROM (HAL compressed) → SA-1 CPU decompresses → WRAM buffer → DMA → VRAM
```
- Main CPU callbacks do **not** see SA-1 decompression.
- DMA typically shows **WRAM→VRAM**, not ROM→VRAM.

## SA-1 Character Conversion (Risk)
SA-1 supports a character conversion DMA mode that can transform bitmap data into SNES
bitplane tiles on the fly (registers around $2230/$2240). If active, **VRAM tile bytes
will not match ROM-decompressed bytes**, and hash mapping will fail until this is detected.

## Known Sprite Offsets (Kirby Super Star)
These match the default tile DB (`TileHashDatabase.KNOWN_SPRITE_OFFSETS`):
- 0x1B0000: Kirby sprites
- 0x1A0000: Enemy sprites
- 0x180000: Items/UI graphics
- 0x190000: Background tiles
- 0x1C0000: Background gradients
- 0x280000: Additional sprites
- 0x0E0000: Title screen/fonts

## Tooling Assumptions
- Uses HAL decompression via `core/hal_compression.py`.
- Current pipeline assumes **4bpp** sprite tiles (32 bytes).
- ROM offsets assume a **headerless** ROM image. If the file has a 512-byte copier
  header, offsets shift by `0x200` and must be adjusted or stripped.
  - Tile DB build now auto-adjusts for SMC headers and stores the header offset in metadata;
    rebuild the DB if you switch ROM files.

## Caveats
- SA-1 ROM address mapping can vary by configuration; validate against `emu.cpuType.sa1` probes
  before trusting bank-based calculations.
- DMA source addresses may be incomplete if only low 16 bits are captured.
- Verify ROM revision/CRC when results look implausible; offsets are not portable across variants.

## Golden Test (Create Once Mapping Works)
Define a single capture (savestate + frame) that reliably maps to a known offset, and record:
- Capture file path
- Expected ROM offset(s)
- ROM hash (CRC32 or SHA1)
Keep this as a regression sanity check before expanding the DB.
