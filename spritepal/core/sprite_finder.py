"""
Comprehensive sprite finder that scans ROMs for actual character sprites
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from core.region_analyzer import EmptyRegionConfig, EmptyRegionDetector
from core.rom_extractor import ROMExtractor
from core.sprite_visual_validator import SpriteVisualValidator
from utils.constants import (
    BYTES_PER_TILE,
    ROM_SCAN_STEP_DEFAULT,
    ROM_SCAN_STEP_QUICK,
    ROM_SPRITE_AREA_1_END,
    ROM_SPRITE_AREA_1_START,
    ROM_SPRITE_AREA_2_END,
    ROM_SPRITE_AREA_2_START,
    ROM_SPRITE_AREA_3_END,
    ROM_SPRITE_AREA_3_START,
    ROM_SPRITE_AREA_4_END,
    ROM_SPRITE_AREA_4_START,
    ROM_SPRITE_AREA_5_END,
    ROM_SPRITE_AREA_5_START,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)

@dataclass
class SpriteCandidate:
    """Represents a potential sprite found in ROM"""
    offset: int
    compressed_size: int
    decompressed_size: int
    tile_count: int
    confidence: float
    visual_metrics: dict[str, float]
    preview_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "offset": f"0x{self.offset:06X}",
            "offset_int": self.offset,
            "compressed_size": self.compressed_size,
            "decompressed_size": self.decompressed_size,
            "tile_count": self.tile_count,
            "confidence": round(self.confidence, 3),
            "visual_metrics": {k: round(v, 3) for k, v in self.visual_metrics.items()},
            "preview_path": self.preview_path
        }

class SpriteFinder:
    """Finds actual character sprites in ROM files"""

    def __init__(self, output_dir: str = "sprite_candidates", region_config: EmptyRegionConfig | None = None) -> None:
        self.extractor = ROMExtractor()
        self.validator = SpriteVisualValidator()
        self.output_dir = output_dir
        self.region_detector = EmptyRegionDetector(region_config)

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

    def find_sprites_in_rom(
        self,
        rom_path: str,
        start_offset: int = ROM_SPRITE_AREA_1_START,
        end_offset: int | None = None,
        step: int = ROM_SCAN_STEP_DEFAULT,
        min_confidence: float = 0.6,
        save_previews: bool = True,
        max_candidates: int = 50,
        use_region_optimization: bool = True
    ) -> list[SpriteCandidate]:
        """
        Scan ROM for actual character sprites.

        Args:
            rom_path: Path to ROM file
            start_offset: Starting offset to scan from
            end_offset: Ending offset (None = end of ROM)
            step: Step size between scan attempts
            min_confidence: Minimum confidence to consider valid
            save_previews: Whether to save preview images
            max_candidates: Maximum number of candidates to return

        Returns:
            List of sprite candidates sorted by confidence
        """
        logger.info(f"Starting sprite search in ROM: {rom_path}")
        logger.info(f"Scan range: 0x{start_offset:06X} to {f'0x{end_offset:06X}' if end_offset else 'EOF'}")
        logger.info(f"Min confidence: {min_confidence}")

        candidates = []

        # Read ROM data
        with Path(rom_path).open("rb") as f:
            rom_data = f.read()

        rom_size = len(rom_data)
        if end_offset is None or end_offset > rom_size:
            end_offset = rom_size

        # Get scan ranges based on optimization setting
        scan_offsets = []

        if use_region_optimization:
            logger.info("Using empty region optimization for faster scanning")

            # Get optimized scan ranges
            scan_ranges = self.region_detector.get_optimized_scan_ranges(
                rom_data[start_offset:end_offset],
                min_gap_size=0x10000  # 64KB minimum gap
            )

            # Adjust ranges to absolute offsets and generate scan offsets
            for range_start, range_end in scan_ranges:
                abs_start = start_offset + range_start
                abs_end = start_offset + range_end
                for offset in range(abs_start, min(abs_end, end_offset), step):
                    scan_offsets.append(offset)

            logger.info(f"Optimized scanning: {len(scan_offsets)} offsets in {len(scan_ranges)} regions")
        else:
            # Traditional linear scanning
            scan_offsets = list(range(start_offset, end_offset, step))
            logger.info(f"Linear scanning: {len(scan_offsets)} offsets")

        # Progress tracking
        total_offsets = len(scan_offsets)
        processed = 0
        found_count = 0

        logger.info(f"Scanning {total_offsets} offsets...")

        # Scan through ROM
        for offset in scan_offsets:
            processed += 1

            # Progress update every 1000 offsets
            if processed % 1000 == 0:
                progress = (processed / total_offsets) * 100
                logger.info(f"Progress: {progress:.1f}% ({processed}/{total_offsets}), found {found_count} candidates")

            # Try to decompress at this offset
            compressed_size = 0
            sprite_data = b""
            try:
                compressed_size, sprite_data = self.extractor.rom_injector.find_compressed_sprite(
                    rom_data, offset, expected_size=None
                )

                if len(sprite_data) == 0:
                    continue

                # Quick validation of tile data
                tile_count = len(sprite_data) // BYTES_PER_TILE
                if tile_count < 16 or tile_count > 2048:  # Reasonable sprite size
                    continue

                # Quick pre-validation
                is_valid, quick_confidence = self.validator.validate_tile_data(
                    sprite_data, tile_count
                )

                if not is_valid or quick_confidence < 0.5:
                    continue

                # Convert to image for visual validation
                temp_image_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        temp_image_path = tmp.name

                    # Convert to PNG
                    self._convert_to_png(sprite_data, temp_image_path)

                    # Visual validation
                    is_valid, confidence, metrics = self.validator.validate_sprite_image(
                        temp_image_path
                    )

                    if is_valid and confidence >= min_confidence:
                        # Found a candidate!
                        logger.info(f"Found sprite candidate at 0x{offset:06X} with confidence {confidence:.3f}")

                        # Save preview if requested
                        preview_path = None
                        if save_previews:
                            preview_name = f"sprite_{offset:06X}_conf{int(confidence*100)}.png"
                            preview_path = Path(self.output_dir) / preview_name

                            # Copy temp image to preview
                            with Image.open(temp_image_path) as img:
                                img.save(str(preview_path))
                            logger.debug(f"Saved preview: {preview_path}")

                        candidate = SpriteCandidate(
                            offset=offset,
                            compressed_size=compressed_size,
                            decompressed_size=len(sprite_data),
                            tile_count=tile_count,
                            confidence=confidence,
                            visual_metrics=metrics,
                            preview_path=str(preview_path) if preview_path else None
                        )

                        candidates.append(candidate)
                        found_count += 1

                        # Stop if we have enough candidates
                        if len(candidates) >= max_candidates:
                            logger.info(f"Reached maximum candidates ({max_candidates})")
                            break

                finally:
                    # Clean up temp file
                    if temp_image_path and Path(temp_image_path).exists():
                        Path(temp_image_path).unlink(missing_ok=True)

            except Exception:
                # Decompression or validation failed, continue
                continue

        # Sort by confidence
        candidates.sort(key=lambda x: x.confidence, reverse=True)

        logger.info(f"Scan complete! Found {len(candidates)} sprite candidates")

        # Save results summary
        self._save_results_summary(rom_path, candidates)

        return candidates

    def _convert_to_png(self, tile_data: bytes, output_path: str) -> None:
        """Convert raw tile data to PNG image"""
        # Use the extractor's conversion method
        self.extractor._convert_4bpp_to_png(tile_data, output_path)

    def _save_results_summary(self, rom_path: str, candidates: list[SpriteCandidate]) -> None:
        """Save a summary of found sprites"""
        rom_name = Path(rom_path).name
        summary_path = Path(self.output_dir) / f"sprite_search_results_{rom_name}.json"

        summary = {
            "rom_file": rom_name,
            "total_candidates": len(candidates),
            "candidates": [c.to_dict() for c in candidates]
        }

        with summary_path.open("w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Saved results summary: {summary_path}")

        # Also create a simple text report
        report_path = Path(self.output_dir) / f"sprite_search_report_{rom_name}.txt"
        with report_path.open("w") as f:
            f.write(f"Sprite Search Report for {rom_name}\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Found {len(candidates)} sprite candidates\n\n")

            for i, candidate in enumerate(candidates[:20]):  # Top 20
                f.write(f"{i+1}. Offset: 0x{candidate.offset:06X}\n")
                f.write(f"   Confidence: {candidate.confidence:.1%}\n")
                f.write(f"   Size: {candidate.tile_count} tiles ({candidate.decompressed_size} bytes)\n")
                f.write(f"   Compressed: {candidate.compressed_size} bytes\n")
                f.write("   Metrics: ")
                for metric, value in candidate.visual_metrics.items():
                    f.write(f"{metric}={value:.2f} ")
                f.write("\n\n")

        logger.info(f"Saved search report: {report_path}")

    def quick_scan_known_areas(self, rom_path: str) -> list[SpriteCandidate]:
        """
        Quick scan of areas where sprites are commonly found in SNES games.
        """
        common_sprite_ranges = [
            (ROM_SPRITE_AREA_1_START, ROM_SPRITE_AREA_1_END),   # Common sprite area 1
            (ROM_SPRITE_AREA_2_START, ROM_SPRITE_AREA_2_END),  # Common sprite area 2
            (ROM_SPRITE_AREA_3_START, ROM_SPRITE_AREA_3_END),  # Common sprite area 3
            (ROM_SPRITE_AREA_4_START, ROM_SPRITE_AREA_4_END),  # Extended sprite area
            (ROM_SPRITE_AREA_5_START, ROM_SPRITE_AREA_5_END),  # Additional sprites
        ]

        all_candidates = []

        for start, end in common_sprite_ranges:
            logger.info(f"Quick scanning range 0x{start:06X}-0x{end:06X}")

            # Use larger step for quick scan
            candidates = self.find_sprites_in_rom(
                rom_path,
                start_offset=start,
                end_offset=end,
                step=ROM_SCAN_STEP_QUICK,  # Larger step for quick scan
                min_confidence=0.7,  # Higher threshold
                save_previews=True,
                max_candidates=10  # Limit per range
            )

            all_candidates.extend(candidates)

            if len(all_candidates) >= 20:
                logger.info("Found enough candidates in quick scan")
                break

        return all_candidates

    def find_sprite_at_offset(self, rom_data: bytes, offset: int) -> dict[str, Any] | None:
        """
        Try to find and validate a sprite at a specific offset.

        Args:
            rom_data: ROM data bytes
            offset: Offset to check

        Returns:
            Sprite info dict if found, None otherwise
        """
        compressed_size = 0
        sprite_data = b""
        try:
            # Try to decompress sprite at this offset
            compressed_size, sprite_data = self.extractor.rom_injector.find_compressed_sprite(
                rom_data, offset, expected_size=None
            )

            if len(sprite_data) == 0:
                return None

            # Quick validation of tile data
            tile_count = len(sprite_data) // BYTES_PER_TILE
            if tile_count < 16 or tile_count > 2048:  # Reasonable sprite size
                return None

            # Quick pre-validation
            is_valid, quick_confidence = self.validator.validate_tile_data(
                sprite_data, tile_count
            )

            if not is_valid or quick_confidence < 0.4:  # Lower threshold for single offset
                return None

            # Build sprite info dict compatible with existing interfaces
            return {
                "offset": offset,
                "offset_hex": f"0x{offset:X}",
                "compressed_size": compressed_size,
                "decompressed_size": len(sprite_data),
                "tile_count": tile_count,
                "quality": quick_confidence,
                "alignment": "perfect" if len(sprite_data) % BYTES_PER_TILE == 0 else f"{len(sprite_data) % BYTES_PER_TILE} extra bytes"
            }

        except Exception:
            # Decompression or validation failed
            return None

    def check_offset_for_sprite(self, rom_path: str, offset: int) -> dict[str, Any] | None:
        """
        Check if a specific ROM file offset contains valid sprite data.

        This method provides the missing interface needed for external validation
        of ROM offsets discovered by other tools (like Lua scripts).

        Args:
            rom_path: Path to ROM file
            offset: ROM file offset to check

        Returns:
            Sprite info dict if valid sprite found, None otherwise
        """
        try:
            with open(rom_path, 'rb') as f:
                rom_data = f.read()
            return self.find_sprite_at_offset(rom_data, offset)
        except Exception as e:
            logger.warning(f"Failed to check offset 0x{offset:06X}: {e}")
            return None
