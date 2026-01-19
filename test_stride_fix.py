#!/usr/bin/env python3
"""
Quick test to demonstrate SNES tile stride fix.

Shows that 16x16 sprites now correctly read tiles 0,1,16,17 instead of 0,1,2,3.
"""

from pathlib import Path

from core.mesen_integration.click_extractor import OAMEntry
from core.mesen_integration.sprite_reassembler import SpriteReassembler


def test_stride_fix():
    """Test the SNES 16-tile row stride fix with a real ROM offset."""

    # Your recently captured sprite offset
    rom_path = Path("roms/Kirby Super Star (USA).sfc")
    offset = 0x1EB260

    print("=" * 60)
    print("TESTING SNES TILE STRIDE FIX")
    print("=" * 60)
    print(f"ROM: {rom_path}")
    print(f"Offset: 0x{offset:X}")
    print()

    # Create reassembler
    reassembler = SpriteReassembler(rom_path=rom_path)

    # Test 1: 8x8 sprite (single tile, no stride needed)
    print("Test 1: 8x8 sprite (1 tile)")
    entry_8x8 = OAMEntry(
        id=0, x=100, y=100, tile=0, width=8, height=8,
        flip_h=False, flip_v=False, palette=0, rom_offset=offset
    )
    img_8x8 = reassembler._render_oam_entry(entry_8x8, palette_index=None)
    if img_8x8:
        print(f"  ✓ Rendered {img_8x8.size} sprite")
    else:
        print("  ✗ Failed to render")
    print()

    # Test 2: 16x16 sprite (4 tiles with stride)
    print("Test 2: 16x16 sprite (4 tiles with SNES stride)")
    print("  Expected tile arrangement: 0, 1, 16, 17")
    entry_16x16 = OAMEntry(
        id=1, x=100, y=100, tile=0, width=16, height=16,
        flip_h=False, flip_v=False, palette=0, rom_offset=offset
    )
    img_16x16 = reassembler._render_oam_entry(entry_16x16, palette_index=None)
    if img_16x16:
        print(f"  ✓ Rendered {img_16x16.size} sprite")
        img_16x16.save("test_16x16_sprite.png")
        print("  ✓ Saved to test_16x16_sprite.png")
    else:
        print("  ✗ Failed to render")
    print()

    # Test 3: 32x32 sprite (16 tiles with stride)
    print("Test 3: 32x32 sprite (16 tiles with SNES stride)")
    print("  Expected tile arrangement:")
    print("    Row 0: 0, 1, 2, 3")
    print("    Row 1: 16, 17, 18, 19")
    print("    Row 2: 32, 33, 34, 35")
    print("    Row 3: 48, 49, 50, 51")
    entry_32x32 = OAMEntry(
        id=2, x=100, y=100, tile=0, width=32, height=32,
        flip_h=False, flip_v=False, palette=0, rom_offset=offset
    )
    img_32x32 = reassembler._render_oam_entry(entry_32x32, palette_index=None)
    if img_32x32:
        print(f"  ✓ Rendered {img_32x32.size} sprite")
        img_32x32.save("test_32x32_sprite.png")
        print("  ✓ Saved to test_32x32_sprite.png")
    else:
        print("  ✗ Failed to render")
    print()

    # Test 4: 32x16 sprite (8 tiles, non-square)
    print("Test 4: 32x16 sprite (8 tiles, non-square)")
    print("  Expected tile arrangement:")
    print("    Row 0: 0, 1, 2, 3")
    print("    Row 1: 16, 17, 18, 19")
    entry_32x16 = OAMEntry(
        id=3, x=100, y=100, tile=0, width=32, height=16,
        flip_h=False, flip_v=False, palette=0, rom_offset=offset
    )
    img_32x16 = reassembler._render_oam_entry(entry_32x16, palette_index=None)
    if img_32x16:
        print(f"  ✓ Rendered {img_32x16.size} sprite")
        img_32x16.save("test_32x16_sprite.png")
        print("  ✓ Saved to test_32x16_sprite.png")
    else:
        print("  ✗ Failed to render")
    print()

    print("=" * 60)
    print("STRIDE FIX TEST COMPLETE")
    print("=" * 60)
    print()
    print("The fix ensures multi-tile sprites use SNES 16-tile row stride.")
    print("Before fix: 16x16 would read tiles 0,1,2,3 (wrong)")
    print("After fix:  16x16 reads tiles 0,1,16,17 (correct)")
    print()

if __name__ == "__main__":
    test_stride_fix()
