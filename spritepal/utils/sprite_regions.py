"""
Sprite region detection and management for smart ROM navigation.

This module provides intelligent grouping of sprites into navigable regions,
enabling efficient ROM exploration by filtering out empty areas.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict

from utils.constants import (
    MAX_SPRITE_COUNT_HEADER,
    MAX_SPRITE_COUNT_MAIN,
    ROM_ALIGNMENT_GAP_THRESHOLD,
    ROM_MIN_REGION_SIZE,
    ROM_SIZE_512KB,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SpriteRegion:
    """Represents a contiguous region containing sprites"""

    region_id: int
    start_offset: int
    end_offset: int
    sprite_offsets: list[int]
    sprite_qualities: list[float]
    average_quality: float
    sprite_count: int
    size_bytes: int
    density: float  # sprites per KB

    # Enhanced metadata
    confidence_score: float = 1.0  # How confident we are this is a real region
    region_type: str = "unknown"  # e.g., "characters", "backgrounds", "effects"
    is_compressed: bool = True  # Whether sprites in this region are compressed
    access_count: int = 0  # Number of times this region has been accessed
    last_accessed: float = 0.0  # Timestamp of last access
    custom_name: str | None = None  # User-defined region name
    custom_color: str | None = None  # User-defined color for visualization

    @property
    def description(self) -> str:
        """Get a human-readable description of the region"""
        if self.custom_name:
            return f"{self.custom_name} (Region {self.region_id + 1})"
        return f"Region {self.region_id + 1}: 0x{self.start_offset:06X}-0x{self.end_offset:06X} ({self.sprite_count} sprites)"

    @property
    def center_offset(self) -> int:
        """Get the center offset of the region for initial positioning"""
        return (self.start_offset + self.end_offset) // 2

    @property
    def quality_category(self) -> str:
        """Categorize region by average quality"""
        if self.average_quality > 0.8:
            return "high"
        if self.average_quality > 0.5:
            return "medium"
        return "low"


class SpriteRegionDetector:
    """Detects and manages sprite regions from scan results"""

    def __init__(
        self,
        gap_threshold: int = ROM_ALIGNMENT_GAP_THRESHOLD,
        min_sprites_per_region: int = 2,
        min_region_size: int = ROM_MIN_REGION_SIZE,
        merge_small_regions: bool = True,
    ):
        self.gap_threshold: int = gap_threshold
        self.min_sprites_per_region: int = min_sprites_per_region
        self.min_region_size: int = min_region_size
        self.merge_small_regions: bool = merge_small_regions
        self.regions: list[SpriteRegion] = []

    def detect_regions(self, sprites: list[tuple[int, float]]) -> list[SpriteRegion]:
        """Process sprite list into regions"""
        if not sprites:
            return []

        # Sort sprites by offset
        sorted_sprites = sorted(sprites, key=lambda x: x[0])

        # Group sprites into regions
        regions = []
        current_region_sprites = [(sorted_sprites[0][0], sorted_sprites[0][1])]
        region_start = sorted_sprites[0][0]

        for i in range(1, len(sorted_sprites)):
            offset, quality = sorted_sprites[i]
            prev_offset = sorted_sprites[i - 1][0]

            # Check if this sprite belongs to current region
            if offset - prev_offset <= self.gap_threshold:
                current_region_sprites.append((offset, quality))
            else:
                # Finalize current region
                region = self._create_region(region_start, current_region_sprites, len(regions))
                if region and self._is_valid_region(region):
                    regions.append(region)

                # Start new region
                current_region_sprites = [(offset, quality)]
                region_start = offset

        # Don't forget the last region
        region = self._create_region(region_start, current_region_sprites, len(regions))
        if region and self._is_valid_region(region):
            regions.append(region)

        # Optionally merge small adjacent regions
        if self.merge_small_regions:
            regions = self._merge_small_regions(regions)

        # Re-index regions after potential merging
        for i, region in enumerate(regions):
            region.region_id = i

        self.regions = regions
        logger.info(f"Detected {len(regions)} sprite regions from {len(sprites)} sprites")
        return regions

    def _create_region(self, start: int, sprites: list[tuple[int, float]], region_id: int) -> SpriteRegion | None:
        """Create a SpriteRegion from sprite list"""
        if not sprites:
            return None

        offsets = [s[0] for s in sprites]
        qualities = [s[1] for s in sprites]

        end_offset = max(offsets) + ROM_MIN_REGION_SIZE  # Add some padding
        size_bytes = end_offset - start
        density = len(sprites) / (size_bytes / 1024) if size_bytes > 0 else 0

        return SpriteRegion(
            region_id=region_id,
            start_offset=start,
            end_offset=end_offset,
            sprite_offsets=offsets,
            sprite_qualities=qualities,
            average_quality=statistics.mean(qualities) if qualities else 0,
            sprite_count=len(sprites),
            size_bytes=size_bytes,
            density=density,
        )

    def _is_valid_region(self, region: SpriteRegion) -> bool:
        """Check if region meets minimum requirements"""
        return region.sprite_count >= self.min_sprites_per_region and region.size_bytes >= self.min_region_size

    def _merge_small_regions(self, regions: list[SpriteRegion]) -> list[SpriteRegion]:
        """Merge small adjacent regions"""
        if len(regions) <= 1:
            return regions

        merged = []
        i = 0
        while i < len(regions):
            current = regions[i]

            # Check if should merge with next region
            if (
                i + 1 < len(regions)
                and current.size_bytes < self.min_region_size * 2
                and regions[i + 1].start_offset - current.end_offset < self.gap_threshold
            ):
                # Merge with next region
                next_region = regions[i + 1]
                merged_sprites = list(
                    zip(
                        current.sprite_offsets + next_region.sprite_offsets,
                        current.sprite_qualities + next_region.sprite_qualities,
                        strict=False,
                    )
                )
                merged_region = self._create_region(current.start_offset, merged_sprites, len(merged))
                if merged_region:
                    merged.append(merged_region)
                i += 2  # Skip next region
            else:
                merged.append(current)
                i += 1

        return merged

    def find_region_for_offset(self, offset: int) -> int | None:
        """Find which region contains the given offset"""
        for i, region in enumerate(self.regions):
            if region.start_offset <= offset <= region.end_offset:
                return i
        return None

    def get_nearest_sprite(self, offset: int, direction: int = 1) -> int | None:
        """Find nearest sprite in given direction (1=forward, -1=backward)"""
        all_sprites = []
        for region in self.regions:
            all_sprites.extend(region.sprite_offsets)

        if not all_sprites:
            return None

        all_sprites.sort()

        if direction > 0:
            # Find next sprite
            for sprite_offset in all_sprites:
                if sprite_offset > offset:
                    return sprite_offset
        else:
            # Find previous sprite
            for sprite_offset in reversed(all_sprites):
                if sprite_offset < offset:
                    return sprite_offset

        return None


class ClassificationRules(TypedDict):
    """Type definition for classification rules structure"""

    min_sprite_count: int
    max_sprite_count: int
    typical_density: tuple[float, float]  # (min, max) sprites per KB
    typical_sizes: tuple[int, int]  # (min, max) bytes


class SpriteRegionClassifier:
    """Classifies sprite regions by type based on patterns"""

    def __init__(self):
        self.classification_rules: dict[str, ClassificationRules] = {
            "characters": {
                "min_sprite_count": 4,
                "max_sprite_count": MAX_SPRITE_COUNT_HEADER,
                "typical_density": (0.5, 2.0),  # sprites per KB
                "typical_sizes": (0x2000, ROM_ALIGNMENT_GAP_THRESHOLD),  # 8KB to 64KB
            },
            "backgrounds": {
                "min_sprite_count": 10,
                "max_sprite_count": MAX_SPRITE_COUNT_MAIN,
                "typical_density": (1.0, 5.0),
                "typical_sizes": (ROM_MIN_REGION_SIZE * 4, ROM_SIZE_512KB // 4),  # 16KB to 128KB
            },
            "effects": {
                "min_sprite_count": 1,
                "max_sprite_count": 20,
                "typical_density": (0.1, 1.0),
                "typical_sizes": (ROM_MIN_REGION_SIZE, ROM_MIN_REGION_SIZE * 8),  # 4KB to 32KB
            },
        }

    def classify_region(self, region: SpriteRegion) -> tuple[str, float]:
        """Classify a region and return type with confidence score"""
        best_match = "unknown"
        best_confidence = 0.0

        for region_type, rules in self.classification_rules.items():
            confidence = 0.0
            factors = 0

            # Check sprite count
            if rules["min_sprite_count"] <= region.sprite_count <= rules["max_sprite_count"]:
                confidence += 0.3
            factors += 0.3

            # Check density
            min_density, max_density = rules["typical_density"]
            if min_density <= region.density <= max_density:
                confidence += 0.3
            factors += 0.3

            # Check size
            min_size, max_size = rules["typical_sizes"]
            if min_size <= region.size_bytes <= max_size:
                confidence += 0.2
            factors += 0.2

            # Check quality distribution
            if region.average_quality > 0.7:
                confidence += 0.2
            factors += 0.2

            # Normalize confidence
            normalized_confidence = confidence / factors if factors > 0 else 0

            if normalized_confidence > best_confidence:
                best_confidence = normalized_confidence
                best_match = region_type

        return best_match, best_confidence


class RegionUpdateManager:
    """Manages dynamic region updates as new sprites are discovered"""

    def __init__(self, detector: SpriteRegionDetector):
        self.detector: SpriteRegionDetector = detector
        self.known_sprites: set[int] = set()
        self.update_callback: Callable[[], None] | None = None

        # Initialize known_sprites with existing sprites from all regions
        for region in self.detector.regions:
            self.known_sprites.update(region.sprite_offsets)

    def add_discovered_sprite(self, offset: int, quality: float) -> bool:
        """Add a newly discovered sprite and update regions if needed"""
        if offset in self.known_sprites:
            return False

        self.known_sprites.add(offset)

        # Check if this sprite falls within existing regions
        region_index = self.detector.find_region_for_offset(offset)

        if region_index is not None:
            # Add to existing region
            region = self.detector.regions[region_index]
            region.sprite_offsets.append(offset)
            region.sprite_qualities.append(quality)
            region.sprite_count += 1
            region.average_quality = statistics.mean(region.sprite_qualities)
            return True
        # Sprite is outside known regions - may need new region
        self._check_new_region_needed(offset, quality)
        return True

    def _check_new_region_needed(self, offset: int, quality: float):
        """Check if a new region should be created"""
        # Find nearest existing region
        nearest_region = None
        min_distance = float("inf")

        for region in self.detector.regions:
            distance = min(abs(offset - region.start_offset), abs(offset - region.end_offset))
            if distance < min_distance:
                min_distance = distance
                nearest_region = region

        # If close enough to existing region, expand it
        if nearest_region and min_distance < self.detector.gap_threshold:
            if offset < nearest_region.start_offset:
                nearest_region.start_offset = offset
            elif offset > nearest_region.end_offset:
                nearest_region.end_offset = offset + ROM_MIN_REGION_SIZE

            nearest_region.sprite_offsets.append(offset)
            nearest_region.sprite_qualities.append(quality)
            nearest_region.sprite_count += 1
            nearest_region.size_bytes = nearest_region.end_offset - nearest_region.start_offset
            nearest_region.density = nearest_region.sprite_count / (nearest_region.size_bytes / 1024)
        else:
            # Create new single-sprite region
            new_region = SpriteRegion(
                region_id=len(self.detector.regions),
                start_offset=offset,
                end_offset=offset + ROM_MIN_REGION_SIZE,
                sprite_offsets=[offset],
                sprite_qualities=[quality],
                average_quality=quality,
                sprite_count=1,
                size_bytes=ROM_MIN_REGION_SIZE,
                density=1.0,
                region_type="discovered",
            )
            self.detector.regions.append(new_region)
            self.detector.regions.sort(key=lambda r: r.start_offset)

            # Re-index regions
            for i, region in enumerate(self.detector.regions):
                region.region_id = i

        # Trigger UI update
        if self.update_callback:
            self.update_callback()
