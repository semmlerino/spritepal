"""Tests for utils/color_distance.py - perceptual color distance utilities."""

from __future__ import annotations

from utils.color_distance import (
    detect_rare_important_colors,
    perceptual_distance,
    perceptual_distance_sq,
    rgb_distance_sq,
    rgb_to_lab,
)


class TestRgbToLab:
    """Tests for RGB to CIELAB conversion."""

    def test_black_converts_correctly(self) -> None:
        """Pure black should have L*=0."""
        lab = rgb_to_lab((0, 0, 0))
        assert abs(lab[0]) < 0.1, f"Black L* should be ~0, got {lab[0]}"

    def test_white_converts_correctly(self) -> None:
        """Pure white should have L*=100."""
        lab = rgb_to_lab((255, 255, 255))
        assert abs(lab[0] - 100) < 1, f"White L* should be ~100, got {lab[0]}"

    def test_gray_is_neutral(self) -> None:
        """Gray should have a*≈0 and b*≈0."""
        lab = rgb_to_lab((128, 128, 128))
        assert abs(lab[1]) < 1, f"Gray a* should be ~0, got {lab[1]}"
        assert abs(lab[2]) < 1, f"Gray b* should be ~0, got {lab[2]}"

    def test_red_has_positive_a(self) -> None:
        """Red should have positive a* (red-green axis)."""
        lab = rgb_to_lab((255, 0, 0))
        assert lab[1] > 40, f"Red a* should be positive, got {lab[1]}"

    def test_green_has_negative_a(self) -> None:
        """Green should have negative a* (red-green axis)."""
        lab = rgb_to_lab((0, 255, 0))
        assert lab[1] < -40, f"Green a* should be negative, got {lab[1]}"

    def test_blue_has_negative_b(self) -> None:
        """Blue should have negative b* (blue-yellow axis)."""
        lab = rgb_to_lab((0, 0, 255))
        assert lab[2] < -80, f"Blue b* should be negative, got {lab[2]}"

    def test_yellow_has_positive_b(self) -> None:
        """Yellow should have positive b* (blue-yellow axis)."""
        lab = rgb_to_lab((255, 255, 0))
        assert lab[2] > 80, f"Yellow b* should be positive, got {lab[2]}"

    def test_caches_results(self) -> None:
        """Function should be cached for performance."""
        # Call twice with same input
        _ = rgb_to_lab((100, 100, 100))
        _ = rgb_to_lab((100, 100, 100))
        # Check cache info
        cache_info = rgb_to_lab.cache_info()
        assert cache_info.hits >= 1, "Should have cache hits"


class TestPerceptualDistance:
    """Tests for perceptual color distance (Delta E)."""

    def test_identical_colors_have_zero_distance(self) -> None:
        """Same color should have distance = 0."""
        dist = perceptual_distance((128, 64, 32), (128, 64, 32))
        assert dist == 0.0

    def test_black_white_distance_is_large(self) -> None:
        """Black to white should have maximum luminance distance."""
        dist = perceptual_distance((0, 0, 0), (255, 255, 255))
        # L* difference is ~100, so distance should be ~100
        assert 90 < dist < 110, f"Black-white distance should be ~100, got {dist}"

    def test_similar_colors_have_small_distance(self) -> None:
        """Perceptually similar colors should have small distance."""
        # Two very similar grays
        dist = perceptual_distance((128, 128, 128), (130, 130, 130))
        assert dist < 3, f"Similar grays should have small distance, got {dist}"

    def test_jnd_threshold(self) -> None:
        """Just noticeable difference is ~2.3 in Delta E."""
        # Colors that are barely distinguishable should be around JND
        dist = perceptual_distance((128, 128, 128), (131, 131, 131))
        assert dist < 5, f"Near-JND colors should be <5, got {dist}"

    def test_perceptual_vs_rgb_on_eye_colors(self) -> None:
        """Perceptual distance should be different from RGB for tricky color pairs.

        This is the core use case: eye whites vs skin tones may have similar
        RGB distances but different perceptual distances.
        """
        eye_white = (250, 250, 250)  # Near-white eye
        skin_tone = (220, 180, 160)  # Warm skin
        cream = (255, 253, 240)  # Cream/highlight

        # Perceptual distances
        perceptual_white_skin = perceptual_distance(eye_white, skin_tone)
        perceptual_white_cream = perceptual_distance(eye_white, cream)

        # Eye white should be more similar to cream than to skin in perception
        assert perceptual_white_cream < perceptual_white_skin, (
            f"Perceptually, eye white should be closer to cream. "
            f"Cream dist={perceptual_white_cream:.1f}, Skin dist={perceptual_white_skin:.1f}"
        )


class TestPerceptualDistanceSq:
    """Tests for squared perceptual distance."""

    def test_squared_matches_non_squared(self) -> None:
        """Squared distance should be square of regular distance."""
        c1 = (100, 50, 200)
        c2 = (150, 75, 180)

        dist = perceptual_distance(c1, c2)
        dist_sq = perceptual_distance_sq(c1, c2)

        assert abs(dist_sq - dist * dist) < 0.001


class TestRgbDistanceSq:
    """Tests for RGB Euclidean distance."""

    def test_identical_colors(self) -> None:
        """Same colors should have zero distance."""
        assert rgb_distance_sq((100, 100, 100), (100, 100, 100)) == 0

    def test_known_distance(self) -> None:
        """Distance between (0,0,0) and (3,4,0) should be 25 (squared)."""
        # 3^2 + 4^2 + 0^2 = 9 + 16 + 0 = 25
        assert rgb_distance_sq((0, 0, 0), (3, 4, 0)) == 25


class TestDetectRareImportantColors:
    """Tests for rare important color detection."""

    def test_empty_input(self) -> None:
        """Empty color dict should return empty list."""
        result = detect_rare_important_colors({})
        assert result == []

    def test_finds_rare_distinct_colors(self) -> None:
        """Should detect colors that are rare and perceptually distinct."""
        # Common color (skin-like, many pixels)
        # Rare color (eye white, few pixels)
        color_counts = {
            (200, 160, 140): 9000,  # Common: skin tone (90%)
            (250, 250, 250): 50,  # Rare: eye white (0.5%)
            (190, 155, 135): 900,  # Common-ish: similar skin
            (30, 30, 30): 50,  # Rare: dark shadow
        }

        result = detect_rare_important_colors(
            color_counts,
            rarity_threshold=0.01,
            distinctness_threshold=15.0,
            max_candidates=5,
        )

        # Should find eye white and dark shadow as rare important colors
        rare_colors = [r[0] for r in result]
        assert len(result) > 0, "Should detect at least one rare color"
        assert (250, 250, 250) in rare_colors, "Eye white should be detected as rare important"
        assert (30, 30, 30) in rare_colors, "Dark shadow should be detected as rare important"

    def test_does_not_include_non_distinct_rare_colors(self) -> None:
        """Rare colors similar to common colors should not be flagged."""
        color_counts = {
            (128, 128, 128): 9000,  # Common: gray
            (130, 130, 130): 50,  # Rare but nearly identical to common
        }

        result = detect_rare_important_colors(
            color_counts,
            rarity_threshold=0.01,
            distinctness_threshold=20.0,
        )

        # The rare color is too similar to the common one
        rare_colors = [r[0] for r in result]
        assert (130, 130, 130) not in rare_colors, "Similar rare color should not be flagged"

    def test_respects_max_candidates(self) -> None:
        """Should limit results to max_candidates."""
        # Many distinct rare colors
        color_counts = {
            (128, 128, 128): 10000,  # Common base
        }
        # Add 10 distinct rare colors
        for i in range(10):
            color_counts[(50 + i * 20, 50, 50)] = 10

        result = detect_rare_important_colors(
            color_counts,
            rarity_threshold=0.01,
            distinctness_threshold=5.0,
            max_candidates=3,
        )

        assert len(result) <= 3, f"Should return at most 3 candidates, got {len(result)}"

    def test_sorts_by_distinctness(self) -> None:
        """Results should be sorted by distinctness (most distinct first)."""
        color_counts = {
            (128, 128, 128): 10000,  # Common: mid-gray
            (255, 255, 255): 50,  # Rare: white (very distinct from gray)
            (100, 100, 100): 50,  # Rare: dark gray (less distinct)
        }

        result = detect_rare_important_colors(
            color_counts,
            rarity_threshold=0.01,
            distinctness_threshold=5.0,
        )

        if len(result) >= 2:
            # White should be more distinct than dark gray
            assert result[0][2] >= result[1][2], "Should be sorted by distinctness descending"

    def test_returns_pixel_count_and_distance(self) -> None:
        """Each result should include color, pixel count, and distance."""
        color_counts = {
            (128, 128, 128): 10000,
            (255, 0, 0): 50,  # Rare red
        }

        result = detect_rare_important_colors(color_counts, rarity_threshold=0.01)

        if result:
            color, pixel_count, distance = result[0]
            assert isinstance(color, tuple), "Should return color tuple"
            assert len(color) == 3, "Color should have 3 components"
            assert isinstance(pixel_count, int), "Should return pixel count"
            assert isinstance(distance, float), "Should return distance"
            assert distance > 0, "Distance should be positive"


class TestPerceptualDistanceIntegration:
    """Integration tests for real-world color scenarios."""

    def test_kirby_eye_white_scenario(self) -> None:
        """Test the Kirby eye white scenario that motivated this change.

        Eye whites should map to white/cream colors rather than skin tones,
        even though the RGB distances might be similar.
        """
        # Simulated eye white from AI frame
        eye_white = (248, 248, 240)

        # Possible palette targets
        cream_white = (248, 248, 248)  # White palette slot
        skin_pink = (248, 200, 200)  # Kirby pink skin
        skin_peach = (240, 208, 176)  # Alternate skin tone

        # Calculate perceptual distances
        dist_to_white = perceptual_distance(eye_white, cream_white)
        dist_to_pink = perceptual_distance(eye_white, skin_pink)
        dist_to_peach = perceptual_distance(eye_white, skin_peach)

        # Eye white should be perceptually closest to cream white
        assert dist_to_white < dist_to_pink, (
            f"Eye white should be closer to white than pink. "
            f"White dist={dist_to_white:.1f}, Pink dist={dist_to_pink:.1f}"
        )
        assert dist_to_white < dist_to_peach, (
            f"Eye white should be closer to white than peach. "
            f"White dist={dist_to_white:.1f}, Peach dist={dist_to_peach:.1f}"
        )
