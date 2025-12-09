"""
Comprehensive tests for visual similarity search functionality.

Tests perceptual hash calculation, similarity scoring accuracy, index save/load,
finding similar sprites, and creating test sprites with known similarities.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from core.visual_similarity_search import (
    # Systematic pytest markers applied based on test content analysis
    SimilarityMatch,
    SpriteGroupFinder,
    SpriteHash,
    VisualSimilarityEngine,
)

logger = logging.getLogger(__name__)

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_qt,
    pytest.mark.performance,
    pytest.mark.rom_data,
]
@pytest.fixture
def test_image_8x8():
    """Create a simple 8x8 test image."""
    # Create a simple checkerboard pattern
    image = Image.new("RGB", (8, 8), color="white")
    pixels = image.load()

    for y in range(8):
        for x in range(8):
            if (x + y) % 2 == 0:
                pixels[x, y] = (0, 0, 0)  # Black
            else:
                pixels[x, y] = (255, 255, 255)  # White

    return image

@pytest.fixture
def test_image_16x16():
    """Create a 16x16 test image with gradient."""
    image = Image.new("RGB", (16, 16), color="white")
    pixels = image.load()

    for y in range(16):
        for x in range(16):
            # Create a diagonal gradient
            intensity = int((x + y) * 255 / 30)
            intensity = min(255, intensity)
            pixels[x, y] = (intensity, intensity, intensity)

    return image

@pytest.fixture
def similar_test_image(test_image_8x8):
    """Create an image similar to test_image_8x8 but slightly different."""
    # Copy the original image
    similar = test_image_8x8.copy()
    pixels = similar.load()

    # Change a few pixels
    pixels[1, 1] = (128, 128, 128)  # Gray instead of black/white
    pixels[6, 6] = (128, 128, 128)  # Gray instead of black/white

    return similar

@pytest.fixture
def different_test_image():
    """Create a completely different test image."""
    image = Image.new("RGB", (8, 8), color="red")
    pixels = image.load()

    # Create a circular pattern
    center_x, center_y = 4, 4
    for y in range(8):
        for x in range(8):
            distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
            if distance < 3:
                pixels[x, y] = (255, 0, 0)  # Red
            else:
                pixels[x, y] = (0, 0, 255)  # Blue

    return image

@pytest.fixture
def similarity_engine():
    """Create VisualSimilarityEngine for testing."""
    return VisualSimilarityEngine(hash_size=8)

class TestSpriteHash:
    """Test SpriteHash data class."""

    def test_sprite_hash_creation(self):
        """Test SpriteHash creation with all fields."""
        phash = np.array([1, 0, 1, 0], dtype=np.uint8)
        dhash = np.array([0, 1, 0, 1], dtype=np.uint8)
        histogram = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        metadata = {"test": "data"}

        sprite_hash = SpriteHash(
            offset=0x1000,
            phash=phash,
            dhash=dhash,
            histogram=histogram,
            metadata=metadata
        )

        assert sprite_hash.offset == 0x1000
        assert np.array_equal(sprite_hash.phash, phash)
        assert np.array_equal(sprite_hash.dhash, dhash)
        assert np.array_equal(sprite_hash.histogram, histogram)
        assert sprite_hash.metadata == metadata

class TestSimilarityMatch:
    """Test SimilarityMatch data class."""

    def test_similarity_match_creation(self):
        """Test SimilarityMatch creation with all fields."""
        metadata = {"sprite_size": 1024}
        match = SimilarityMatch(
            offset=0x2000,
            similarity_score=0.85,
            hash_distance=5,
            metadata=metadata
        )

        assert match.offset == 0x2000
        assert match.similarity_score == 0.85
        assert match.hash_distance == 5
        assert match.metadata == metadata

class TestVisualSimilarityEngine:
    """Test VisualSimilarityEngine class."""

    def test_engine_initialization(self):
        """Test VisualSimilarityEngine initialization."""
        engine = VisualSimilarityEngine(hash_size=16)

        assert engine.hash_size == 16
        assert engine.sprite_database == {}
        assert engine.index_built is False

    def test_default_initialization(self):
        """Test default initialization parameters."""
        engine = VisualSimilarityEngine()

        assert engine.hash_size == 8
        assert isinstance(engine.sprite_database, dict)

    def test_calculate_phash(self, similarity_engine, test_image_8x8):
        """Test perceptual hash calculation."""
        phash = similarity_engine._calculate_phash(test_image_8x8)

        # Should be a numpy array of uint8
        assert isinstance(phash, np.ndarray)
        assert phash.dtype == np.uint8
        assert len(phash) == similarity_engine.hash_size ** 2  # 8x8 = 64

        # Values should be 0 or 1
        assert np.all((phash == 0) | (phash == 1))

    def test_calculate_dhash(self, similarity_engine, test_image_8x8):
        """Test difference hash calculation."""
        dhash = similarity_engine._calculate_dhash(test_image_8x8)

        # Should be a numpy array of uint8
        assert isinstance(dhash, np.ndarray)
        assert dhash.dtype == np.uint8
        assert len(dhash) == similarity_engine.hash_size ** 2  # 8x8 = 64

        # Values should be 0 or 1
        assert np.all((dhash == 0) | (dhash == 1))

    def test_calculate_color_histogram(self, similarity_engine, test_image_8x8):
        """Test color histogram calculation."""
        histogram = similarity_engine._calculate_color_histogram(test_image_8x8)

        # Should be a numpy array of float32
        assert isinstance(histogram, np.ndarray)
        assert histogram.dtype == np.float32
        assert len(histogram) == 48  # 16 bins * 3 channels

        # Should be normalized (sum to ~1.0)
        assert abs(histogram.sum() - 1.0) < 0.01

    def test_hamming_distance(self, similarity_engine):
        """Test Hamming distance calculation."""
        hash1 = np.array([1, 0, 1, 0, 1], dtype=np.uint8)
        hash2 = np.array([1, 1, 0, 0, 1], dtype=np.uint8)

        distance = similarity_engine._hamming_distance(hash1, hash2)

        assert distance == 2  # Positions 1 and 2 are different

    def test_histogram_similarity(self, similarity_engine):
        """Test histogram similarity calculation."""
        hist1 = np.array([0.5, 0.3, 0.2], dtype=np.float32)
        hist2 = np.array([0.4, 0.4, 0.2], dtype=np.float32)

        similarity = similarity_engine._histogram_similarity(hist1, hist2)

        # Should be intersection of histograms
        expected = np.minimum(hist1, hist2).sum()
        assert abs(similarity - expected) < 0.001

    def test_index_sprite(self, similarity_engine, test_image_8x8):
        """Test sprite indexing."""
        metadata = {"size": 1024, "tiles": 16}

        sprite_hash = similarity_engine.index_sprite(
            offset=0x1000,
            image=test_image_8x8,
            metadata=metadata
        )

        # Should return SpriteHash object
        assert isinstance(sprite_hash, SpriteHash)
        assert sprite_hash.offset == 0x1000
        assert sprite_hash.metadata == metadata

        # Should be added to database
        assert 0x1000 in similarity_engine.sprite_database
        assert similarity_engine.sprite_database[0x1000] == sprite_hash

    def test_index_sprite_without_metadata(self, similarity_engine, test_image_8x8):
        """Test sprite indexing without metadata."""
        sprite_hash = similarity_engine.index_sprite(
            offset=0x2000,
            image=test_image_8x8
        )

        assert sprite_hash.metadata == {}

    def test_find_similar_with_indexed_sprite(self, similarity_engine,
                                             test_image_8x8, similar_test_image):
        """Test finding similar sprites using indexed sprite as target."""
        # Index two sprites
        similarity_engine.index_sprite(0x1000, test_image_8x8)
        similarity_engine.index_sprite(0x2000, similar_test_image)

        # Find sprites similar to the first one
        matches = similarity_engine.find_similar(
            target=0x1000,
            max_results=10,
            similarity_threshold=0.5
        )

        # Should find the similar sprite
        assert len(matches) >= 1
        assert isinstance(matches[0], SimilarityMatch)
        assert matches[0].offset == 0x2000
        assert matches[0].similarity_score > 0.5

    def test_find_similar_with_image(self, similarity_engine,
                                   test_image_8x8, similar_test_image):
        """Test finding similar sprites using image as target."""
        # Index one sprite
        similarity_engine.index_sprite(0x1000, test_image_8x8)

        # Find sprites similar to another image
        matches = similarity_engine.find_similar(
            target=similar_test_image,
            max_results=10,
            similarity_threshold=0.5
        )

        # Should find the indexed sprite
        assert len(matches) >= 1
        assert matches[0].offset == 0x1000
        assert matches[0].similarity_score > 0.5

    def test_find_similar_no_matches(self, similarity_engine,
                                   test_image_8x8, different_test_image):
        """Test finding similar sprites with no good matches."""
        # Index sprites that are very different
        similarity_engine.index_sprite(0x1000, test_image_8x8)

        # Find sprites similar to a very different image
        matches = similarity_engine.find_similar(
            target=different_test_image,
            max_results=10,
            similarity_threshold=0.9  # High threshold
        )

        # Should find no matches
        assert len(matches) == 0

    def test_find_similar_nonexistent_offset(self, similarity_engine):
        """Test finding similar sprites with nonexistent target offset."""
        with pytest.raises(ValueError, match="not indexed"):
            similarity_engine.find_similar(target=0x9999)

    def test_find_similar_max_results_limit(self, similarity_engine, test_image_8x8):
        """Test max_results parameter limits output."""
        # Index multiple similar sprites
        for i in range(10):
            # Create slightly different versions of the same image
            modified_image = test_image_8x8.copy()
            similarity_engine.index_sprite(0x1000 + i * 0x100, modified_image)

        # Find similar sprites with limit
        matches = similarity_engine.find_similar(
            target=0x1000,
            max_results=3,
            similarity_threshold=0.0
        )

        # Should respect max_results limit
        assert len(matches) <= 3

    def test_find_similar_sorted_by_similarity(self, similarity_engine,
                                             test_image_8x8, similar_test_image):
        """Test that results are sorted by similarity score."""
        # Index multiple sprites with different similarities
        similarity_engine.index_sprite(0x1000, test_image_8x8)
        similarity_engine.index_sprite(0x2000, similar_test_image)  # More similar

        # Create a less similar sprite
        less_similar = test_image_8x8.copy()
        pixels = less_similar.load()
        # Change more pixels to make it less similar
        for x in range(4):
            for y in range(4):
                pixels[x, y] = (255, 0, 0)  # Red
        similarity_engine.index_sprite(0x3000, less_similar)

        matches = similarity_engine.find_similar(
            target=0x1000,
            max_results=10,
            similarity_threshold=0.1
        )

        # Should be sorted by similarity (descending)
        if len(matches) > 1:
            for i in range(len(matches) - 1):
                assert matches[i].similarity_score >= matches[i + 1].similarity_score

    def test_calculate_similarity_identical_images(self, similarity_engine, test_image_8x8):
        """Test similarity calculation for identical images."""
        hash1 = similarity_engine.index_sprite(0x1000, test_image_8x8)
        hash2 = similarity_engine.index_sprite(0x2000, test_image_8x8)

        similarity = similarity_engine._calculate_similarity(hash1, hash2)

        # Identical images should have similarity close to 1.0
        assert similarity > 0.99

    def test_calculate_similarity_different_images(self, similarity_engine,
                                                 test_image_8x8, different_test_image):
        """Test similarity calculation for different images."""
        hash1 = similarity_engine.index_sprite(0x1000, test_image_8x8)
        hash2 = similarity_engine.index_sprite(0x2000, different_test_image)

        similarity = similarity_engine._calculate_similarity(hash1, hash2)

        # Different images should have low similarity
        assert similarity < 0.5

    def test_build_similarity_index_empty_database(self, similarity_engine):
        """Test building index with empty database."""
        similarity_engine.build_similarity_index()

        # Should handle empty database gracefully
        assert similarity_engine.index_built is True

    def test_build_similarity_index_with_sprites(self, similarity_engine, test_image_8x8):
        """Test building index with sprites."""
        # Add some sprites
        similarity_engine.index_sprite(0x1000, test_image_8x8)
        similarity_engine.index_sprite(0x2000, test_image_8x8)

        similarity_engine.build_similarity_index()

        assert similarity_engine.index_built is True

    def test_export_import_index(self, similarity_engine, test_image_8x8):
        """Test exporting and importing similarity index."""
        # Index some sprites
        similarity_engine.index_sprite(0x1000, test_image_8x8, {"test": "data"})
        similarity_engine.build_similarity_index()

        # Export to temporary file
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            export_path = Path(f.name)

        try:
            similarity_engine.export_index(export_path)

            # Create new engine and import
            new_engine = VisualSimilarityEngine()
            new_engine.import_index(export_path)

            # Should have same data
            assert new_engine.hash_size == similarity_engine.hash_size
            assert len(new_engine.sprite_database) == len(similarity_engine.sprite_database)
            assert new_engine.index_built == similarity_engine.index_built
            assert 0x1000 in new_engine.sprite_database
            assert new_engine.sprite_database[0x1000].metadata == {"test": "data"}

        finally:
            export_path.unlink(missing_ok=True)

class TestSpriteGroupFinder:
    """Test SpriteGroupFinder class."""

    @pytest.fixture
    def group_finder(self, similarity_engine):
        """Create SpriteGroupFinder for testing."""
        return SpriteGroupFinder(similarity_engine)

    def test_group_finder_initialization(self, group_finder, similarity_engine):
        """Test SpriteGroupFinder initialization."""
        assert group_finder.engine == similarity_engine
        assert group_finder.groups == []

    def test_find_sprite_groups_basic(self, group_finder, similarity_engine,
                                    test_image_8x8, similar_test_image):
        """Test basic sprite group finding."""
        # Index similar sprites
        similarity_engine.index_sprite(0x1000, test_image_8x8)
        similarity_engine.index_sprite(0x2000, similar_test_image)
        similarity_engine.index_sprite(0x3000, test_image_8x8)  # Duplicate

        groups = group_finder.find_sprite_groups(
            similarity_threshold=0.5,
            min_group_size=2
        )

        # Should find at least one group
        assert len(groups) >= 1
        assert isinstance(groups[0], list)
        assert len(groups[0]) >= 2

    def test_find_sprite_groups_no_similar_sprites(self, group_finder, similarity_engine,
                                                 test_image_8x8, different_test_image):
        """Test group finding with no similar sprites."""
        # Index very different sprites
        similarity_engine.index_sprite(0x1000, test_image_8x8)
        similarity_engine.index_sprite(0x2000, different_test_image)

        groups = group_finder.find_sprite_groups(
            similarity_threshold=0.9,  # High threshold
            min_group_size=2
        )

        # Should find no groups
        assert len(groups) == 0

    def test_find_sprite_groups_sorted_by_size(self, group_finder, similarity_engine,
                                             test_image_8x8, test_image_16x16):
        """Test that groups are sorted by size."""
        # Create two groups of different sizes
        # Group 1: 3 similar sprites
        similarity_engine.index_sprite(0x1000, test_image_8x8)
        similarity_engine.index_sprite(0x1100, test_image_8x8)
        similarity_engine.index_sprite(0x1200, test_image_8x8)

        # Group 2: 2 similar sprites (different from group 1)
        similarity_engine.index_sprite(0x2000, test_image_16x16)
        similarity_engine.index_sprite(0x2100, test_image_16x16)

        groups = group_finder.find_sprite_groups(
            similarity_threshold=0.8,
            min_group_size=2
        )

        # Should be sorted by size (largest first)
        if len(groups) > 1:
            assert len(groups[0]) >= len(groups[1])

    def test_find_animations_basic(self, group_finder, similarity_engine, test_image_8x8):
        """Test basic animation sequence finding."""
        # Index sprites at close offsets (simulating animation frames)
        similarity_engine.index_sprite(0x1000, test_image_8x8)

        # Create slightly modified versions for animation frames
        frame2 = test_image_8x8.copy()
        frame3 = test_image_8x8.copy()

        similarity_engine.index_sprite(0x1100, frame2)  # Close offset
        similarity_engine.index_sprite(0x1200, frame3)  # Close offset

        animations = group_finder.find_animations(
            offset_proximity=0x1000,
            similarity_threshold=0.8
        )

        # Should find animation sequence
        assert len(animations) >= 1
        assert isinstance(animations[0], list)
        assert len(animations[0]) >= 2

    def test_find_animations_offset_proximity(self, group_finder, similarity_engine, test_image_8x8):
        """Test animation finding respects offset proximity."""
        # Index sprites at distant offsets
        similarity_engine.index_sprite(0x1000, test_image_8x8)
        similarity_engine.index_sprite(0x50000, test_image_8x8)  # Far away

        animations = group_finder.find_animations(
            offset_proximity=0x1000,  # Small proximity
            similarity_threshold=0.8
        )

        # Should not find animation due to distance
        assert len(animations) == 0

    def test_find_animations_similarity_threshold(self, group_finder, similarity_engine,
                                                test_image_8x8, different_test_image):
        """Test animation finding respects similarity threshold."""
        # Index dissimilar sprites at close offsets
        similarity_engine.index_sprite(0x1000, test_image_8x8)
        similarity_engine.index_sprite(0x1100, different_test_image)

        animations = group_finder.find_animations(
            offset_proximity=0x10000,
            similarity_threshold=0.9  # High threshold
        )

        # Should not find animation due to low similarity
        assert len(animations) == 0

    def test_find_animations_sorted_by_offset(self, group_finder, similarity_engine, test_image_8x8):
        """Test that animation frames are in offset order."""
        # Index sprites in random order
        similarity_engine.index_sprite(0x3000, test_image_8x8)
        similarity_engine.index_sprite(0x1000, test_image_8x8)
        similarity_engine.index_sprite(0x2000, test_image_8x8)

        animations = group_finder.find_animations(
            offset_proximity=0x10000,
            similarity_threshold=0.8
        )

        # Animation should be in offset order
        if animations and len(animations[0]) > 1:
            animation = animations[0]
            for i in range(len(animation) - 1):
                assert animation[i] < animation[i + 1]

@pytest.mark.slow
class TestVisualSimilarityPerformance:
    """Performance tests for visual similarity search."""

    def test_hash_calculation_performance(self, similarity_engine, test_image_8x8):
        """Test hash calculation performance."""
        import time

        # Time hash calculations
        start_time = time.time()
        for _ in range(100):
            similarity_engine._calculate_phash(test_image_8x8)
            similarity_engine._calculate_dhash(test_image_8x8)
            similarity_engine._calculate_color_histogram(test_image_8x8)

        elapsed = time.time() - start_time
        avg_time = elapsed / 100

        # Should be reasonably fast (less than 10ms per image)
        assert avg_time < 0.01
        logger.info(f"Average hash calculation time: {avg_time*1000:.2f}ms")

    def test_similarity_search_performance(self, similarity_engine, test_image_8x8):
        """Test similarity search performance with many sprites."""
        import time

        # Index many sprites
        num_sprites = 1000
        for i in range(num_sprites):
            # Create slight variations
            img = test_image_8x8.copy()
            similarity_engine.index_sprite(0x1000 + i * 0x100, img)

        # Time similarity search
        start_time = time.time()
        similarity_engine.find_similar(
            target=0x1000,
            max_results=10,
            similarity_threshold=0.5
        )
        elapsed = time.time() - start_time

        # Should complete in reasonable time
        assert elapsed < 1.0  # Less than 1 second
        logger.info(f"Search in {num_sprites} sprites took {elapsed*1000:.2f}ms")

@pytest.mark.benchmark
class TestBenchmarkVisualSimilarity:
    """Benchmark tests for visual similarity search."""

    def test_benchmark_phash_calculation(self, benchmark, similarity_engine, test_image_8x8):
        """Benchmark perceptual hash calculation."""
        result = benchmark(similarity_engine._calculate_phash, test_image_8x8)
        assert isinstance(result, np.ndarray)

    def test_benchmark_histogram_calculation(self, benchmark, similarity_engine, test_image_8x8):
        """Benchmark histogram calculation."""
        result = benchmark(similarity_engine._calculate_color_histogram, test_image_8x8)
        assert isinstance(result, np.ndarray)

    def test_benchmark_similarity_calculation(self, benchmark, similarity_engine,
                                           test_image_8x8, similar_test_image):
        """Benchmark similarity calculation between two sprites."""
        hash1 = similarity_engine.index_sprite(0x1000, test_image_8x8)
        hash2 = similarity_engine.index_sprite(0x2000, similar_test_image)

        result = benchmark(similarity_engine._calculate_similarity, hash1, hash2)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0
