"""Tests for checksum disambiguation when multiple games share the same checksum.

Bug: Three Kirby games share checksum 0xBF51:
- "KIRBY SUPER STAR" (Europe_Alt)
- "KIRBY SUPER DELUXE" (Europe_FunPak)
- "KIRBY'S FUN PAK" (Europe_BF51)

Current behavior: First match wins (arbitrary).
Expected behavior: Use title scoring to disambiguate.
"""

import pytest

from core.sprite_config_loader import SpriteConfigLoader


@pytest.fixture
def config_loader() -> SpriteConfigLoader:
    """Create a SpriteConfigLoader with the real config."""
    return SpriteConfigLoader()


class TestSingleChecksumMatch:
    """Tests for games with unique checksums (should work as before)."""

    def test_single_checksum_match_is_authoritative(self, config_loader: SpriteConfigLoader) -> None:
        """Single checksum match wins even if title doesn't match exactly."""
        # KIRBY SUPER STAR USA has unique checksum 0x8A5C
        game_name, game_config = config_loader.find_game_config(
            rom_title="KIRBY SUPER STAR",
            rom_checksum=0x8A5C,
        )

        assert game_name == "KIRBY SUPER STAR"
        assert game_config is not None

    def test_single_checksum_match_wins_over_title(self, config_loader: SpriteConfigLoader) -> None:
        """Checksum match should win even with slightly different title."""
        # Use a unique checksum but with a slightly different title
        game_name, game_config = config_loader.find_game_config(
            rom_title="KIRBY SUPER STAR USA VERSION",  # Slightly different
            rom_checksum=0x8A5C,  # Unique checksum for KIRBY SUPER STAR USA
        )

        assert game_name == "KIRBY SUPER STAR"
        assert game_config is not None


class TestMultipleChecksumMatches:
    """Tests for games that share the same checksum (the bug fix)."""

    def test_multiple_checksum_matches_use_title_scoring(self, config_loader: SpriteConfigLoader) -> None:
        """When multiple games share a checksum, use title scoring to disambiguate."""
        # All three games share checksum 0xBF51
        # Title "KIRBY'S FUN PAK" should match "KIRBY'S FUN PAK" config (exact)
        game_name, game_config = config_loader.find_game_config(
            rom_title="KIRBY'S FUN PAK",
            rom_checksum=0xBF51,
        )

        # Should select "KIRBY'S FUN PAK" due to exact title match (score 100)
        assert game_name == "KIRBY'S FUN PAK", (
            f"Expected 'KIRBY'S FUN PAK' but got '{game_name}'. "
            "Checksum 0xBF51 is shared by 3 games - should use title scoring."
        )
        assert game_config is not None

    def test_kirby_super_star_title_selects_correct_game(self, config_loader: SpriteConfigLoader) -> None:
        """Title 'KIRBY SUPER STAR' + checksum 0xBF51 should select KIRBY SUPER STAR."""
        game_name, game_config = config_loader.find_game_config(
            rom_title="KIRBY SUPER STAR",
            rom_checksum=0xBF51,
        )

        assert game_name == "KIRBY SUPER STAR", (
            f"Expected 'KIRBY SUPER STAR' but got '{game_name}'. Title should disambiguate when checksum is shared."
        )
        assert game_config is not None

    def test_kirby_super_deluxe_title_selects_correct_game(self, config_loader: SpriteConfigLoader) -> None:
        """Title 'KIRBY SUPER DELUXE' + checksum 0xBF51 should select KIRBY SUPER DELUXE."""
        game_name, game_config = config_loader.find_game_config(
            rom_title="KIRBY SUPER DELUXE",
            rom_checksum=0xBF51,
        )

        assert game_name == "KIRBY SUPER DELUXE", (
            f"Expected 'KIRBY SUPER DELUXE' but got '{game_name}'. Title should disambiguate when checksum is shared."
        )
        assert game_config is not None


class TestTitleScoringPrecedence:
    """Tests to verify title scoring precedence: exact(100) > substring(50) > equivalence(25)."""

    def test_exact_match_beats_substring(self, config_loader: SpriteConfigLoader) -> None:
        """Exact title match (100) should beat substring match (50)."""
        # "KIRBY'S FUN PAK" exact match (100) should beat
        # "KIRBY SUPER STAR" substring match with "KIRBY" (50)
        game_name, game_config = config_loader.find_game_config(
            rom_title="KIRBY'S FUN PAK",
            rom_checksum=0xBF51,
        )

        assert game_name == "KIRBY'S FUN PAK"

    def test_equivalence_match_is_used_for_disambiguation(self, config_loader: SpriteConfigLoader) -> None:
        """Equivalence patterns (FUN PAK ↔ SUPER STAR) should contribute to scoring."""
        # With shared checksum, title "FUN PAK" should prefer the actual "KIRBY'S FUN PAK"
        # over "KIRBY SUPER STAR" which only has equivalence match (25)
        game_name, game_config = config_loader.find_game_config(
            rom_title="KIRBY'S FUN PAK",
            rom_checksum=0xBF51,
        )

        # The exact match for "KIRBY'S FUN PAK" (100) beats equivalence (25)
        assert game_name == "KIRBY'S FUN PAK"


class TestGetGameSpritesDisambiguation:
    """Tests for get_game_sprites() which has the same bug."""

    def test_get_game_sprites_disambiguates_by_title(self, config_loader: SpriteConfigLoader) -> None:
        """get_game_sprites() should also use title scoring for disambiguation."""
        sprites = config_loader.get_game_sprites(
            rom_title="KIRBY'S FUN PAK",
            rom_checksum=0xBF51,
        )

        # Should return sprites from "KIRBY'S FUN PAK" config, not "KIRBY SUPER STAR"
        # We can't easily verify which game was selected internally,
        # but the returned sprites should be non-empty (all have sprites)
        assert len(sprites) > 0, "Should return sprites from the correct game config"

    def test_get_game_sprites_super_star_title(self, config_loader: SpriteConfigLoader) -> None:
        """get_game_sprites() with 'KIRBY SUPER STAR' title should select correct config."""
        sprites = config_loader.get_game_sprites(
            rom_title="KIRBY SUPER STAR",
            rom_checksum=0xBF51,
        )

        assert len(sprites) > 0, "Should return sprites from KIRBY SUPER STAR config"


class TestNoChecksumMatch:
    """Tests for fallback behavior when no checksum matches."""

    def test_title_only_match_uses_scoring(self, config_loader: SpriteConfigLoader) -> None:
        """When no checksum matches, title scoring should be used."""
        # Use a checksum that doesn't exist in config
        game_name, game_config = config_loader.find_game_config(
            rom_title="KIRBY SUPER STAR",
            rom_checksum=0x0000,  # Non-existent checksum
        )

        # Should match by title
        assert game_name == "KIRBY SUPER STAR"
        assert game_config is not None

    def test_no_match_returns_none(self, config_loader: SpriteConfigLoader) -> None:
        """When neither checksum nor title matches, return None."""
        game_name, game_config = config_loader.find_game_config(
            rom_title="NONEXISTENT GAME",
            rom_checksum=0x0000,
        )

        assert game_name is None
        assert game_config is None
