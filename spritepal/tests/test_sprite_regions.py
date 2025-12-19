"""
Tests for sprite region detection and management functionality.
"""
from __future__ import annotations

import time

import pytest

from utils.sprite_regions import (
    # Systematic pytest markers applied based on test content analysis
    RegionUpdateManager,
    SpriteRegion,
    SpriteRegionClassifier,
    SpriteRegionDetector,
)

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.headless,
    pytest.mark.performance,
    pytest.mark.slow,
]
class TestSpriteRegion:
    """Test SpriteRegion data class functionality"""

    def test_sprite_region_creation(self):
        """Test creating a SpriteRegion with all fields"""
        region = SpriteRegion(
            region_id=0,
            start_offset=0x200000,
            end_offset=0x210000,
            sprite_offsets=[0x200000, 0x201000, 0x202000],
            sprite_qualities=[0.9, 0.8, 0.85],
            average_quality=0.85,
            sprite_count=3,
            size_bytes=0x10000,
            density=0.1875  # 3 sprites / 64KB
        )

        assert region.region_id == 0
        assert region.start_offset == 0x200000
        assert region.end_offset == 0x210000
        assert len(region.sprite_offsets) == 3
        assert region.sprite_count == 3
        assert region.density == 0.1875

    def test_description_property(self):
        """Test the description property with and without custom name"""
        region = SpriteRegion(
            region_id=2,
            start_offset=0x300000,
            end_offset=0x310000,
            sprite_offsets=[],
            sprite_qualities=[],
            average_quality=0.8,
            sprite_count=5,
            size_bytes=0x10000,
            density=0.3
        )

        # Default description
        assert region.description == "Region 3: 0x300000-0x310000 (5 sprites)"

        # With custom name
        region.custom_name = "Kirby Sprites"
        assert region.description == "Kirby Sprites (Region 3)"

    def test_center_offset_property(self):
        """Test center offset calculation"""
        region = SpriteRegion(
            region_id=0,
            start_offset=0x200000,
            end_offset=0x210000,
            sprite_offsets=[],
            sprite_qualities=[],
            average_quality=0.8,
            sprite_count=1,
            size_bytes=0x10000,
            density=0.1
        )

        assert region.center_offset == 0x208000  # (0x200000 + 0x210000) // 2

    def test_quality_category_property(self):
        """Test quality categorization"""
        # High quality
        region = SpriteRegion(
            region_id=0,
            start_offset=0,
            end_offset=0x1000,
            sprite_offsets=[],
            sprite_qualities=[],
            average_quality=0.9,
            sprite_count=1,
            size_bytes=0x1000,
            density=1.0
        )
        assert region.quality_category == "high"

        # Medium quality
        region.average_quality = 0.6
        assert region.quality_category == "medium"

        # Low quality
        region.average_quality = 0.3
        assert region.quality_category == "low"

class TestSpriteRegionDetector:
    """Test SpriteRegionDetector functionality"""

    def test_empty_sprite_list(self):
        """Test detection with empty sprite list"""
        detector = SpriteRegionDetector()
        regions = detector.detect_regions([])
        assert regions == []

    def test_single_region_detection(self):
        """Test detection of a single contiguous region"""
        detector = SpriteRegionDetector(gap_threshold=0x2000)
        sprites = [
            (0x200000, 0.8),
            (0x200100, 0.9),
            (0x200200, 0.7),
            (0x201000, 0.85),
        ]

        regions = detector.detect_regions(sprites)
        assert len(regions) == 1
        assert regions[0].sprite_count == 4
        assert regions[0].start_offset == 0x200000
        assert regions[0].end_offset >= 0x201000

    def test_multiple_region_detection(self):
        """Test detection of multiple regions with gaps"""
        detector = SpriteRegionDetector(gap_threshold=0x1000)
        sprites = [
            # Region 1
            (0x100000, 0.8),
            (0x100100, 0.9),
            (0x100200, 0.7),
            # Gap > 0x1000
            # Region 2
            (0x105000, 0.8),
            (0x105100, 0.9),
            # Gap > 0x1000
            # Region 3
            (0x200000, 0.6),
            (0x200100, 0.7),
        ]

        regions = detector.detect_regions(sprites)
        assert len(regions) == 3
        assert regions[0].sprite_count == 3
        assert regions[1].sprite_count == 2
        assert regions[2].sprite_count == 2

    def test_minimum_sprites_per_region(self):
        """Test minimum sprites per region filter"""
        detector = SpriteRegionDetector(
            gap_threshold=0x1000,
            min_sprites_per_region=3
        )
        sprites = [
            # Region 1 - will be kept (3 sprites)
            (0x100000, 0.8),
            (0x100100, 0.9),
            (0x100200, 0.7),
            # Gap
            # Region 2 - will be filtered out (2 sprites)
            (0x105000, 0.8),
            (0x105100, 0.9),
        ]

        regions = detector.detect_regions(sprites)
        assert len(regions) == 1
        assert regions[0].sprite_count == 3

    def test_minimum_region_size(self):
        """Test minimum region size filter"""
        detector = SpriteRegionDetector(
            gap_threshold=0x10000,
            min_region_size=0x2000  # 8KB minimum
        )
        sprites = [
            # Small region - will be filtered out
            (0x100000, 0.8),
            (0x100100, 0.9),  # Region size < 0x2000
            # Gap
            # Large region - will be kept
            (0x200000, 0.8),
            (0x202000, 0.9),  # Region size >= 0x2000
        ]

        regions = detector.detect_regions(sprites)
        assert len(regions) == 1
        assert regions[0].start_offset == 0x200000

    def test_region_merging(self):
        """Test small region merging"""
        detector = SpriteRegionDetector(
            gap_threshold=0x1000,
            min_region_size=0x1000,
            merge_small_regions=True
        )
        sprites = [
            # Small region 1
            (0x100000, 0.8),
            (0x100100, 0.9),
            # Small gap (< gap_threshold)
            (0x100800, 0.7),
            (0x100900, 0.8),
        ]

        regions = detector.detect_regions(sprites)
        # Should be merged into one region
        assert len(regions) == 1
        assert regions[0].sprite_count == 4

    def test_find_region_for_offset(self):
        """Test finding which region contains an offset"""
        detector = SpriteRegionDetector(gap_threshold=0x1000)
        sprites = [
            (0x100000, 0.8),
            (0x100100, 0.9),
            (0x200000, 0.7),
            (0x200100, 0.8),
        ]

        detector.detect_regions(sprites)

        # Test offsets in regions
        assert detector.find_region_for_offset(0x100050) == 0
        assert detector.find_region_for_offset(0x200050) == 1

        # Test offset outside regions
        assert detector.find_region_for_offset(0x300000) is None

    def test_get_nearest_sprite(self):
        """Test finding nearest sprite in given direction"""
        detector = SpriteRegionDetector()
        sprites = [
            (0x100000, 0.8),
            (0x100100, 0.9),
            (0x200000, 0.7),
            (0x200100, 0.8),
        ]

        detector.detect_regions(sprites)

        # Find next sprite
        assert detector.get_nearest_sprite(0x100050, direction=1) == 0x100100
        assert detector.get_nearest_sprite(0x100100, direction=1) == 0x200000
        assert detector.get_nearest_sprite(0x200100, direction=1) is None

        # Find previous sprite
        assert detector.get_nearest_sprite(0x200050, direction=-1) == 0x200000
        assert detector.get_nearest_sprite(0x200000, direction=-1) == 0x100100
        assert detector.get_nearest_sprite(0x100000, direction=-1) is None

    def test_region_ordering(self):
        """Test that regions are ordered by start offset"""
        detector = SpriteRegionDetector(
            gap_threshold=0x80000,  # Gap threshold smaller than 0x100000 to ensure 3 separate regions
            min_sprites_per_region=1  # Allow single-sprite regions for this test
        )
        # Provide sprites out of order
        sprites = [
            (0x300000, 0.8),
            (0x100000, 0.9),
            (0x200000, 0.7),
        ]

        regions = detector.detect_regions(sprites)
        assert len(regions) == 3
        assert regions[0].start_offset == 0x100000
        assert regions[1].start_offset == 0x200000
        assert regions[2].start_offset == 0x300000

        # Check region IDs are sequential
        for i, region in enumerate(regions):
            assert region.region_id == i

class TestSpriteRegionClassifier:
    """Test region classification functionality"""

    def test_character_region_classification(self):
        """Test classification of character-like regions"""
        classifier = SpriteRegionClassifier()

        # Create a typical character region
        # Characters need density between 0.5-2.0 sprites/KB
        region = SpriteRegion(
            region_id=0,
            start_offset=0x200000,
            end_offset=0x204000,  # 16KB
            sprite_offsets=[0x200000 + i * 0x800 for i in range(12)],
            sprite_qualities=[0.85] * 12,
            average_quality=0.85,
            sprite_count=12,
            size_bytes=0x4000,  # 16KB
            density=0.75  # 12 sprites / 16KB = 0.75 sprites/KB (within character range)
        )

        region_type, confidence = classifier.classify_region(region)
        assert region_type == "characters"
        assert confidence > 0.5

    def test_background_region_classification(self):
        """Test classification of background-like regions"""
        classifier = SpriteRegionClassifier()

        # Create a typical background region
        region = SpriteRegion(
            region_id=0,
            start_offset=0x300000,
            end_offset=0x310000,  # 64KB
            sprite_offsets=[0x300000 + i * 0x400 for i in range(64)],
            sprite_qualities=[0.8] * 64,
            average_quality=0.8,
            sprite_count=64,
            size_bytes=0x10000,  # 64KB
            density=1.0  # 64 sprites / 64KB
        )

        region_type, confidence = classifier.classify_region(region)
        assert region_type == "backgrounds"
        assert confidence > 0.5

    def test_effects_region_classification(self):
        """Test classification of effects-like regions"""
        classifier = SpriteRegionClassifier()

        # Create a typical effects region
        region = SpriteRegion(
            region_id=0,
            start_offset=0x100000,
            end_offset=0x102000,  # 8KB
            sprite_offsets=[0x100000, 0x101000],
            sprite_qualities=[0.7, 0.75],
            average_quality=0.725,
            sprite_count=2,
            size_bytes=0x2000,  # 8KB
            density=0.25  # 2 sprites / 8KB
        )

        region_type, confidence = classifier.classify_region(region)
        assert region_type == "effects"
        assert confidence > 0.3

    def test_unknown_region_classification(self):
        """Test classification of regions that don't match patterns"""
        classifier = SpriteRegionClassifier()

        # Create an unusual region
        region = SpriteRegion(
            region_id=0,
            start_offset=0x400000,
            end_offset=0x500000,  # 1MB - too large
            sprite_offsets=[0x400000],
            sprite_qualities=[0.5],
            average_quality=0.5,
            sprite_count=1,
            size_bytes=0x100000,  # 1MB
            density=0.001  # Very low density
        )

        region_type, confidence = classifier.classify_region(region)
        # This region is so unusual it should either be unknown or have very low confidence
        assert region_type == "unknown" or confidence <= 0.3, f"Got {region_type} with confidence {confidence}"

class TestRegionUpdateManager:
    """Test dynamic region update functionality"""

    def test_add_sprite_to_existing_region(self):
        """Test adding a sprite to an existing region"""
        detector = SpriteRegionDetector()
        sprites = [
            (0x200000, 0.8),
            (0x200100, 0.9),
            (0x200200, 0.7),
        ]
        detector.detect_regions(sprites)

        manager = RegionUpdateManager(detector)

        # Add sprite within existing region
        result = manager.add_discovered_sprite(0x200300, 0.85)
        assert result is True
        assert detector.regions[0].sprite_count == 4
        assert 0x200300 in detector.regions[0].sprite_offsets

    def test_expand_region_for_nearby_sprite(self):
        """Test expanding a region for a nearby sprite"""
        detector = SpriteRegionDetector(gap_threshold=0x1000, min_sprites_per_region=1)
        sprites = [(0x200000, 0.8)]
        detector.detect_regions(sprites)

        manager = RegionUpdateManager(detector)

        # Add sprite just outside region but within gap threshold
        result = manager.add_discovered_sprite(0x201500, 0.9)
        assert result is True
        assert detector.regions[0].sprite_count == 2
        assert detector.regions[0].end_offset >= 0x201500

    def test_create_new_region_for_distant_sprite(self):
        """Test creating a new region for a distant sprite"""
        detector = SpriteRegionDetector(gap_threshold=0x1000, min_sprites_per_region=1)
        sprites = [(0x200000, 0.8)]
        detector.detect_regions(sprites)

        manager = RegionUpdateManager(detector)

        # Add sprite far from existing region
        result = manager.add_discovered_sprite(0x300000, 0.9)
        assert result is True
        assert len(detector.regions) == 2
        assert detector.regions[1].start_offset == 0x300000
        assert detector.regions[1].sprite_count == 1

    def test_prevent_duplicate_sprites(self):
        """Test that duplicate sprites are not added"""
        detector = SpriteRegionDetector(min_sprites_per_region=1)
        sprites = [(0x200000, 0.8)]
        detector.detect_regions(sprites)

        manager = RegionUpdateManager(detector)

        # Try to add the same sprite again
        result = manager.add_discovered_sprite(0x200000, 0.9)
        assert result is False
        assert detector.regions[0].sprite_count == 1

    def test_update_callback(self):
        """Test that update callback is triggered"""
        detector = SpriteRegionDetector(min_sprites_per_region=1)
        sprites = [(0x200000, 0.8)]
        detector.detect_regions(sprites)

        manager = RegionUpdateManager(detector)

        # Set up callback tracking
        callback_count = 0
        def callback():
            nonlocal callback_count
            callback_count += 1

        manager.update_callback = callback

        # Add new sprite
        manager.add_discovered_sprite(0x300000, 0.9)
        assert callback_count == 1

class TestPerformance:
    """Test performance with large sprite counts"""

    def test_large_sprite_count_performance(self):
        """Test performance with many sprites"""
        import random
        random.seed(42)  # Seed for reproducibility

        # Generate 10,000 sprites
        sprites = []
        for i in range(10000):
            offset = i * 0x100
            quality = random.uniform(0.5, 1.0)
            sprites.append((offset, quality))

        detector = SpriteRegionDetector(gap_threshold=0x1000)

        start_time = time.time()
        regions = detector.detect_regions(sprites)
        elapsed = time.time() - start_time

        # Should complete quickly
        assert elapsed < 0.5  # 500ms max
        assert len(regions) > 0

        # Verify all sprites are accounted for
        total_sprites = sum(r.sprite_count for r in regions)
        assert total_sprites == len(sprites)

    def test_region_lookup_performance(self):
        """Test performance of region lookup operations"""
        # Use smaller gap threshold to ensure regions stay separate
        detector = SpriteRegionDetector(gap_threshold=0x1000)

        # Create many regions
        sprites = []
        for i in range(100):
            base_offset = i * 0x10000  # 64KB spacing between region groups
            for j in range(10):
                sprites.append((base_offset + j * 0x100, 0.8))

        regions = detector.detect_regions(sprites)
        assert len(regions) >= 50  # Should have many regions

        # Test lookup performance
        start_time = time.time()
        for _ in range(1000):
            # Random offset lookups
            offset = 0x500000
            detector.find_region_for_offset(offset)
        elapsed = time.time() - start_time

        # Should be very fast
        assert elapsed < 0.1  # 100ms for 1000 lookups

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
