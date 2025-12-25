"""
Comprehensive sprite finder that scans ROMs for actual character sprites
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from core.region_analyzer import EmptyRegionConfig, EmptyRegionDetector

if TYPE_CHECKING:
    from core.rom_extractor import ROMExtractor

from core.sprite_visual_validator import SpriteVisualValidator
from core.tile_renderer import TileRenderer
from core.types import SpriteInfo
from utils.constants import (
    BYTES_PER_TILE,
    DEFAULT_TILES_PER_ROW,
    LARGE_SPRITE_MAX,
    MAX_SPRITE_SIZE,
    MIN_SPRITE_SIZE,
    MIN_SPRITE_TILES,
    ROM_SCAN_STEP_DEFAULT,
    ROM_SPRITE_AREA_1_START,
    normalize_address,
)
from utils.logging_config import get_logger
from utils.rom_utils import detect_smc_offset

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

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
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


@dataclass
class ScanResult:
    """Result from scanning a single offset for a sprite.

    This is the unified result type used by scan_offset() to provide
    consistent validation across sequential and parallel finders.
    """
    offset: int
    compressed_size: int
    decompressed_size: int
    tile_count: int
    confidence: float
    tile_validation_score: float
    visual_metrics: dict[str, float] | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for metadata/serialization."""
        return {
            "offset": self.offset,
            "offset_hex": f"0x{self.offset:X}",
            "compressed_size": self.compressed_size,
            "decompressed_size": self.decompressed_size,
            "tile_count": self.tile_count,
            "confidence": round(self.confidence, 3),
            "tile_validation_score": round(self.tile_validation_score, 3),
            "visual_metrics": {k: round(v, 3) for k, v in self.visual_metrics.items()}
                             if self.visual_metrics else None
        }

    def to_sprite_candidate(self, preview_path: str | None = None) -> SpriteCandidate:
        """Convert to SpriteCandidate for API compatibility."""
        return SpriteCandidate(
            offset=self.offset,
            compressed_size=self.compressed_size,
            decompressed_size=self.decompressed_size,
            tile_count=self.tile_count,
            confidence=self.confidence,
            visual_metrics=self.visual_metrics or {},
            preview_path=preview_path
        )


class SpriteFinder:
    """Finds actual character sprites in ROM files"""

    def __init__(
        self,
        output_dir: str = "sprite_candidates",
        region_config: EmptyRegionConfig | None = None,
        *,
        rom_extractor: ROMExtractor | None = None,
    ) -> None:
        if rom_extractor is None:
            from core.app_context import get_app_context

            rom_extractor = get_app_context().rom_extractor

        self.extractor = rom_extractor
        self.validator = SpriteVisualValidator()
        self.tile_renderer = TileRenderer()
        self.output_dir = output_dir
        self.region_detector = EmptyRegionDetector(region_config)

        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    def _quick_sprite_check(self, rom_data: bytes, offset: int) -> bool:
        """
        Quick heuristic check to filter definite non-sprites.

        This is a minimal filter that only rejects offsets that CANNOT contain
        valid HAL-compressed data. Previous implementation was too aggressive
        and rejected valid sprites. Now we let decompression validation catch
        invalid data instead of over-filtering here.

        Args:
            rom_data: ROM data bytes
            offset: Offset to check

        Returns:
            True if offset might contain a sprite, False if definitely not
        """
        # Need at least 4 bytes to attempt decompression
        if offset + 4 > len(rom_data):
            return False

        # Only check first 4 bytes for definite non-starters
        header = rom_data[offset:offset + 4]

        # 0xFF is the HAL stream terminator - can't be first byte
        if header[0] == 0xFF:
            return False

        # All zeros - no valid HAL command starts with 0x00
        if all(b == 0 for b in header):
            return False

        # Let decompression validation handle everything else
        # Previous checks (unique bytes < 4, ASCII patterns) were too aggressive
        # and rejected valid compressed data with low entropy headers
        return True

    def _calculate_quick_confidence(
        self,
        decompressed_size: int,
        compressed_size: int,
        tile_count: int,
        tile_validation_score: float
    ) -> float:
        """
        Calculate confidence score without visual validation.

        Uses structural factors to estimate sprite validity. This provides
        a consistent confidence calculation for both sequential and parallel
        finders when full visual validation is not performed.

        Args:
            decompressed_size: Size of decompressed sprite data
            compressed_size: Size of compressed data in ROM
            tile_count: Number of tiles in sprite
            tile_validation_score: Score from tile data validation (0.0-1.0)

        Returns:
            Confidence score between 0.0 and 1.0
        """
        score = 0.0

        # Factor 1: Size reasonableness (30%)
        if MIN_SPRITE_SIZE <= decompressed_size <= MAX_SPRITE_SIZE:
            score += 0.3

        # Factor 2: Compression ratio (20%)
        if compressed_size > 0:
            ratio = compressed_size / decompressed_size
            if 0.1 <= ratio <= 0.7:
                score += 0.2

        # Factor 3: Tile count (20%)
        if 4 <= tile_count <= 512:
            score += 0.2

        # Factor 4: Tile validation score (30%)
        # Scale tile_validation_score (0.0-1.0) to contribute up to 0.3
        score += tile_validation_score * 0.3

        return min(score, 1.0)

    def scan_offset(
        self,
        rom_data: bytes,
        offset: int,
        quick_check: bool = True,
        full_visual_validation: bool = False,
        min_tile_confidence: float = 0.4
    ) -> ScanResult | None:
        """
        Unified offset scanning pipeline.

        This is the canonical method for checking a single offset for a sprite.
        Both sequential scanning (find_sprites_in_rom) and parallel scanning
        (ParallelSpriteFinder) should use this method to ensure consistent
        validation behavior.

        Args:
            rom_data: ROM data bytes
            offset: Offset to scan
            quick_check: Whether to apply pre-decompression heuristics
            full_visual_validation: Whether to generate image and run visual validation
            min_tile_confidence: Minimum tile validation confidence to accept

        Returns:
            ScanResult if valid sprite found, None otherwise
        """
        # Step 1: Pre-decompression heuristic (fast filter)
        if quick_check and not self._quick_sprite_check(rom_data, offset):
            return None

        # Step 2: Try decompression
        try:
            # Use ROMExtractor's rom_injector
            compressed_size, sprite_data = self.extractor.rom_injector.find_compressed_sprite(
                rom_data, offset, expected_size=None
            )
            if len(sprite_data) == 0:
                return None
        except Exception:
            return None

        # Step 3: Tile count validation
        tile_count = len(sprite_data) // BYTES_PER_TILE
        if tile_count < MIN_SPRITE_TILES or tile_count > LARGE_SPRITE_MAX:
            return None

        # Step 4: Tile data validation
        is_valid, tile_confidence = self.validator.validate_tile_data(
            sprite_data, tile_count
        )
        if not is_valid or tile_confidence < min_tile_confidence:
            return None

        # Step 5: Calculate confidence
        if full_visual_validation:
            # Run full visual validation (expensive)
            visual_metrics, final_confidence = self._run_visual_validation(
                sprite_data, tile_confidence
            )
        else:
            # Calculate confidence from structural data only
            visual_metrics = None
            final_confidence = self._calculate_quick_confidence(
                decompressed_size=len(sprite_data),
                compressed_size=compressed_size,
                tile_count=tile_count,
                tile_validation_score=tile_confidence
            )

        return ScanResult(
            offset=offset,
            compressed_size=compressed_size,
            decompressed_size=len(sprite_data),
            tile_count=tile_count,
            confidence=final_confidence,
            tile_validation_score=tile_confidence,
            visual_metrics=visual_metrics
        )

    def _run_visual_validation(
        self,
        sprite_data: bytes,
        tile_confidence: float
    ) -> tuple[dict[str, float] | None, float]:
        """
        Run full visual validation pipeline.

        Converts sprite data to image and runs visual metrics analysis.

        Args:
            sprite_data: Decompressed sprite data
            tile_confidence: Confidence from tile validation

        Returns:
            Tuple of (visual_metrics dict, final confidence score)
        """
        temp_image_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                temp_image_path = tmp.name

            self._convert_to_png(sprite_data, temp_image_path)

            is_valid, confidence, metrics = self.validator.validate_sprite_image(
                temp_image_path
            )

            if is_valid:
                return metrics, confidence
            else:
                return None, tile_confidence * 0.5  # Penalize failed visual validation

        except Exception:
            return None, tile_confidence
        finally:
            if temp_image_path and Path(temp_image_path).exists():
                Path(temp_image_path).unlink(missing_ok=True)

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

        # Read ROM data, stripping SMC header if present
        with Path(rom_path).open("rb") as f:
            rom_data = f.read()

        # Detect and strip SMC header
        smc_offset = detect_smc_offset(rom_data)
        if smc_offset > 0:
            logger.info(f"Stripping {smc_offset}-byte SMC header from ROM data")
            rom_data = rom_data[smc_offset:]

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
        skipped_duplicates = 0

        # Track found sprite ranges to avoid duplicates (LOC-2.2c fix)
        # When we find a sprite at offset X with compressed size Y,
        # offsets in [X, X+Y) are part of the same compressed block
        found_ranges: list[tuple[int, int]] = []

        def is_in_found_range(check_offset: int) -> bool:
            """Check if offset falls within any previously found sprite."""
            return any(start <= check_offset < end for start, end in found_ranges)

        logger.info(f"Scanning {total_offsets} offsets...")

        # Scan through ROM
        for offset in scan_offsets:
            processed += 1

            # Skip offsets within already-found sprites to avoid duplicates
            if is_in_found_range(offset):
                skipped_duplicates += 1
                continue

            # Progress update every 1000 offsets
            if processed % 1000 == 0:
                progress = (processed / total_offsets) * 100
                logger.info(f"Progress: {progress:.1f}% ({processed}/{total_offsets}), found {found_count} candidates, skipped {skipped_duplicates} duplicates")

            # Try to decompress at this offset
            compressed_size = 0
            sprite_data = b""
            try:
                # Use ROMExtractor's rom_injector
                compressed_size, sprite_data = self.extractor.rom_injector.find_compressed_sprite(
                    rom_data, offset, expected_size=None
                )

                if len(sprite_data) == 0:
                    continue

                # Quick validation of tile data
                tile_count = len(sprite_data) // BYTES_PER_TILE
                if tile_count < MIN_SPRITE_TILES or tile_count > LARGE_SPRITE_MAX:  # Reasonable sprite size
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

                        # Track this sprite's range to prevent duplicate detection
                        # at nearby offsets within the same compressed block
                        if compressed_size > 0:
                            found_ranges.append((offset, offset + compressed_size))
                            logger.debug(
                                f"Marking range 0x{offset:06X}-0x{offset + compressed_size:06X} "
                                "as found to prevent duplicates"
                            )

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
        """Convert raw tile data to PNG image using TileRenderer."""
        # Calculate dimensions
        num_tiles = len(tile_data) // BYTES_PER_TILE
        if num_tiles == 0:
            return

        width_tiles = DEFAULT_TILES_PER_ROW
        height_tiles = (num_tiles + width_tiles - 1) // width_tiles

        # Render using TileRenderer (palette_index=None for grayscale)
        image = self.tile_renderer.render_tiles(
            tile_data, width_tiles, height_tiles, palette_index=None
        )
        if image is not None:
            # Convert to grayscale and save
            image.convert("L").save(output_path, "PNG")

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

    def find_sprite_at_offset(self, rom_data: bytes, offset: int) -> SpriteInfo | None:
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
            # Use ROMExtractor's rom_injector
            compressed_size, sprite_data = self.extractor.rom_injector.find_compressed_sprite(
                rom_data, offset, expected_size=None
            )

            if len(sprite_data) == 0:
                return None

            # Quick validation of tile data
            tile_count = len(sprite_data) // BYTES_PER_TILE
            if tile_count < MIN_SPRITE_TILES or tile_count > LARGE_SPRITE_MAX:  # Reasonable sprite size
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

    def check_offset_for_sprite(self, rom_path: str, offset: int) -> SpriteInfo | None:
        """
        Check if a specific ROM file offset contains valid sprite data.

        This method provides the missing interface needed for external validation
        of ROM offsets discovered by other tools (like Lua scripts).

        Automatically handles SNES address to file offset conversion for
        addresses that look like emulator addresses (e.g., $808000).

        Args:
            rom_path: Path to ROM file
            offset: ROM file offset or SNES address to check

        Returns:
            Sprite info dict if valid sprite found, None otherwise
        """
        try:
            rom_file = Path(rom_path)
            rom_size = rom_file.stat().st_size

            # Normalize address (handles SNES->file conversion and SMC headers)
            file_offset = normalize_address(offset, rom_size)

            with rom_file.open('rb') as f:
                rom_data = f.read()

            logger.debug(
                f"Checking offset: input=0x{offset:06X} -> file=0x{file_offset:06X}"
            )
            return self.find_sprite_at_offset(rom_data, file_offset)
        except Exception as e:
            logger.warning(f"Failed to check offset 0x{offset:06X}: {e}")
            return None
