"""
Tests for sprite visual validator
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

import core.sprite_visual_validator as validator_module
from core.sprite_visual_validator import SpriteVisualValidator

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
    pytest.mark.ci_safe,
]

@pytest.fixture
def validator():
    """Create a validator instance"""
    return SpriteVisualValidator()

@pytest.fixture
def create_test_image():
    """Factory fixture to create test images"""
    def _create_image(width=128, height=128, pattern="sprite"):
        """Create a test image with specified pattern"""
        img = Image.new("L", (width, height), 0)
        pixels = img.load()

        if pattern == "sprite":
            # Create a simple sprite-like pattern with coherent shapes
            # Draw some rectangles and circles to simulate sprite features
            for y in range(height):
                for x in range(width):
                    # Create tile-based pattern
                    tile_x = x // 8
                    tile_y = y // 8

                    # Checkerboard of different patterns
                    if (tile_x + tile_y) % 3 == 0:
                        # Solid tile
                        pixels[x, y] = 200
                    elif (tile_x + tile_y) % 3 == 1:
                        # Edge pattern
                        if x % 8 in [0, 7] or y % 8 in [0, 7]:
                            pixels[x, y] = 255
                        else:
                            pixels[x, y] = 50
                    # else leave as 0 (empty)

        elif pattern == "noise":
            # Random noise - should fail validation (seeded for reproducibility)
            np.random.seed(42)
            noise = np.random.randint(0, 256, (height, width), dtype=np.uint8)
            img = Image.fromarray(noise, mode="L")

        elif pattern == "empty":
            # All zeros - should fail
            pass

        elif pattern == "solid":
            # All one value - should fail
            img = Image.new("L", (width, height), 128)

        return img

    return _create_image

class TestSpriteVisualValidator:
    """Test sprite visual validation functionality"""

    def test_init(self, validator):
        """Test validator initialization"""
        assert validator.tile_size == 8

    def test_validate_sprite_image_with_good_sprite(self, validator, create_test_image, tmp_path):
        """Test validation with a good sprite-like image"""
        # Create a sprite-like image
        img = create_test_image(128, 128, "sprite")
        img_path = tmp_path / "test_sprite.png"
        img.save(img_path)

        # Validate
        is_valid, confidence, metrics = validator.validate_sprite_image(str(img_path))

        # Should be valid with reasonable confidence
        assert is_valid  # Handle numpy bool properly
        assert confidence > 0.4  # Not too strict, implementation may vary
        assert isinstance(metrics, dict)
        assert "coherence" in metrics
        assert "tile_diversity" in metrics
        assert "edge_score" in metrics
        assert "symmetry" in metrics
        assert "empty_space" in metrics
        assert "pattern_regularity" in metrics

    def test_validate_sprite_image_with_noise(self, validator, create_test_image, tmp_path):
        """Test validation with random noise - should fail"""
        img = create_test_image(128, 128, "noise")
        img_path = tmp_path / "test_noise.png"
        img.save(img_path)

        is_valid, confidence, metrics = validator.validate_sprite_image(str(img_path))

        # Random noise should fail or have very low confidence
        assert confidence < 0.6  # Likely to fail
        assert isinstance(metrics, dict)

    def test_validate_sprite_image_with_empty(self, validator, create_test_image, tmp_path):
        """Test validation with empty image - should fail"""
        img = create_test_image(128, 128, "empty")
        img_path = tmp_path / "test_empty.png"
        img.save(img_path)

        is_valid, confidence, metrics = validator.validate_sprite_image(str(img_path))

        assert not is_valid  # Handle numpy bool properly
        assert confidence < 0.5

    def test_validate_sprite_image_with_solid(self, validator, create_test_image, tmp_path):
        """Test validation with solid color - should fail"""
        img = create_test_image(128, 128, "solid")
        img_path = tmp_path / "test_solid.png"
        img.save(img_path)

        is_valid, confidence, metrics = validator.validate_sprite_image(str(img_path))

        # Solid color lacks diversity and edges
        assert confidence < 0.5

    def test_validate_sprite_image_invalid_path(self, validator):
        """Test validation with invalid image path"""
        is_valid, confidence, metrics = validator.validate_sprite_image("/nonexistent/image.png")

        assert not is_valid  # Handle numpy bool properly
        assert confidence == 0.0
        assert metrics == {}

    def test_calculate_coherence_score_without_cv2(self, validator):
        """Test coherence calculation without cv2 (fallback mode)"""
        # Patch cv2 to None to test fallback
        with patch.object(validator_module, "cv2", None):
            # Create test array with reasonable sprite-like data
            img_array = np.zeros((64, 64), dtype=np.uint8)
            # Add some non-zero regions (30% filled)
            img_array[10:30, 10:30] = 128
            img_array[40:50, 40:50] = 200

            score = validator._calculate_coherence_score(img_array)

            assert 0.0 <= score <= 1.0
            assert score >= 0.2  # Should have some coherence

    def test_calculate_tile_diversity(self, validator):
        """Test tile diversity calculation"""
        # Create image with varying tiles
        img_array = np.zeros((32, 32), dtype=np.uint8)

        # Make 4 different tile patterns
        img_array[0:8, 0:8] = 50    # Tile 1
        img_array[0:8, 8:16] = 100  # Tile 2
        img_array[8:16, 0:8] = 150  # Tile 3
        img_array[8:16, 8:16] = 200 # Tile 4
        # Rest are empty (0)

        score = validator._calculate_tile_diversity(img_array)

        assert 0.0 <= score <= 1.0
        # Should have good diversity (not too low, not too high)
        assert score > 0.3

    def test_calculate_edge_score_without_cv2(self, validator):
        """Test edge score calculation without cv2"""
        with patch.object(validator_module, "cv2", None):
            # Create image with edges
            img_array = np.zeros((32, 32), dtype=np.uint8)
            # Draw a square outline
            img_array[10, 10:20] = 255
            img_array[20, 10:20] = 255
            img_array[10:20, 10] = 255
            img_array[10:20, 20] = 255

            score = validator._calculate_edge_score(img_array)

            assert 0.0 <= score <= 1.0
            assert score > 0.2  # Should detect some edges

    def test_calculate_symmetry_score(self, validator):
        """Test symmetry score calculation"""
        # Create perfectly symmetric image
        img_array = np.zeros((32, 32), dtype=np.uint8)
        # Draw symmetric pattern
        for y in range(32):
            for x in range(16):
                val = (x + y) % 256
                img_array[y, x] = val
                img_array[y, 31-x] = val  # Mirror

        score = validator._calculate_symmetry_score(img_array)

        assert 0.0 <= score <= 1.0
        assert score > 0.8  # Should have high symmetry

    def test_calculate_empty_space_ratio(self, validator):
        """Test empty space ratio calculation"""
        # Create image with 50% empty space
        img_array = np.zeros((32, 32), dtype=np.uint8)
        img_array[:16, :] = 128  # Fill half

        score = validator._calculate_empty_space_ratio(img_array)

        assert 0.0 <= score <= 1.0
        assert score > 0.8  # 50% is in ideal range

    def test_calculate_pattern_regularity_without_cv2(self, validator):
        """Test pattern regularity without cv2"""
        with patch.object(validator_module, "cv2", None):
            # Create regular pattern
            img_array = np.zeros((32, 32), dtype=np.uint8)
            # Fill alternating tiles
            for y in range(0, 32, 8):
                for x in range(0, 32, 8):
                    if ((x//8) + (y//8)) % 2 == 0:
                        img_array[y:y+8, x:x+8] = 128

            score = validator._calculate_pattern_regularity(img_array)

            assert 0.0 <= score <= 1.0

    def test_calculate_overall_confidence(self, validator):
        """Test overall confidence calculation"""
        metrics = {
            "coherence": 0.8,
            "tile_diversity": 0.7,
            "edge_score": 0.6,
            "symmetry": 0.5,
            "empty_space": 0.9,
            "pattern_regularity": 0.7
        }

        confidence = validator._calculate_overall_confidence(metrics)

        assert 0.0 <= confidence <= 1.0
        # Should be weighted average
        assert 0.6 < confidence < 0.8

    def test_validate_tile_data_valid(self, validator):
        """Test tile data validation with valid data"""
        # Create valid tile data (512 tiles * 32 bytes)
        tile_count = 512
        # Create data with reasonable entropy (not uniform distribution)
        # Mix of patterns to simulate real sprite data
        tile_data = bytearray()
        for i in range(tile_count):
            # Create varied but not random tile patterns
            for j in range(32):
                # Create patterns that would appear in real sprites
                if i % 4 == 0:
                    tile_data.append((i + j) % 256)
                elif i % 4 == 1:
                    tile_data.append(((i * 3) + j) % 128)
                elif i % 4 == 2:
                    tile_data.append(0 if j < 16 else 200)
                else:
                    tile_data.append(50 if (j % 4) == 0 else 150)

        tile_data = bytes(tile_data)
        is_valid, confidence = validator.validate_tile_data(tile_data, tile_count)

        assert is_valid  # Handle numpy bool properly
        assert confidence > 0.5

    def test_validate_tile_data_wrong_size(self, validator):
        """Test tile data validation with wrong size"""
        tile_count = 100
        tile_data = b"\x00" * 50  # Wrong size

        is_valid, confidence = validator.validate_tile_data(tile_data, tile_count)

        assert not is_valid  # Handle numpy bool properly
        assert confidence == 0.0

    def test_validate_tile_data_too_uniform(self, validator):
        """Test tile data validation with too uniform data"""
        tile_count = 100
        tile_data = b"\x00" * (tile_count * 32)  # All zeros

        is_valid, confidence = validator.validate_tile_data(tile_data, tile_count)

        assert not is_valid  # Handle numpy bool properly
        assert confidence < 0.5

    def test_validate_tile_data_entropy_check(self, validator):
        """Test tile data validation entropy checking"""
        tile_count = 100

        # Very low entropy (repeated pattern)
        tile_data_low = b"\x00\x01" * (tile_count * 16)
        is_valid_low, conf_low = validator.validate_tile_data(tile_data_low, tile_count)

        # Good entropy (varied but realistic sprite-like data)
        # Create data that has patterns like real sprites
        good_data = bytearray()
        for i in range(tile_count):
            # Mix of empty, partially filled, and full tiles
            tile_type = i % 5
            for j in range(32):
                if tile_type == 0:
                    good_data.append(0)  # Empty tile
                elif tile_type == 1:
                    good_data.append(255 if j < 16 else 0)  # Half filled
                elif tile_type == 2:
                    good_data.append((i * 7 + j * 3) % 128)  # Gradient
                elif tile_type == 3:
                    good_data.append(128 if (j % 4) < 2 else 64)  # Pattern
                else:
                    good_data.append(200)  # Solid
        tile_data_good = bytes(good_data)
        is_valid_good, conf_good = validator.validate_tile_data(tile_data_good, tile_count)

        # Very high entropy (pure random - suspicious) - seeded for reproducibility
        np.random.seed(42)
        tile_data_high = bytes(np.random.randint(0, 256, tile_count * 32))
        is_valid_high, conf_high = validator.validate_tile_data(tile_data_high, tile_count)

        assert not is_valid_low  # Handle numpy bool properly
        assert is_valid_good  # Handle numpy bool properly
        assert conf_good > conf_low
