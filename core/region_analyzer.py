"""
Empty region detection for optimized ROM scanning.
Identifies regions that can be skipped during sprite searching.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

from core.analysis_utils import (
    calculate_entropy,
    calculate_zero_percentage,
    detect_repeating_patterns,
)
from utils.constants import (
    EMPTY_REGION_ENTROPY_THRESHOLD,
    EMPTY_REGION_MAX_UNIQUE_BYTES,
    EMPTY_REGION_PATTERN_THRESHOLD,
    EMPTY_REGION_SIZE,
    EMPTY_REGION_ZERO_THRESHOLD,
    ROM_MIN_REGION_SIZE,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)


class EmptyRegionConfig(NamedTuple):
    """Configuration for empty region detection."""

    entropy_threshold: float = EMPTY_REGION_ENTROPY_THRESHOLD
    zero_threshold: float = EMPTY_REGION_ZERO_THRESHOLD
    pattern_threshold: float = EMPTY_REGION_PATTERN_THRESHOLD
    max_unique_bytes: int = EMPTY_REGION_MAX_UNIQUE_BYTES
    region_size: int = EMPTY_REGION_SIZE


@dataclass
class RegionAnalysis:
    """Result of analyzing a ROM region."""

    offset: int
    size: int
    is_empty: bool
    entropy: float
    zero_percentage: float
    unique_bytes: int
    pattern_score: float
    reason: str = ""


class EmptyRegionDetector:
    """Detects empty or non-sprite regions in ROM data for optimized scanning."""

    def __init__(self, config: EmptyRegionConfig | None = None):
        """Initialize detector with configuration."""
        self.config = config or EmptyRegionConfig()
        self._cache: dict[tuple[int, int], RegionAnalysis] = {}
        logger.info(f"EmptyRegionDetector initialized with region size: {self.config.region_size} bytes")

    def analyze_region(self, data: bytes, offset: int = 0) -> RegionAnalysis:
        """
        Analyze a region of ROM data to determine if it's empty/non-sprite.

        Args:
            data: Raw ROM data to analyze
            offset: Starting offset in ROM

        Returns:
            RegionAnalysis with detection results
        """
        # Check cache
        cache_key = (offset, len(data))
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Calculate metrics
        entropy = calculate_entropy(data)
        zero_percentage = calculate_zero_percentage(data)
        unique_bytes = len(set(data))
        pattern_score = detect_repeating_patterns(data)

        # Determine if region is empty based on thresholds
        is_empty = False
        reason = ""

        # Check each criterion
        if entropy < self.config.entropy_threshold:
            is_empty = True
            reason = f"Low entropy ({entropy:.3f} < {self.config.entropy_threshold})"
        elif zero_percentage > self.config.zero_threshold:
            is_empty = True
            reason = f"High zero percentage ({zero_percentage:.1%} > {self.config.zero_threshold:.1%})"
        elif unique_bytes <= self.config.max_unique_bytes:
            is_empty = True
            reason = f"Too few unique bytes ({unique_bytes} <= {self.config.max_unique_bytes})"
        elif pattern_score > self.config.pattern_threshold:
            is_empty = True
            reason = f"Repeating pattern detected (score: {pattern_score:.2f})"

        result = RegionAnalysis(
            offset=offset,
            size=len(data),
            is_empty=is_empty,
            entropy=entropy,
            zero_percentage=zero_percentage,
            unique_bytes=unique_bytes,
            pattern_score=pattern_score,
            reason=reason,
        )

        # Cache result
        self._cache[cache_key] = result

        return result

    def scan_rom_regions(
        self, rom_data: bytes, progress_callback: Callable[[int, int], None] | None = None
    ) -> list[tuple[int, int]]:
        """
        Scan entire ROM and return list of non-empty regions.

        Args:
            rom_data: Complete ROM data
            progress_callback: Optional callback(current, total) for progress

        Returns:
            List of (start_offset, end_offset) tuples for non-empty regions
        """
        logger.info(f"Scanning ROM ({len(rom_data):,} bytes) for empty regions")

        non_empty_regions = []
        current_region_start = None

        total_regions = (len(rom_data) + self.config.region_size - 1) // self.config.region_size
        analyzed_regions = 0
        empty_regions = 0

        for offset in range(0, len(rom_data), self.config.region_size):
            # Extract region
            region_end = min(offset + self.config.region_size, len(rom_data))
            region_data = rom_data[offset:region_end]

            # Analyze region
            analysis = self.analyze_region(region_data, offset)
            analyzed_regions += 1

            if analysis.is_empty:
                empty_regions += 1
                # If we were tracking a non-empty region, close it
                if current_region_start is not None:
                    non_empty_regions.append((current_region_start, offset))
                    current_region_start = None
            # Start new region if needed
            elif current_region_start is None:
                current_region_start = offset

            # Report progress
            if progress_callback and analyzed_regions % 100 == 0:
                progress_callback(analyzed_regions, total_regions)

        # Close final region if needed
        if current_region_start is not None:
            non_empty_regions.append((current_region_start, len(rom_data)))

        # Log statistics
        empty_percentage = (empty_regions / analyzed_regions) * 100 if analyzed_regions > 0 else 0
        logger.info(
            f"Region analysis complete: {empty_regions}/{analyzed_regions} regions empty "
            f"({empty_percentage:.1f}%), {len(non_empty_regions)} non-empty ranges found"
        )

        return non_empty_regions

    def get_optimized_scan_ranges(
        self, rom_data: bytes, min_gap_size: int = ROM_MIN_REGION_SIZE
    ) -> list[tuple[int, int]]:
        """
        Get optimized scan ranges, merging small gaps between regions.

        Args:
            rom_data: Complete ROM data
            min_gap_size: Minimum gap size to keep separate (default 4KB)

        Returns:
            List of (start, end) tuples for scanning
        """
        # Get initial non-empty regions
        regions = self.scan_rom_regions(rom_data)

        if not regions:
            return []

        # Merge regions with small gaps
        merged = []
        current_start, current_end = regions[0]

        for start, end in regions[1:]:
            gap = start - current_end

            if gap < min_gap_size:
                # Merge with current region
                current_end = end
            else:
                # Gap is large enough, keep separate
                merged.append((current_start, current_end))
                current_start, current_end = start, end

        # Add final region
        merged.append((current_start, current_end))

        logger.info(f"Optimized {len(regions)} regions into {len(merged)} scan ranges")
        return merged

    def clear_cache(self):
        """Clear the analysis cache."""
        self._cache.clear()
        logger.debug("Cleared empty region analysis cache")
