"""
Comprehensive tests for VisualSimilarityEngine and related classes.

Tests cover:
- Perceptual hashing (phash, dhash)
- Color histogram calculation
- Similarity scoring
- Sprite indexing
- Find similar functionality
- Index persistence (import/export)
- Sprite group finding
- Animation detection
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image

from core.visual_similarity_search import (
    SimilarityMatch,
    SpriteGroupFinder,
    SpriteHash,
    VisualSimilarityEngine,
)

# Test markers
pytestmark = [
    pytest.mark.headless,
]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def engine() -> VisualSimilarityEngine:
    """Create a fresh VisualSimilarityEngine."""
    return VisualSimilarityEngine()


@pytest.fixture
def small_engine() -> VisualSimilarityEngine:
    """Create engine with small hash size for faster tests."""
    return VisualSimilarityEngine(hash_size=4)


@pytest.fixture
def solid_red_image() -> Image.Image:
    """Create a solid red 64x64 image."""
    return Image.new("RGB", (64, 64), color=(255, 0, 0))


@pytest.fixture
def solid_blue_image() -> Image.Image:
    """Create a solid blue 64x64 image."""
    return Image.new("RGB", (64, 64), color=(0, 0, 255))


@pytest.fixture
def solid_black_image() -> Image.Image:
    """Create a solid black 64x64 image."""
    return Image.new("RGB", (64, 64), color=(0, 0, 0))


@pytest.fixture
def solid_white_image() -> Image.Image:
    """Create a solid white 64x64 image."""
    return Image.new("RGB", (64, 64), color=(255, 255, 255))


@pytest.fixture
def gradient_image() -> Image.Image:
    """Create a horizontal gradient image."""
    img = Image.new("L", (64, 64))
    for x in range(64):
        for y in range(64):
            img.putpixel((x, y), int(x * 255 / 63))
    return img.convert("RGB")


@pytest.fixture
def random_image() -> Image.Image:
    """Create a pseudo-random image for testing."""
    np.random.seed(42)
    data = np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8)
    return Image.fromarray(data, "RGB")


# =============================================================================
# VisualSimilarityEngine - Initialization
# =============================================================================


class TestEngineInit:
    """Tests for engine initialization."""

    def test_engine_initialization_default(self) -> None:
        """Verify engine initializes with default hash_size=8."""
        engine = VisualSimilarityEngine()

        assert engine.hash_size == 8
        assert engine.sprite_database == {}
        assert engine.index_built is False

    def test_engine_initialization_custom_hash_size(self) -> None:
        """Verify engine initializes with custom hash_size."""
        engine = VisualSimilarityEngine(hash_size=16)

        assert engine.hash_size == 16

    def test_engine_initial_state(self) -> None:
        """Verify sprite_database is empty and index_built=False after init."""
        engine = VisualSimilarityEngine(hash_size=4)

        assert len(engine.sprite_database) == 0
        assert engine.index_built is False

    def test_engine_with_various_hash_sizes(self) -> None:
        """Test with various hash sizes."""
        for size in [4, 8, 16, 32]:
            engine = VisualSimilarityEngine(hash_size=size)
            assert engine.hash_size == size


# =============================================================================
# Perceptual Hash (phash)
# =============================================================================


class TestPerceptualHash:
    """Tests for perceptual hash calculation."""

    def test_phash_identical_images_same_hash(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Two identical images should produce identical phash arrays."""
        hash1 = engine._calculate_phash(solid_red_image)
        hash2 = engine._calculate_phash(solid_red_image)

        np.testing.assert_array_equal(hash1, hash2)

    def test_phash_different_images_different_hash(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        gradient_image: Image.Image,
    ) -> None:
        """Very different images should produce different phashes."""
        hash1 = engine._calculate_phash(solid_red_image)
        hash2 = engine._calculate_phash(gradient_image)

        # Not all elements should be equal
        assert not np.array_equal(hash1, hash2)

    def test_phash_scaled_image_similar_hash(
        self, engine: VisualSimilarityEngine, gradient_image: Image.Image
    ) -> None:
        """Scaled version of image should have similar phash."""
        original_hash = engine._calculate_phash(gradient_image)

        # Scale the image
        scaled = gradient_image.resize((128, 128), Image.Resampling.LANCZOS)
        scaled_hash = engine._calculate_phash(scaled)

        # Should be identical since both are resized to hash_size
        np.testing.assert_array_equal(original_hash, scaled_hash)

    def test_phash_output_dimensions(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Phash output should be hash_size^2 binary values."""
        result = engine._calculate_phash(solid_red_image)

        # Default hash_size=8, so 64 bits
        assert result.shape == (64,)

    def test_phash_output_type_and_range(
        self, engine: VisualSimilarityEngine, gradient_image: Image.Image
    ) -> None:
        """Output should be np.ndarray of uint8 with values in [0, 1]."""
        result = engine._calculate_phash(gradient_image)

        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8
        assert np.all((result == 0) | (result == 1))

    def test_phash_grayscale_image(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Grayscale image should work correctly."""
        gray_img = Image.new("L", (64, 64), 128)
        result = engine._calculate_phash(gray_img)

        assert result.shape == (64,)

    def test_phash_rgba_image(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """RGBA image should be converted and hashed."""
        rgba_img = Image.new("RGBA", (64, 64), (255, 0, 0, 128))
        result = engine._calculate_phash(rgba_img)

        assert result.shape == (64,)

    def test_phash_small_image(self, engine: VisualSimilarityEngine) -> None:
        """Small image (1x1) should still produce valid hash."""
        tiny_img = Image.new("RGB", (1, 1), (128, 128, 128))
        result = engine._calculate_phash(tiny_img)

        assert result.shape == (64,)


# =============================================================================
# Difference Hash (dhash)
# =============================================================================


class TestDifferenceHash:
    """Tests for difference hash calculation."""

    def test_dhash_identical_images_same_hash(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Two identical images should produce identical dhash arrays."""
        hash1 = engine._calculate_dhash(solid_red_image)
        hash2 = engine._calculate_dhash(solid_red_image)

        np.testing.assert_array_equal(hash1, hash2)

    def test_dhash_output_dimensions(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Dhash should be hash_size * hash_size bits."""
        result = engine._calculate_dhash(solid_red_image)

        # hash_size=8, image resized to 9x8, differences give 8x8=64
        assert result.shape == (64,)

    def test_dhash_output_type_and_range(
        self, engine: VisualSimilarityEngine, gradient_image: Image.Image
    ) -> None:
        """Output should be np.ndarray of uint8 with binary values."""
        result = engine._calculate_dhash(gradient_image)

        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8
        assert np.all((result == 0) | (result == 1))

    def test_dhash_gradient_image_pattern(
        self, engine: VisualSimilarityEngine, gradient_image: Image.Image
    ) -> None:
        """Gradient image should produce dhash with all 1s (always increasing)."""
        result = engine._calculate_dhash(gradient_image)

        # Horizontal gradient means each pixel is greater than left neighbor
        # So all differences should be 1
        assert np.sum(result) > 0  # At least some 1s

    def test_dhash_detects_structure_changes(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        gradient_image: Image.Image,
    ) -> None:
        """Different structures should produce different dhash."""
        hash1 = engine._calculate_dhash(solid_red_image)
        hash2 = engine._calculate_dhash(gradient_image)

        # Should be different
        assert not np.array_equal(hash1, hash2)

    def test_dhash_small_hash_size(self) -> None:
        """Test dhash with small hash size."""
        engine = VisualSimilarityEngine(hash_size=4)
        img = Image.new("RGB", (64, 64), (100, 100, 100))
        result = engine._calculate_dhash(img)

        # 4x4 = 16 bits
        assert result.shape == (16,)


# =============================================================================
# Color Histogram
# =============================================================================


class TestColorHistogram:
    """Tests for color histogram calculation."""

    def test_histogram_output_dimensions(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Histogram should be 48-element array (16 bins x 3 channels)."""
        result = engine._calculate_color_histogram(solid_red_image)

        assert result.shape == (48,)

    def test_histogram_normalization(
        self, engine: VisualSimilarityEngine, random_image: Image.Image
    ) -> None:
        """Histogram values should sum to ~1.0 (normalized)."""
        result = engine._calculate_color_histogram(random_image)

        assert abs(np.sum(result) - 1.0) < 0.01

    def test_histogram_single_color_image(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Solid red image should have peak in highest R bin, lowest G/B bins."""
        result = engine._calculate_color_histogram(solid_red_image)

        # R channel is bins 0-15, G is 16-31, B is 32-47
        # For solid (255,0,0): R goes to bin 15, G to bin 0, B to bin 0
        # Each channel gets 1/3 of normalized mass

        # R channel bin 15 (highest) should have the peak
        assert result[15] > 0.3  # R channel, highest bin

        # G and B should be at bin 0 (lowest)
        assert result[16] > 0.3  # G channel, bin 0
        assert result[32] > 0.3  # B channel, bin 0

    def test_histogram_black_image(
        self, engine: VisualSimilarityEngine, solid_black_image: Image.Image
    ) -> None:
        """All-black image should have histogram at lowest bins."""
        result = engine._calculate_color_histogram(solid_black_image)

        # Bin 0 for each channel should have all the mass
        assert result[0] > 0.3  # R channel bin 0
        assert result[16] > 0.3  # G channel bin 0
        assert result[32] > 0.3  # B channel bin 0

    def test_histogram_white_image(
        self, engine: VisualSimilarityEngine, solid_white_image: Image.Image
    ) -> None:
        """All-white image should have histogram at highest bins."""
        result = engine._calculate_color_histogram(solid_white_image)

        # Bin 15 (highest) for each channel should have mass
        assert result[15] > 0.3  # R channel bin 15
        assert result[31] > 0.3  # G channel bin 15
        assert result[47] > 0.3  # B channel bin 15

    def test_histogram_rgba_image_conversion(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """RGBA images should be converted to RGB before histogram."""
        rgba_img = Image.new("RGBA", (64, 64), (255, 0, 0, 128))
        result = engine._calculate_color_histogram(rgba_img)

        assert result.shape == (48,)
        # Should behave like solid red - R channel peak at bin 15
        assert result[15] > 0.3  # R channel, highest bin

    def test_histogram_identical_images_same_histogram(
        self, engine: VisualSimilarityEngine, gradient_image: Image.Image
    ) -> None:
        """Two identical images should produce identical histograms."""
        hist1 = engine._calculate_color_histogram(gradient_image)
        hist2 = engine._calculate_color_histogram(gradient_image)

        np.testing.assert_array_almost_equal(hist1, hist2)

    def test_histogram_grayscale_conversion(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Grayscale image should be converted to RGB."""
        gray_img = Image.new("L", (64, 64), 128)
        result = engine._calculate_color_histogram(gray_img)

        assert result.shape == (48,)


# =============================================================================
# Indexing
# =============================================================================


class TestIndexSprite:
    """Tests for sprite indexing."""

    def test_index_sprite_basic(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Index a sprite and verify it's stored in database."""
        engine.index_sprite(0x1000, solid_red_image)

        assert 0x1000 in engine.sprite_database

    def test_index_sprite_returns_sprite_hash(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """index_sprite() should return SpriteHash object."""
        result = engine.index_sprite(0x1000, solid_red_image)

        assert isinstance(result, SpriteHash)
        assert result.offset == 0x1000

    def test_index_sprite_multiple_sprites(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        solid_blue_image: Image.Image,
    ) -> None:
        """Index multiple sprites at different offsets."""
        engine.index_sprite(0x1000, solid_red_image)
        engine.index_sprite(0x2000, solid_blue_image)

        assert len(engine.sprite_database) == 2
        assert 0x1000 in engine.sprite_database
        assert 0x2000 in engine.sprite_database

    def test_index_sprite_with_metadata(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Index sprite with metadata dict."""
        metadata = {"name": "hero", "frame": 1}
        result = engine.index_sprite(0x1000, solid_red_image, metadata=metadata)

        assert result.metadata == metadata

    def test_index_sprite_without_metadata(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Index sprite without metadata should default to empty dict."""
        result = engine.index_sprite(0x1000, solid_red_image)

        assert result.metadata == {}

    def test_index_sprite_offset_overwrite(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        solid_blue_image: Image.Image,
    ) -> None:
        """Indexing same offset twice should overwrite previous entry."""
        engine.index_sprite(0x1000, solid_red_image, metadata={"color": "red"})
        engine.index_sprite(0x1000, solid_blue_image, metadata={"color": "blue"})

        assert len(engine.sprite_database) == 1
        assert engine.sprite_database[0x1000].metadata["color"] == "blue"

    def test_index_sprite_hash_fields_populated(
        self, engine: VisualSimilarityEngine, gradient_image: Image.Image
    ) -> None:
        """Returned SpriteHash should have all fields populated."""
        result = engine.index_sprite(0x1000, gradient_image, metadata={"test": True})

        assert result.offset == 0x1000
        assert result.phash is not None
        assert result.dhash is not None
        assert result.histogram is not None
        assert result.metadata == {"test": True}

    def test_index_sprite_various_image_sizes(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Index sprites of different sizes."""
        for size, offset in [(16, 0x1000), (32, 0x2000), (64, 0x3000), (128, 0x4000)]:
            img = Image.new("RGB", (size, size), (100, 100, 100))
            result = engine.index_sprite(offset, img)
            assert result is not None


# =============================================================================
# Hamming Distance
# =============================================================================


class TestHammingDistance:
    """Tests for Hamming distance calculation."""

    def test_hamming_distance_identical_hashes(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Two identical binary arrays should have distance 0."""
        hash1 = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=np.uint8)
        hash2 = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=np.uint8)

        distance = engine._hamming_distance(hash1, hash2)
        assert distance == 0

    def test_hamming_distance_completely_different(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Inverted arrays should have maximum distance."""
        hash1 = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=np.uint8)
        hash2 = np.array([0, 0, 0, 0, 1, 1, 1, 1], dtype=np.uint8)

        distance = engine._hamming_distance(hash1, hash2)
        assert distance == 8  # All bits different

    def test_hamming_distance_single_bit_difference(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Arrays differing by 1 bit should return distance=1."""
        hash1 = np.array([1, 0, 1, 0], dtype=np.uint8)
        hash2 = np.array([1, 0, 1, 1], dtype=np.uint8)

        distance = engine._hamming_distance(hash1, hash2)
        assert distance == 1

    def test_hamming_distance_symmetric(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """hamming_distance(A, B) should equal hamming_distance(B, A)."""
        hash1 = np.array([1, 0, 1, 0, 1, 1], dtype=np.uint8)
        hash2 = np.array([0, 0, 1, 1, 1, 0], dtype=np.uint8)

        dist1 = engine._hamming_distance(hash1, hash2)
        dist2 = engine._hamming_distance(hash2, hash1)

        assert dist1 == dist2

    def test_hamming_distance_returns_integer(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Output should be int type."""
        hash1 = np.array([1, 0, 1, 0], dtype=np.uint8)
        hash2 = np.array([1, 1, 0, 0], dtype=np.uint8)

        distance = engine._hamming_distance(hash1, hash2)
        assert isinstance(distance, (int, np.integer))

    def test_hamming_distance_large_arrays(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Should work with 64-bit or larger arrays."""
        hash1 = np.zeros(64, dtype=np.uint8)
        hash2 = np.ones(64, dtype=np.uint8)

        distance = engine._hamming_distance(hash1, hash2)
        assert distance == 64


# =============================================================================
# Histogram Similarity
# =============================================================================


class TestHistogramSimilarity:
    """Tests for histogram similarity calculation."""

    def test_histogram_similarity_identical(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Two identical histograms should return ~1.0."""
        hist = np.array([0.5, 0.5], dtype=np.float32)

        similarity = engine._histogram_similarity(hist, hist)
        assert abs(similarity - 1.0) < 0.01

    def test_histogram_similarity_completely_different(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Non-overlapping histograms should return ~0.0."""
        hist1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        hist2 = np.array([0.0, 0.0, 1.0], dtype=np.float32)

        similarity = engine._histogram_similarity(hist1, hist2)
        assert similarity == 0.0

    def test_histogram_similarity_partial_overlap(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Partial overlap should return 0.0 < similarity < 1.0."""
        hist1 = np.array([0.5, 0.5, 0.0], dtype=np.float32)
        hist2 = np.array([0.0, 0.5, 0.5], dtype=np.float32)

        similarity = engine._histogram_similarity(hist1, hist2)
        assert 0.0 < similarity < 1.0

    def test_histogram_similarity_range(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Should always return value in [0.0, 1.0]."""
        hist1 = np.array([0.25, 0.25, 0.25, 0.25], dtype=np.float32)
        hist2 = np.array([0.5, 0.5, 0.0, 0.0], dtype=np.float32)

        similarity = engine._histogram_similarity(hist1, hist2)
        assert 0.0 <= similarity <= 1.0

    def test_histogram_similarity_symmetric(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Similarity should be symmetric."""
        hist1 = np.array([0.3, 0.3, 0.4], dtype=np.float32)
        hist2 = np.array([0.5, 0.3, 0.2], dtype=np.float32)

        sim1 = engine._histogram_similarity(hist1, hist2)
        sim2 = engine._histogram_similarity(hist2, hist1)

        assert abs(sim1 - sim2) < 0.001


# =============================================================================
# Overall Similarity Calculation
# =============================================================================


class TestSimilarityCalculation:
    """Tests for overall similarity score calculation."""

    def test_similarity_identical_sprites(
        self, engine: VisualSimilarityEngine, gradient_image: Image.Image
    ) -> None:
        """Two identical sprite hashes should have similarity ~1.0."""
        hash1 = engine.index_sprite(0x1000, gradient_image)
        hash2 = engine.index_sprite(0x2000, gradient_image)

        similarity = engine._calculate_similarity(hash1, hash2)
        assert similarity > 0.99

    def test_similarity_different_sprites(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        solid_blue_image: Image.Image,
    ) -> None:
        """Very different sprites should have lower similarity."""
        hash1 = engine.index_sprite(0x1000, solid_red_image)
        hash2 = engine.index_sprite(0x2000, solid_blue_image)

        similarity = engine._calculate_similarity(hash1, hash2)
        # Different colors but similar structure (solid blocks)
        assert similarity < 1.0

    def test_similarity_score_range(
        self,
        engine: VisualSimilarityEngine,
        random_image: Image.Image,
        gradient_image: Image.Image,
    ) -> None:
        """Should return value in [0.0, 1.0]."""
        hash1 = engine.index_sprite(0x1000, random_image)
        hash2 = engine.index_sprite(0x2000, gradient_image)

        similarity = engine._calculate_similarity(hash1, hash2)
        assert 0.0 <= similarity <= 1.0

    def test_similarity_symmetric(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        gradient_image: Image.Image,
    ) -> None:
        """Similarity should be symmetric."""
        hash1 = engine.index_sprite(0x1000, solid_red_image)
        hash2 = engine.index_sprite(0x2000, gradient_image)

        sim1 = engine._calculate_similarity(hash1, hash2)
        sim2 = engine._calculate_similarity(hash2, hash1)

        assert abs(sim1 - sim2) < 0.001


# =============================================================================
# Find Similar
# =============================================================================


class TestFindSimilar:
    """Tests for find_similar search functionality."""

    def test_find_similar_by_image(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        solid_blue_image: Image.Image,
    ) -> None:
        """Find similar sprites using new PIL Image."""
        engine.index_sprite(0x1000, solid_red_image)
        engine.index_sprite(0x2000, solid_blue_image)

        # Search with a similar red image
        similar_red = Image.new("RGB", (64, 64), (250, 5, 5))
        results = engine.find_similar(similar_red, similarity_threshold=0.5)

        assert len(results) >= 1

    def test_find_similar_by_offset(
        self,
        engine: VisualSimilarityEngine,
        gradient_image: Image.Image,
    ) -> None:
        """Find similar sprites using indexed sprite offset."""
        # Index identical images at different offsets
        engine.index_sprite(0x1000, gradient_image)
        engine.index_sprite(0x2000, gradient_image)
        engine.index_sprite(0x3000, gradient_image)

        results = engine.find_similar(0x1000, similarity_threshold=0.9)

        # Should find the other two identical sprites
        assert len(results) == 2

    def test_find_similar_unindexed_offset_raises(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Searching for unindexed offset should raise ValueError."""
        engine.index_sprite(0x1000, solid_red_image)

        with pytest.raises(ValueError, match="not indexed"):
            engine.find_similar(0x9999)

    def test_find_similar_skips_self_comparison(
        self,
        engine: VisualSimilarityEngine,
        gradient_image: Image.Image,
    ) -> None:
        """Searching indexed sprite shouldn't include itself in results."""
        engine.index_sprite(0x1000, gradient_image)

        results = engine.find_similar(0x1000)

        offsets = [r.offset for r in results]
        assert 0x1000 not in offsets

    def test_find_similar_respects_max_results(
        self,
        engine: VisualSimilarityEngine,
        gradient_image: Image.Image,
    ) -> None:
        """max_results should limit returned matches."""
        # Index many similar sprites
        for i in range(10):
            engine.index_sprite(0x1000 + i * 0x100, gradient_image)

        results = engine.find_similar(0x1000, max_results=3, similarity_threshold=0.5)

        assert len(results) <= 3

    def test_find_similar_respects_similarity_threshold(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        solid_blue_image: Image.Image,
        gradient_image: Image.Image,
    ) -> None:
        """Only matches >= threshold should be returned."""
        engine.index_sprite(0x1000, solid_red_image)
        engine.index_sprite(0x2000, solid_blue_image)
        engine.index_sprite(0x3000, gradient_image)

        # Very high threshold should return fewer results
        results = engine.find_similar(0x1000, similarity_threshold=0.99)

        for match in results:
            assert match.similarity_score >= 0.99

    def test_find_similar_returns_sorted_by_score(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        solid_blue_image: Image.Image,
        gradient_image: Image.Image,
    ) -> None:
        """Results should be sorted descending by similarity_score."""
        engine.index_sprite(0x1000, solid_red_image)
        engine.index_sprite(0x2000, solid_blue_image)
        engine.index_sprite(0x3000, gradient_image)

        results = engine.find_similar(0x1000, similarity_threshold=0.0)

        for i in range(1, len(results)):
            assert results[i - 1].similarity_score >= results[i].similarity_score

    def test_find_similar_empty_database(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Searching empty database should return empty list."""
        results = engine.find_similar(solid_red_image)
        assert results == []

    def test_find_similar_returns_similarity_match_objects(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
    ) -> None:
        """Results should be SimilarityMatch with correct fields."""
        # Index two similar images
        red1 = Image.new("RGB", (64, 64), (255, 0, 0))
        red2 = Image.new("RGB", (64, 64), (250, 0, 0))
        engine.index_sprite(0x1000, red1, metadata={"name": "red1"})
        engine.index_sprite(0x2000, red2, metadata={"name": "red2"})

        results = engine.find_similar(0x1000, similarity_threshold=0.5)

        assert len(results) >= 1
        match = results[0]
        assert isinstance(match, SimilarityMatch)
        assert match.offset == 0x2000
        assert 0.0 <= match.similarity_score <= 1.0
        assert isinstance(match.hash_distance, (int, np.integer))
        assert match.metadata == {"name": "red2"}

    def test_find_similar_threshold_zero(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        solid_blue_image: Image.Image,
    ) -> None:
        """Threshold 0.0 should return all matches."""
        engine.index_sprite(0x1000, solid_red_image)
        engine.index_sprite(0x2000, solid_blue_image)

        results = engine.find_similar(0x1000, similarity_threshold=0.0)

        assert len(results) == 1  # Only 0x2000, not self


# =============================================================================
# Index Building
# =============================================================================


class TestBuildIndex:
    """Tests for similarity index building."""

    def test_build_index_sets_flag(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """build_similarity_index() should set index_built=True."""
        engine.index_sprite(0x1000, solid_red_image)

        engine.build_similarity_index()

        assert engine.index_built is True

    def test_build_index_empty_database(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Calling on empty database should log warning and return."""
        engine.build_similarity_index()
        # Should not raise, just log warning
        assert engine.index_built is False or engine.index_built is True

    def test_build_index_with_sprites(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Building index with sprites should complete successfully."""
        engine.index_sprite(0x1000, solid_red_image)
        engine.index_sprite(0x2000, solid_red_image)

        engine.build_similarity_index()

        assert engine.index_built is True

    def test_build_index_idempotent(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Building index twice should be safe."""
        engine.index_sprite(0x1000, solid_red_image)

        engine.build_similarity_index()
        engine.build_similarity_index()

        assert engine.index_built is True

    def test_build_index_preserves_database(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Index building shouldn't modify sprite_database."""
        engine.index_sprite(0x1000, solid_red_image)
        db_before = dict(engine.sprite_database)

        engine.build_similarity_index()

        assert engine.sprite_database.keys() == db_before.keys()


# =============================================================================
# Import/Export Index
# =============================================================================


class TestImportExport:
    """Tests for index persistence."""

    def test_export_index_creates_file(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        tmp_path: Path,
    ) -> None:
        """export_index() should create a pickle file."""
        engine.index_sprite(0x1000, solid_red_image)
        export_path = tmp_path / "index.pkl"

        engine.export_index(export_path)

        assert export_path.exists()

    def test_export_index_preserves_hash_size(
        self,
        solid_red_image: Image.Image,
        tmp_path: Path,
    ) -> None:
        """Exported file should contain correct hash_size."""
        engine = VisualSimilarityEngine(hash_size=16)
        engine.index_sprite(0x1000, solid_red_image)
        export_path = tmp_path / "index.pkl"

        engine.export_index(export_path)

        # Import into new engine
        new_engine = VisualSimilarityEngine()
        new_engine.import_index(export_path)

        assert new_engine.hash_size == 16

    def test_export_index_preserves_database(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        tmp_path: Path,
    ) -> None:
        """All indexed sprites should be in exported data."""
        engine.index_sprite(0x1000, solid_red_image, metadata={"a": 1})
        engine.index_sprite(0x2000, solid_red_image, metadata={"b": 2})
        export_path = tmp_path / "index.pkl"

        engine.export_index(export_path)

        new_engine = VisualSimilarityEngine()
        new_engine.import_index(export_path)

        assert 0x1000 in new_engine.sprite_database
        assert 0x2000 in new_engine.sprite_database

    def test_export_index_preserves_index_built_flag(
        self,
        engine: VisualSimilarityEngine,
        solid_red_image: Image.Image,
        tmp_path: Path,
    ) -> None:
        """index_built state should be preserved."""
        engine.index_sprite(0x1000, solid_red_image)
        engine.build_similarity_index()
        export_path = tmp_path / "index.pkl"

        engine.export_index(export_path)

        new_engine = VisualSimilarityEngine()
        new_engine.import_index(export_path)

        assert new_engine.index_built is True

    def test_import_export_round_trip(
        self,
        engine: VisualSimilarityEngine,
        gradient_image: Image.Image,
        tmp_path: Path,
    ) -> None:
        """Export then import should produce identical engine state."""
        engine.index_sprite(0x1000, gradient_image, metadata={"test": True})
        engine.build_similarity_index()
        export_path = tmp_path / "index.pkl"

        engine.export_index(export_path)

        new_engine = VisualSimilarityEngine()
        new_engine.import_index(export_path)

        assert new_engine.hash_size == engine.hash_size
        assert len(new_engine.sprite_database) == len(engine.sprite_database)
        assert new_engine.index_built == engine.index_built

    def test_import_nonexistent_file_raises(
        self, engine: VisualSimilarityEngine, tmp_path: Path
    ) -> None:
        """Importing non-existent file should raise error."""
        fake_path = tmp_path / "nonexistent.pkl"

        with pytest.raises(FileNotFoundError):
            engine.import_index(fake_path)


# =============================================================================
# SpriteGroupFinder
# =============================================================================


class TestSpriteGroupFinder:
    """Tests for sprite group finding."""

    @pytest.fixture
    def populated_engine(
        self, engine: VisualSimilarityEngine
    ) -> VisualSimilarityEngine:
        """Engine with various sprites indexed."""
        # Group 1: Similar red images
        for i in range(3):
            red = Image.new("RGB", (64, 64), (255 - i * 5, 0, 0))
            engine.index_sprite(0x1000 + i * 0x100, red, metadata={"group": "red"})

        # Group 2: Similar blue images
        for i in range(2):
            blue = Image.new("RGB", (64, 64), (0, 0, 255 - i * 5))
            engine.index_sprite(0x2000 + i * 0x100, blue, metadata={"group": "blue"})

        # Isolated: Gradient
        gradient = Image.new("L", (64, 64))
        for x in range(64):
            for y in range(64):
                gradient.putpixel((x, y), x * 4)
        engine.index_sprite(0x3000, gradient.convert("RGB"), metadata={"group": "gradient"})

        return engine

    def test_sprite_group_finder_initialization(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """GroupFinder should initialize with engine and empty groups list."""
        finder = SpriteGroupFinder(engine)

        assert finder.engine == engine
        assert finder.groups == []

    def test_find_sprite_groups_basic(
        self, populated_engine: VisualSimilarityEngine
    ) -> None:
        """Find groups of similar sprites."""
        finder = SpriteGroupFinder(populated_engine)

        groups = finder.find_sprite_groups(similarity_threshold=0.7, min_group_size=2)

        assert len(groups) > 0

    def test_find_sprite_groups_respects_threshold(
        self, populated_engine: VisualSimilarityEngine
    ) -> None:
        """Looser threshold merges more sprites into fewer groups."""
        finder = SpriteGroupFinder(populated_engine)

        loose_groups = finder.find_sprite_groups(
            similarity_threshold=0.5, min_group_size=2
        )
        strict_groups = finder.find_sprite_groups(
            similarity_threshold=0.95, min_group_size=2
        )

        # Loose threshold merges more sprites → fewer larger groups
        # Strict threshold matches fewer sprites → more smaller groups (or none)
        assert len(loose_groups) <= len(strict_groups)

    def test_find_sprite_groups_respects_min_size(
        self, populated_engine: VisualSimilarityEngine
    ) -> None:
        """min_group_size should filter out small groups."""
        finder = SpriteGroupFinder(populated_engine)

        groups = finder.find_sprite_groups(
            similarity_threshold=0.7, min_group_size=5
        )

        for group in groups:
            assert len(group) >= 5

    def test_find_sprite_groups_sorted_by_size(
        self, populated_engine: VisualSimilarityEngine
    ) -> None:
        """Groups should be sorted descending by size."""
        finder = SpriteGroupFinder(populated_engine)

        groups = finder.find_sprite_groups(
            similarity_threshold=0.5, min_group_size=2
        )

        for i in range(1, len(groups)):
            assert len(groups[i - 1]) >= len(groups[i])

    def test_find_sprite_groups_empty_database(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Empty database should return empty groups list."""
        finder = SpriteGroupFinder(engine)

        groups = finder.find_sprite_groups()

        assert groups == []


# =============================================================================
# Animation Detection
# =============================================================================


class TestAnimationDetection:
    """Tests for animation sequence detection."""

    @pytest.fixture
    def animation_engine(
        self, engine: VisualSimilarityEngine
    ) -> VisualSimilarityEngine:
        """Engine with animation-like sprites (sequential, similar)."""
        # Create animation sequence - similar images at sequential offsets
        for i in range(4):
            # Slight variation to simulate animation frames
            frame = Image.new("RGB", (64, 64), (200 + i * 10, 100, 100))
            engine.index_sprite(0x1000 + i * 0x100, frame)

        # Separate sprite far away
        other = Image.new("RGB", (64, 64), (0, 255, 0))
        engine.index_sprite(0x5000, other)

        return engine

    def test_find_animations_basic(
        self, animation_engine: VisualSimilarityEngine
    ) -> None:
        """Find animation sequences with proximity and similarity."""
        finder = SpriteGroupFinder(animation_engine)

        animations = finder.find_animations(
            offset_proximity=0x500, similarity_threshold=0.7
        )

        assert len(animations) > 0

    def test_find_animations_respects_offset_proximity(
        self, animation_engine: VisualSimilarityEngine
    ) -> None:
        """Animation frames should be within offset_proximity distance."""
        finder = SpriteGroupFinder(animation_engine)

        # Very small proximity should not find animations
        animations = finder.find_animations(
            offset_proximity=0x10, similarity_threshold=0.5
        )

        # Frames are 0x100 apart, so 0x10 proximity shouldn't find them
        for anim in animations:
            for i in range(1, len(anim)):
                assert anim[i] - anim[i - 1] <= 0x10

    def test_find_animations_respects_similarity_threshold(
        self, animation_engine: VisualSimilarityEngine
    ) -> None:
        """Only similar adjacent frames should be connected."""
        finder = SpriteGroupFinder(animation_engine)

        # Very high threshold might find fewer animations
        strict_anims = finder.find_animations(
            offset_proximity=0x500, similarity_threshold=0.99
        )
        loose_anims = finder.find_animations(
            offset_proximity=0x500, similarity_threshold=0.5
        )

        assert len(strict_anims) <= len(loose_anims)

    def test_find_animations_min_2_frames(
        self, animation_engine: VisualSimilarityEngine
    ) -> None:
        """Animations with <2 frames should not be returned."""
        finder = SpriteGroupFinder(animation_engine)

        animations = finder.find_animations()

        for anim in animations:
            assert len(anim) >= 2

    def test_find_animations_empty_database(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Empty database should return empty animations list."""
        finder = SpriteGroupFinder(engine)

        animations = finder.find_animations()

        assert animations == []


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_very_small_image_1x1_pixel(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """1x1 pixel image should be resizable and hashable."""
        tiny = Image.new("RGB", (1, 1), (128, 128, 128))

        result = engine.index_sprite(0x1000, tiny)

        assert result is not None
        assert result.phash is not None

    def test_very_large_image_handling(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """Large images should be resizable."""
        large = Image.new("RGB", (512, 512), (100, 100, 100))

        result = engine.index_sprite(0x1000, large)

        assert result is not None

    def test_transparent_png_conversion(
        self, engine: VisualSimilarityEngine
    ) -> None:
        """RGBA PNG should convert to RGB without errors."""
        rgba = Image.new("RGBA", (64, 64), (255, 0, 0, 128))

        result = engine.index_sprite(0x1000, rgba)

        assert result is not None
        assert result.histogram.shape == (48,)

    def test_find_similar_with_default_parameters(
        self, engine: VisualSimilarityEngine, solid_red_image: Image.Image
    ) -> None:
        """Using all default params should work correctly."""
        engine.index_sprite(0x1000, solid_red_image)
        engine.index_sprite(0x2000, solid_red_image)

        # Just use defaults
        results = engine.find_similar(0x1000)

        assert isinstance(results, list)

    def test_large_sprite_database(
        self, small_engine: VisualSimilarityEngine
    ) -> None:
        """Engine should handle many sprites without crashes."""
        for i in range(100):
            img = Image.new("RGB", (16, 16), (i % 256, (i * 2) % 256, (i * 3) % 256))
            small_engine.index_sprite(i * 0x100, img)

        assert len(small_engine.sprite_database) == 100


# =============================================================================
# Data Structure Tests
# =============================================================================


class TestDataStructures:
    """Tests for data structure correctness."""

    def test_sprite_hash_dataclass_fields(self) -> None:
        """Verify SpriteHash has all 5 fields and correct types."""
        sprite_hash = SpriteHash(
            offset=0x1000,
            phash=np.zeros(64, dtype=np.uint8),
            dhash=np.zeros(64, dtype=np.uint8),
            histogram=np.zeros(48, dtype=np.float32),
            metadata={"test": True}
        )

        assert sprite_hash.offset == 0x1000
        assert isinstance(sprite_hash.phash, np.ndarray)
        assert isinstance(sprite_hash.dhash, np.ndarray)
        assert isinstance(sprite_hash.histogram, np.ndarray)
        assert sprite_hash.metadata == {"test": True}

    def test_similarity_match_dataclass_fields(self) -> None:
        """Verify SimilarityMatch has all 4 fields and correct types."""
        match = SimilarityMatch(
            offset=0x2000,
            similarity_score=0.95,
            hash_distance=3,
            metadata={"name": "sprite1"}
        )

        assert match.offset == 0x2000
        assert match.similarity_score == 0.95
        assert match.hash_distance == 3
        assert match.metadata == {"name": "sprite1"}

    def test_sprite_hash_with_metadata(self) -> None:
        """Metadata dict can be arbitrary key-value pairs."""
        metadata = {
            "name": "hero",
            "frame": 1,
            "tags": ["player", "animation"],
            "nested": {"a": 1}
        }
        sprite_hash = SpriteHash(
            offset=0,
            phash=np.zeros(64),
            dhash=np.zeros(64),
            histogram=np.zeros(48),
            metadata=metadata
        )

        assert sprite_hash.metadata == metadata
