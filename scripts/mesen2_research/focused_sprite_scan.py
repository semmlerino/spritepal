#!/usr/bin/env python3
"""
Focused sprite scan using exhal around successful decompression offsets
"""

import os
import subprocess
import tempfile
from pathlib import Path


def test_exhal_decompress(rom_path: str, offset: int) -> tuple[bool, int, bytes]:
    """Test exhal decompression, return (success, size, preview_data)"""
    script_dir = Path(__file__).parent
    exhal_path = script_dir.parent / "tools" / "exhal"

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        cmd = [str(exhal_path), rom_path, f"0x{offset:X}", tmp_path]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10)

        if result.returncode == 0 and Path(tmp_path).exists():
            size = Path(tmp_path).stat().st_size
            if size > 0:
                with open(tmp_path, "rb") as f:
                    preview = f.read(64)  # First 64 bytes for analysis
                return True, size, preview

        return False, 0, b""
    except Exception:
        return False, 0, b""
    finally:
        if Path(tmp_path).exists():
            Path(tmp_path).unlink()


def analyze_sprite_data(data: bytes, size: int) -> dict:
    """Analyze decompressed data for sprite characteristics"""
    if not data:
        return {"is_sprite": False, "confidence": 0.0}

    # Check for sprite-like patterns
    non_zero = sum(1 for b in data if b != 0)
    unique_bytes = len(set(data))

    # Repeating patterns (common in sprites)
    pattern_score = 0
    if len(data) >= 4:
        for i in range(0, len(data) - 3, 2):
            if data[i : i + 2] == data[i + 2 : i + 4]:
                pattern_score += 1

    # Size analysis (sprites are typically certain sizes)
    size_score = 0
    if 1000 < size < 65000:  # Reasonable sprite size range
        size_score = min(1.0, size / 32768)  # Normalize to 32KB

    # Data density (sprites aren't all zeros or all 0xFF)
    density = non_zero / len(data) if data else 0
    density_score = 1.0 if 0.1 < density < 0.9 else 0.5

    # Tile boundary analysis (SNES sprites are 32-byte tiles in 4bpp)
    tile_score = 1.0 if size % 32 == 0 else 0.8

    confidence = (size_score + density_score + tile_score + min(1.0, pattern_score / 10)) / 4

    return {
        "is_sprite": confidence > 0.4,
        "confidence": confidence,
        "size": size,
        "tiles": size // 32,
        "density": density,
        "unique_bytes": unique_bytes,
        "patterns": pattern_score,
    }


def scan_focused_areas():
    """Scan around successful decompression offsets"""
    rom_path = os.environ.get(
        "SPRITEPAL_ROM_PATH", str(Path(__file__).resolve().parents[2] / "roms" / "Kirby Super Star (USA).sfc")
    )

    if not Path(rom_path).exists():
        print(f"Error: ROM not found: {rom_path}")
        return

    # Focus on areas where we found successful decompressions
    focus_areas = [
        # Area around 0xC0000 (successful 42KB decompression)
        (0xC0000 - 0x2000, 0xC0000 + 0x10000, "Around 0xC0000 success"),
        # Area around 0xE0000 (successful 57KB decompression)
        (0xE0000 - 0x2000, 0xE0000 + 0x10000, "Around 0xE0000 success"),
        # Extended search in promising ranges
        (0x70000, 0x90000, "Extended area 1"),
        (0xD0000, 0xF0000, "Extended area 2"),
    ]

    all_sprites = []

    for start, end, description in focus_areas:
        print(f"\n--- Scanning {description}: 0x{start:06X} - 0x{end:06X} ---")

        sprites_found = 0
        step = 0x100  # Test every 256 bytes

        for offset in range(start, end, step):
            success, size, preview = test_exhal_decompress(rom_path, offset)

            if success and size > 100:  # At least 100 bytes
                analysis = analyze_sprite_data(preview, size)

                if analysis["is_sprite"]:
                    sprites_found += 1
                    all_sprites.append((offset, analysis))

                    print(
                        f"  ✓ 0x{offset:06X}: {size:5d} bytes, {analysis['tiles']:3d} tiles, "
                        f"confidence={analysis['confidence']:.3f}"
                    )

                    # Show data preview for interesting findings
                    if analysis["confidence"] > 0.7:
                        preview_hex = " ".join(f"{b:02X}" for b in preview[:16])
                        print(f"    Preview: {preview_hex}")

        print(f"  Found {sprites_found} sprite candidates in {description}")

    # Summary of all findings
    print("\n=== SUMMARY ===")
    print(f"Total sprite candidates found: {len(all_sprites)}")

    # Sort by confidence
    all_sprites.sort(key=lambda x: x[1]["confidence"], reverse=True)

    print("\nTop sprite candidates:")
    for i, (offset, analysis) in enumerate(all_sprites[:15], 1):
        print(
            f"{i:2d}. 0x{offset:06X}: {analysis['size']:5d} bytes, "
            f"{analysis['tiles']:3d} tiles, confidence={analysis['confidence']:.3f}"
        )

    # Export for integration with existing tools
    if all_sprites:
        output_file = "discovered_sprite_offsets.txt"
        with open(output_file, "w") as f:
            f.write("# Sprite offsets discovered using exhal validation\n")
            f.write("# Format: offset size tiles confidence\n\n")

            for offset, analysis in all_sprites:
                if analysis["confidence"] > 0.5:  # Only export high-confidence candidates
                    f.write(
                        f"0x{offset:06X}  # {analysis['size']} bytes, "
                        f"{analysis['tiles']} tiles, score={analysis['confidence']:.3f}\n"
                    )

        print(f"\n✓ High-confidence sprites exported to: {output_file}")

        # Show integration with Mesen2 findings
        print("\n--- INTEGRATION OPPORTUNITIES ---")
        print(f"• Found {len([s for s in all_sprites if s[1]['confidence'] > 0.7])} high-confidence sprites")
        print("• Can now correlate these ROM offsets with Mesen2 VRAM transfer timing")
        print("• Use these offsets with existing ROMExtractor for validation")


if __name__ == "__main__":
    scan_focused_areas()
