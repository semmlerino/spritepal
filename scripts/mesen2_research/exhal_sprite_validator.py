#!/usr/bin/env python3
"""
Exhal-based sprite validation system
Uses exhal tool to validate sprite offsets by attempting decompression
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

# Known ROM sprite areas from constants.py
ROM_SPRITE_AREAS = [
    (0x80000, 0x100000),  # Area 1
    (0x100000, 0x180000),  # Area 2
    (0x180000, 0x200000),  # Area 3
    (0x200000, 0x280000),  # Area 4
    (0x280000, 0x300000),  # Area 5
]


class DecompressionResult(NamedTuple):
    """Result of exhal decompression attempt"""

    offset: int
    success: bool
    size: int
    error_message: str | None = None
    data_preview: bytes | None = None


@dataclass
class SpriteCandidate:
    """Validated sprite candidate"""

    rom_offset: int
    decompressed_size: int
    complexity_score: float
    tile_estimate: int
    data_preview: str


class ExhalSpriteValidator:
    """Validates sprite offsets using exhal decompression"""

    def __init__(self, rom_path: str):
        self.rom_path = Path(rom_path)
        # Use absolute path to exhal tool
        script_dir = Path(__file__).parent
        self.exhal_path = script_dir.parent / "tools" / "exhal"

        if not self.rom_path.exists():
            raise FileNotFoundError(f"ROM not found: {rom_path}")
        if not self.exhal_path.exists():
            raise FileNotFoundError(f"exhal tool not found: {self.exhal_path}")

        print(f"Using exhal tool: {self.exhal_path}")
        print(f"Using ROM file: {self.rom_path}")

    def test_decompression(self, offset: int) -> DecompressionResult:
        """Test decompression at specific ROM offset using exhal"""
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            # Run exhal: romfile offset outfile
            cmd = [str(self.exhal_path), str(self.rom_path), f"0x{offset:X}", tmp_path]

            result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10)

            if result.returncode == 0 and Path(tmp_path).exists():
                # Successfully decompressed
                with open(tmp_path, "rb") as f:
                    data = f.read()

                return DecompressionResult(
                    offset=offset, success=True, size=len(data), data_preview=data[:64] if data else None
                )
            # Decompression failed
            error_msg = result.stderr.strip() if result.stderr else f"Return code: {result.returncode}"
            return DecompressionResult(offset=offset, success=False, size=0, error_message=error_msg)

        except subprocess.TimeoutExpired:
            return DecompressionResult(offset=offset, success=False, size=0, error_message="Timeout")
        except Exception as e:
            return DecompressionResult(offset=offset, success=False, size=0, error_message=str(e))
        finally:
            # Clean up temp file
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()

    def analyze_sprite_data(self, data: bytes) -> tuple[float, int]:
        """
        Analyze decompressed data to estimate if it's sprite graphics
        Returns (complexity_score, estimated_tiles)
        """
        if not data:
            return 0.0, 0

        # Basic sprite data analysis
        non_zero_bytes = sum(1 for b in data if b != 0)
        zero_runs = 0
        in_zero_run = False

        # Count runs of zeros (common in sprite data)
        for byte in data:
            if byte == 0:
                if not in_zero_run:
                    zero_runs += 1
                    in_zero_run = True
            else:
                in_zero_run = False

        # Sprite graphics typically have:
        # - Mix of zero and non-zero bytes (not all zeros, not all 0xFF)
        # - Reasonable data density
        # - Multiple zero runs (between sprite tiles)

        if len(data) == 0:
            complexity = 0.0
        else:
            density = non_zero_bytes / len(data)
            if density < 0.01 or density > 0.95:
                complexity = 0.1  # Too empty or too full
            else:
                complexity = min(1.0, density * 2 + zero_runs / (len(data) / 100))

        # Estimate tiles (SNES sprites are typically 32 bytes per 8x8 tile in 4bpp)
        estimated_tiles = len(data) // 32

        return complexity, estimated_tiles

    def scan_rom_area(self, start_offset: int, end_offset: int, step: int = 0x100) -> list[SpriteCandidate]:
        """Scan a ROM area for valid sprite offsets"""
        print(f"Scanning ROM area: 0x{start_offset:06X} - 0x{end_offset:06X}")

        candidates = []
        total_attempts = (end_offset - start_offset) // step
        successful_decompressions = 0

        for i, offset in enumerate(range(start_offset, end_offset, step)):
            if i % 50 == 0:
                progress = (i * 100) // total_attempts
                print(f"  Progress: {progress}% (offset 0x{offset:06X})")

            result = self.test_decompression(offset)

            if result.success and result.size > 32:  # At least 1 tile worth
                successful_decompressions += 1

                # Analyze the decompressed data
                complexity, tiles = self.analyze_sprite_data(result.data_preview or b"")

                if complexity > 0.2 and tiles > 0:  # Looks like sprite data
                    # Create preview string
                    preview = ""
                    if result.data_preview:
                        preview = " ".join(f"{b:02X}" for b in result.data_preview[:16])

                    candidate = SpriteCandidate(
                        rom_offset=offset,
                        decompressed_size=result.size,
                        complexity_score=complexity,
                        tile_estimate=tiles,
                        data_preview=preview,
                    )
                    candidates.append(candidate)

                    print(f"  ✓ Found sprite candidate at 0x{offset:06X} ({result.size} bytes, {tiles} tiles)")

        print(
            f"  Scan complete: {successful_decompressions} successful decompressions, {len(candidates)} sprite candidates"
        )
        return candidates

    def validate_all_areas(self, step: int = 0x100) -> dict[tuple[int, int], list[SpriteCandidate]]:
        """Validate all known ROM sprite areas"""
        print("Starting comprehensive sprite validation using exhal...")

        all_results = {}
        total_candidates = 0

        for start, end in ROM_SPRITE_AREAS:
            print(f"\n--- Scanning Area: 0x{start:06X} - 0x{end:06X} ---")
            candidates = self.scan_rom_area(start, end, step)
            all_results[(start, end)] = candidates
            total_candidates += len(candidates)

        print("\n=== VALIDATION SUMMARY ===")
        print(f"Total sprite candidates found: {total_candidates}")

        # Show top candidates
        all_candidates = []
        for candidates in all_results.values():
            all_candidates.extend(candidates)

        # Sort by complexity score
        all_candidates.sort(key=lambda c: c.complexity_score, reverse=True)

        print("\nTop 10 candidates:")
        for i, candidate in enumerate(all_candidates[:10], 1):
            print(
                f"{i:2d}. 0x{candidate.rom_offset:06X}: {candidate.decompressed_size:5d} bytes, "
                f"{candidate.tile_estimate:3d} tiles, score={candidate.complexity_score:.3f}"
            )

        return all_results

    def export_results(self, results: dict[tuple[int, int], list[SpriteCandidate]], output_file: str) -> None:
        """Export results to file for use with existing extraction tools"""
        with open(output_file, "w") as f:
            f.write("# Exhal-Validated Sprite Offsets for Kirby Super Star\n")
            f.write("# Generated using exhal tool validation\n")
            f.write(f"# ROM: {self.rom_path}\n\n")

            total_candidates = sum(len(candidates) for candidates in results.values())
            f.write(f"# Total candidates found: {total_candidates}\n\n")

            for (start, end), candidates in results.items():
                f.write(f"# Area 0x{start:06X} - 0x{end:06X}: {len(candidates)} candidates\n")

                f.writelines(
                    f"0x{candidate.rom_offset:06X}  # {candidate.decompressed_size} bytes, "
                    f"{candidate.tile_estimate} tiles, score={candidate.complexity_score:.3f}\n"
                    for candidate in sorted(candidates, key=lambda c: c.rom_offset)
                )
                f.write("\n")


def main():
    """Test the exhal sprite validator"""
    rom_path = "Kirby Super Star (USA).sfc"

    if not Path(rom_path).exists():
        print(f"Error: ROM file not found: {rom_path}")
        return 1

    validator = ExhalSpriteValidator(rom_path)

    # Test a small area first
    print("Testing exhal validation on a small ROM section...")
    test_candidates = validator.scan_rom_area(0x80000, 0x81000, step=0x100)  # 4KB test

    if test_candidates:
        print(f"\n✓ Test successful - found {len(test_candidates)} candidates in test area")

        # Run full validation
        print("\nRunning full validation (this may take several minutes)...")
        all_results = validator.validate_all_areas(step=0x200)  # 512-byte steps for speed

        # Export results
        output_file = "exhal_validated_sprites.txt"
        validator.export_results(all_results, output_file)
        print(f"\n✓ Results exported to: {output_file}")

        return 0
    print("✗ Test failed - no sprite candidates found")
    return 1


if __name__ == "__main__":
    sys.exit(main())
