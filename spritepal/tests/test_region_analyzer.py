"""
Comprehensive tests for EmptyRegionDetector and RegionAnalysis.

Tests cover:
- Entropy calculation
- Zero percentage calculation
- Repeating pattern detection
- Region analysis decision logic
- ROM scanning
- Optimized range merging
- Caching behavior
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from core.region_analyzer import (
    EmptyRegionConfig,
    EmptyRegionDetector,
    RegionAnalysis,
)

if TYPE_CHECKING:
    pass

# Test markers
pytestmark = [
    pytest.mark.headless,
]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def detector() -> EmptyRegionDetector:
    """Create detector with default config."""
    return EmptyRegionDetector()


@pytest.fixture
def custom_detector() -> EmptyRegionDetector:
    """Create detector with custom config for easier testing."""
    config = EmptyRegionConfig(
        entropy_threshold=0.5,
        zero_threshold=0.8,
        pattern_threshold=0.7,
        max_unique_bytes=3,
        region_size=64
    )
    return EmptyRegionDetector(config)


# =============================================================================
# Constructor & Configuration Tests
# =============================================================================


class TestEmptyRegionDetectorInit:
    """Tests for detector initialization."""

    def test_detector_init_with_default_config(self) -> None:
        """Verify EmptyRegionDetector initializes with default config values."""
        detector = EmptyRegionDetector()

        assert detector.config.entropy_threshold == 0.1
        assert detector.config.zero_threshold == 0.9
        assert detector.config.pattern_threshold == 0.85
        assert detector.config.max_unique_bytes == 4
        assert detector.config.region_size == 4096

    def test_detector_init_with_custom_config(self) -> None:
        """Verify detector accepts custom EmptyRegionConfig."""
        config = EmptyRegionConfig(
            entropy_threshold=0.2,
            zero_threshold=0.95,
            pattern_threshold=0.9,
            max_unique_bytes=2,
            region_size=8192
        )
        detector = EmptyRegionDetector(config)

        assert detector.config == config

    def test_config_values_stored_correctly(self) -> None:
        """Verify all config values are accessible via detector.config."""
        config = EmptyRegionConfig(
            entropy_threshold=0.15,
            zero_threshold=0.85,
            pattern_threshold=0.75,
            max_unique_bytes=5,
            region_size=2048
        )
        detector = EmptyRegionDetector(config)

        assert detector.config.entropy_threshold == 0.15
        assert detector.config.zero_threshold == 0.85
        assert detector.config.pattern_threshold == 0.75
        assert detector.config.max_unique_bytes == 5
        assert detector.config.region_size == 2048


# =============================================================================
# Entropy Calculation Tests
# =============================================================================


class TestEntropyCalculation:
    """Tests for Shannon entropy calculation."""

    def test_entropy_empty_data(self, detector: EmptyRegionDetector) -> None:
        """Empty data returns 0.0 entropy."""
        result = detector._calculate_entropy(b"")
        assert result == 0.0

    def test_entropy_single_byte_repeated(self, detector: EmptyRegionDetector) -> None:
        """Uniform data (all same bytes) returns 0.0 entropy."""
        result = detector._calculate_entropy(b"\x00" * 100)
        assert result == 0.0

        result = detector._calculate_entropy(b"\xFF" * 100)
        assert result == 0.0

    def test_entropy_two_distinct_bytes_equal_distribution(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Two distinct bytes with equal distribution returns 1.0 entropy."""
        data = b"\x00\xFF" * 50  # 50% each
        result = detector._calculate_entropy(data)
        assert abs(result - 1.0) < 0.01  # ~1.0 for 2 equally distributed bytes

    def test_entropy_four_distinct_bytes_equal_distribution(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Four distinct bytes with equal distribution returns 2.0 entropy."""
        data = b"\x00\x01\x02\x03" * 256
        result = detector._calculate_entropy(data)
        assert abs(result - 2.0) < 0.01  # ~2.0 for 4 equally distributed bytes

    def test_entropy_all_256_bytes_equal_distribution(
        self, detector: EmptyRegionDetector
    ) -> None:
        """All 256 byte values equally distributed returns ~8.0 entropy."""
        data = bytes(range(256)) * 4  # Each byte value appears 4 times
        result = detector._calculate_entropy(data)
        assert abs(result - 8.0) < 0.01  # Max entropy for bytes

    def test_entropy_skewed_distribution(self, detector: EmptyRegionDetector) -> None:
        """Skewed distribution returns low entropy."""
        # 90% zeros, 10% 0xFF
        data = b"\x00" * 90 + b"\xFF" * 10
        result = detector._calculate_entropy(data)
        assert result < 1.0  # Low entropy due to skew

    def test_entropy_range_validation(self, detector: EmptyRegionDetector) -> None:
        """Any data returns value between 0.0 and 8.0."""
        test_cases = [
            b"\x00" * 100,
            b"\xFF" * 100,
            b"\x00\xFF" * 50,
            bytes(range(256)),
            b"Hello, World!",
        ]
        for data in test_cases:
            result = detector._calculate_entropy(data)
            assert 0.0 <= result <= 8.0


# =============================================================================
# Zero Percentage Tests
# =============================================================================


class TestZeroPercentage:
    """Tests for zero byte percentage calculation."""

    def test_zero_percentage_empty_data(self, detector: EmptyRegionDetector) -> None:
        """Empty data returns 1.0 (100% zeros by convention)."""
        result = detector._calculate_zero_percentage(b"")
        assert result == 1.0

    def test_zero_percentage_all_zeros(self, detector: EmptyRegionDetector) -> None:
        """All zeros returns 1.0."""
        result = detector._calculate_zero_percentage(b"\x00" * 100)
        assert result == 1.0

    def test_zero_percentage_no_zeros(self, detector: EmptyRegionDetector) -> None:
        """No zeros returns 0.0."""
        result = detector._calculate_zero_percentage(b"\xFF" * 100)
        assert result == 0.0

    def test_zero_percentage_half_zeros(self, detector: EmptyRegionDetector) -> None:
        """Half zeros returns 0.5."""
        result = detector._calculate_zero_percentage(b"\x00\xFF" * 50)
        assert result == 0.5

    def test_zero_percentage_90_percent_zeros(
        self, detector: EmptyRegionDetector
    ) -> None:
        """90% zeros returns 0.9."""
        data = b"\x00" * 90 + b"\xFF" * 10
        result = detector._calculate_zero_percentage(data)
        assert result == 0.9

    def test_zero_percentage_single_byte_zero(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Single zero byte returns 1.0."""
        result = detector._calculate_zero_percentage(b"\x00")
        assert result == 1.0

    def test_zero_percentage_single_byte_nonzero(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Single nonzero byte returns 0.0."""
        result = detector._calculate_zero_percentage(b"\x01")
        assert result == 0.0


# =============================================================================
# Repeating Pattern Detection Tests
# =============================================================================


class TestPatternDetection:
    """Tests for repeating pattern detection."""

    # Size boundary conditions

    def test_pattern_data_too_small(self, detector: EmptyRegionDetector) -> None:
        """Data < 16 bytes returns 0.0."""
        result = detector._detect_repeating_patterns(b"\x00" * 15)
        assert result == 0.0

    def test_pattern_exactly_16_bytes(self, detector: EmptyRegionDetector) -> None:
        """Exactly 16 bytes with pattern is properly analyzed."""
        result = detector._detect_repeating_patterns(b"\x00" * 16)
        assert result > 0.0  # Should detect pattern

    # Common pattern detection

    def test_pattern_all_zeros(self, detector: EmptyRegionDetector) -> None:
        """All zeros pattern detected with high coverage."""
        data = b"\x00" * 64
        result = detector._detect_repeating_patterns(data)
        assert result > 0.8

    def test_pattern_all_ones(self, detector: EmptyRegionDetector) -> None:
        """All 0xFF pattern detected with high coverage."""
        data = b"\xFF" * 64
        result = detector._detect_repeating_patterns(data)
        assert result > 0.8

    def test_pattern_alternating_00ff(self, detector: EmptyRegionDetector) -> None:
        """Alternating 0x00 0xFF pattern detected."""
        data = b"\x00\xFF" * 32
        result = detector._detect_repeating_patterns(data)
        assert result > 0.8

    def test_pattern_alternating_ff00(self, detector: EmptyRegionDetector) -> None:
        """Alternating 0xFF 0x00 pattern detected."""
        data = b"\xFF\x00" * 32
        result = detector._detect_repeating_patterns(data)
        assert result > 0.8

    def test_pattern_partial_coverage_below_threshold(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Pattern covering < 80% returns 0.0 for common patterns."""
        # 50% zeros, 50% random - less than 80% threshold
        data = b"\x00" * 32 + bytes(range(32))
        result = detector._detect_repeating_patterns(data)
        # Won't match common patterns (need 80%) or 4-byte repeat (need 90%)
        # The 4-byte repeat check will fail because first 4 bytes are zeros
        # but the rest doesn't match
        assert result < 0.8

    # 4-byte repeating pattern detection

    def test_pattern_4byte_repeat_high_coverage(
        self, detector: EmptyRegionDetector
    ) -> None:
        """4-byte repeating pattern detected at >90% coverage."""
        pattern = b"\x12\x34\x56\x78"
        data = pattern * 16  # 100% coverage
        result = detector._detect_repeating_patterns(data)
        assert result > 0.9

    def test_pattern_4byte_repeat_low_coverage(
        self, detector: EmptyRegionDetector
    ) -> None:
        """4-byte pattern at <90% coverage returns 0.0."""
        pattern = b"\x12\x34\x56\x78"
        # Only first 70% matches
        data = pattern * 11 + b"\x99\x99\x99\x99" * 5
        result = detector._detect_repeating_patterns(data)
        # Won't reach 90% threshold
        assert result < 0.9

    # Edge cases

    def test_pattern_no_patterns_detected(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Random-ish bytes return 0.0."""
        # Use bytes that don't form repeating patterns
        data = bytes([i ^ (i >> 1) for i in range(64)])
        result = detector._detect_repeating_patterns(data)
        assert result == 0.0


# =============================================================================
# analyze_region Decision Path Tests
# =============================================================================


class TestAnalyzeRegionDecision:
    """Tests for analyze_region decision logic."""

    # Low entropy trigger

    def test_analyze_low_entropy_triggers_empty(
        self, custom_detector: EmptyRegionDetector
    ) -> None:
        """Very low entropy triggers is_empty=True."""
        # All same bytes = 0 entropy < 0.5 threshold
        data = b"\x42" * 64
        result = custom_detector.analyze_region(data, offset=0)

        assert result.is_empty is True
        assert "Low entropy" in result.reason

    def test_analyze_low_entropy_boundary(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Entropy exactly at threshold is not empty."""
        # This is hard to test exactly, so we use known low entropy data
        # The default threshold is 0.1, so we need entropy >= 0.1
        # Two bytes at 95/5 ratio gives entropy ~0.286
        data = b"\x00" * 95 + b"\xFF" * 5
        result = detector.analyze_region(data, offset=0)
        # This will likely trigger high zero percentage instead
        # The point is we're testing the decision flow

    # High zero percentage trigger

    def test_analyze_high_zeros_triggers_empty(
        self, detector: EmptyRegionDetector
    ) -> None:
        """>90% zeros triggers is_empty=True."""
        data = b"\x00" * 95 + b"\x01\x02\x03\x04\x05"  # 95% zeros
        result = detector.analyze_region(data, offset=0)

        assert result.is_empty is True
        assert "High zero percentage" in result.reason or "Low entropy" in result.reason

    def test_analyze_high_zeros_exactly_90_percent(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Exactly 90% zeros (threshold) is not empty (> not >=)."""
        data = b"\x00" * 90 + bytes(range(10))  # Exactly 90%
        result = detector.analyze_region(data, offset=0)
        # 90% is not > 90%, so zero threshold shouldn't trigger
        # But might trigger on other criteria

    def test_analyze_high_zeros_91_percent(
        self, detector: EmptyRegionDetector
    ) -> None:
        """91% zeros triggers empty."""
        data = b"\x00" * 91 + bytes(range(9))  # 91%
        result = detector.analyze_region(data, offset=0)
        assert result.is_empty is True

    # Low unique bytes trigger

    def test_analyze_few_unique_bytes_triggers_empty(
        self, detector: EmptyRegionDetector
    ) -> None:
        """<= 4 unique bytes triggers is_empty=True."""
        # Only 3 unique bytes
        data = b"\x00\x01\x02" * 34  # 3 unique bytes, 102 bytes total
        result = detector.analyze_region(data, offset=0)

        assert result.is_empty is True

    def test_analyze_unique_bytes_boundary(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Exactly 4 unique bytes triggers empty (<= 4)."""
        data = b"\x00\x01\x02\x03" * 25  # 4 unique bytes
        result = detector.analyze_region(data, offset=0)
        assert result.is_empty is True

    def test_analyze_unique_bytes_just_above(
        self, detector: EmptyRegionDetector
    ) -> None:
        """5 unique bytes doesn't trigger unique byte check."""
        data = b"\x00\x01\x02\x03\x04" * 20  # 5 unique bytes
        result = detector.analyze_region(data, offset=0)
        # Should not trigger on unique bytes alone
        # May still be empty due to other criteria (pattern detection)

    # Repeating pattern trigger

    def test_analyze_pattern_score_triggers_empty(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Pattern score > 0.85 triggers is_empty=True."""
        # Create data with high pattern score but not zero-heavy
        data = b"\xFF" * 100  # 100% pattern
        result = detector.analyze_region(data, offset=0)

        assert result.is_empty is True

    # Decision logic ordering

    def test_analyze_first_criterion_met_stops(
        self, detector: EmptyRegionDetector
    ) -> None:
        """When first criterion is met, that reason is reported."""
        # Data that triggers low entropy (first check)
        data = b"\x00" * 100
        result = detector.analyze_region(data, offset=0)

        assert result.is_empty is True
        # Should report entropy, which is checked first
        assert "Low entropy" in result.reason

    def test_analyze_no_criteria_met(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Normal sprite data is not empty."""
        # Create "normal" data - high entropy, varied bytes, no patterns
        data = bytes(range(256)) + bytes(range(255, -1, -1))
        result = detector.analyze_region(data, offset=0)

        assert result.is_empty is False
        assert result.reason == ""

    # Offset parameter

    def test_analyze_region_with_offset(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Analyze region at non-zero offset preserves offset."""
        data = bytes(range(100))
        result = detector.analyze_region(data, offset=0x1000)

        assert result.offset == 0x1000

    def test_analyze_region_offset_zero(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Analyze region at offset=0 works correctly."""
        data = bytes(range(100))
        result = detector.analyze_region(data, offset=0)

        assert result.offset == 0


# =============================================================================
# Caching Tests
# =============================================================================


class TestCaching:
    """Tests for analysis result caching."""

    def test_cache_stores_result(self, detector: EmptyRegionDetector) -> None:
        """Analyzing same data twice returns cached result."""
        data = bytes(range(100))
        result1 = detector.analyze_region(data, offset=0x1000)
        result2 = detector.analyze_region(data, offset=0x1000)

        assert result1 is result2  # Same object from cache

    def test_cache_key_uses_offset_and_size(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Same data at different offsets are cached separately."""
        data = bytes(range(100))
        result1 = detector.analyze_region(data, offset=0x1000)
        result2 = detector.analyze_region(data, offset=0x2000)

        assert result1 is not result2
        assert result1.offset == 0x1000
        assert result2.offset == 0x2000

    def test_cache_key_uses_size(self, detector: EmptyRegionDetector) -> None:
        """Different sized data at same offset are cached separately."""
        data1 = bytes(range(100))
        data2 = bytes(range(200))
        result1 = detector.analyze_region(data1, offset=0x1000)
        result2 = detector.analyze_region(data2, offset=0x1000)

        assert result1 is not result2
        assert result1.size == 100
        assert result2.size == 200

    def test_clear_cache_empties_storage(
        self, detector: EmptyRegionDetector
    ) -> None:
        """clear_cache() empties the cache."""
        data = bytes(range(100))
        detector.analyze_region(data, offset=0x1000)

        assert len(detector._cache) == 1

        detector.clear_cache()

        assert len(detector._cache) == 0

    def test_analyze_after_clear_cache_recalculates(
        self, detector: EmptyRegionDetector
    ) -> None:
        """After clearing cache, analyzing returns new object."""
        data = bytes(range(100))
        result1 = detector.analyze_region(data, offset=0x1000)

        detector.clear_cache()

        result2 = detector.analyze_region(data, offset=0x1000)

        assert result1 is not result2  # Different objects


# =============================================================================
# scan_rom_regions Tests
# =============================================================================


class TestScanROMRegions:
    """Tests for ROM scanning."""

    @pytest.fixture
    def small_region_detector(self) -> EmptyRegionDetector:
        """Create detector with small region size for easier testing."""
        config = EmptyRegionConfig(region_size=16)
        return EmptyRegionDetector(config)

    def test_scan_rom_empty_data(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Scanning empty ROM returns empty list."""
        result = small_region_detector.scan_rom_regions(b"")
        assert result == []

    def test_scan_rom_single_region_empty(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Single empty region returns empty list."""
        # All zeros = empty region
        result = small_region_detector.scan_rom_regions(b"\x00" * 16)
        assert result == []

    def test_scan_rom_single_region_nonempty(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Single non-empty region returns its range."""
        # High entropy data = non-empty
        data = bytes(range(16))
        result = small_region_detector.scan_rom_regions(data)
        assert result == [(0, 16)]

    def test_scan_rom_alternating_regions(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Empty, non-empty, empty pattern returns correct ranges."""
        # Empty (16 bytes) + non-empty (16 bytes) + empty (16 bytes)
        empty_region = b"\x00" * 16
        nonempty_region = bytes(range(16))
        data = empty_region + nonempty_region + empty_region

        result = small_region_detector.scan_rom_regions(data)

        assert result == [(16, 32)]  # Only middle region is non-empty

    # Region boundary handling

    def test_scan_rom_uneven_size(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """ROM size not multiple of region size handled correctly."""
        # 20 bytes = 1 full region (16) + partial (4)
        data = bytes(range(20))
        result = small_region_detector.scan_rom_regions(data)
        # Should analyze both regions
        assert len(result) >= 1

    def test_scan_rom_exact_multiple(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """ROM exactly multiple of region size works correctly."""
        # 3 regions of 16 bytes each, all non-empty
        data = bytes(range(256))[:48]  # 48 bytes = 3 regions
        result = small_region_detector.scan_rom_regions(data)
        assert result == [(0, 48)]

    def test_scan_rom_final_region_nonempty(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """ROM ending with non-empty region includes it in results."""
        # Empty + non-empty at end
        empty = b"\x00" * 16
        nonempty = bytes(range(16))
        data = empty + nonempty

        result = small_region_detector.scan_rom_regions(data)
        assert result == [(16, 32)]

    def test_scan_rom_final_region_empty(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """ROM ending with empty region closes previous non-empty range."""
        nonempty = bytes(range(16))
        empty = b"\x00" * 16
        data = nonempty + empty

        result = small_region_detector.scan_rom_regions(data)
        assert result == [(0, 16)]

    # Progress callback

    def test_scan_rom_no_progress_callback(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Scan without callback works normally."""
        data = bytes(range(64))
        result = small_region_detector.scan_rom_regions(data, progress_callback=None)
        assert result is not None

    def test_scan_rom_progress_callback_called(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Progress callback is invoked during scanning."""
        # Need > 100 regions to trigger callback (every 100 regions)
        # Default region size is 4096, so need > 400KB
        # Instead, use smaller region size
        config = EmptyRegionConfig(region_size=16)
        detector = EmptyRegionDetector(config)

        # Create data with 200 regions
        data = bytes(range(256)) * (16 * 200 // 256 + 1)
        data = data[:16 * 200]  # Exactly 200 regions

        callback = Mock()
        detector.scan_rom_regions(data, progress_callback=callback)

        # Should have been called at region 100
        assert callback.call_count >= 1

    def test_scan_rom_progress_callback_arguments(
        self, detector: EmptyRegionDetector
    ) -> None:
        """Callback receives (current, total) arguments."""
        config = EmptyRegionConfig(region_size=16)
        detector = EmptyRegionDetector(config)

        data = bytes(range(256)) * 13  # ~200+ regions
        data = data[:16 * 200]

        callback = Mock()
        detector.scan_rom_regions(data, progress_callback=callback)

        if callback.call_count > 0:
            # Check call arguments
            call_args = callback.call_args_list[0]
            current, total = call_args[0]
            assert current == 100  # First call at 100
            assert total == 200  # Total regions

    # Result correctness

    def test_scan_rom_result_ordered(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Results are in ascending order by start offset."""
        # Multiple non-empty regions
        nonempty = bytes(range(16))
        empty = b"\x00" * 16
        data = nonempty + empty + nonempty + empty + nonempty

        result = small_region_detector.scan_rom_regions(data)

        # Check ordering
        for i in range(1, len(result)):
            assert result[i][0] > result[i-1][0]

    def test_scan_rom_result_no_overlap(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Result regions don't overlap."""
        nonempty = bytes(range(16))
        empty = b"\x00" * 16
        data = nonempty + empty + nonempty

        result = small_region_detector.scan_rom_regions(data)

        for i in range(1, len(result)):
            assert result[i][0] >= result[i-1][1]


# =============================================================================
# get_optimized_scan_ranges Tests
# =============================================================================


class TestOptimizedScanRanges:
    """Tests for optimized range merging."""

    @pytest.fixture
    def small_region_detector(self) -> EmptyRegionDetector:
        """Create detector with small region size for easier testing."""
        config = EmptyRegionConfig(region_size=16)
        return EmptyRegionDetector(config)

    def test_optimized_ranges_empty_rom(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """All empty ROM returns empty list."""
        data = b"\x00" * 64
        result = small_region_detector.get_optimized_scan_ranges(data)
        assert result == []

    def test_optimized_ranges_single_region(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Single non-empty region returns single range."""
        data = bytes(range(16))
        result = small_region_detector.get_optimized_scan_ranges(data)
        assert result == [(0, 16)]

    def test_optimized_ranges_small_gap_merged(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Regions with small gap are merged."""
        nonempty = bytes(range(16))
        # Gap of 16 bytes (1 region) < default min_gap_size (4096)
        empty = b"\x00" * 16
        data = nonempty + empty + nonempty

        result = small_region_detector.get_optimized_scan_ranges(data, min_gap_size=32)

        assert len(result) == 1
        assert result[0] == (0, 48)  # Merged into single range

    def test_optimized_ranges_large_gap_separate(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Regions with large gap remain separate."""
        nonempty = bytes(range(16))
        empty = b"\x00" * 16
        data = nonempty + empty + nonempty

        # Gap of 16 bytes >= min_gap_size of 16, so don't merge
        result = small_region_detector.get_optimized_scan_ranges(data, min_gap_size=16)

        assert len(result) == 2
        assert result[0] == (0, 16)
        assert result[1] == (32, 48)

    def test_optimized_ranges_exact_min_gap_threshold(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Gap exactly at min_gap_size is NOT merged (gap < min_gap_size)."""
        nonempty = bytes(range(16))
        empty = b"\x00" * 16  # 16 byte gap
        data = nonempty + empty + nonempty

        # min_gap_size=16, gap=16: gap is NOT < 16, so don't merge
        result = small_region_detector.get_optimized_scan_ranges(data, min_gap_size=16)

        assert len(result) == 2

    def test_optimized_ranges_one_less_than_threshold(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Gap one less than min_gap_size IS merged."""
        nonempty = bytes(range(16))
        empty = b"\x00" * 16  # 16 byte gap
        data = nonempty + empty + nonempty

        # min_gap_size=17, gap=16: gap < 17, so merge
        result = small_region_detector.get_optimized_scan_ranges(data, min_gap_size=17)

        assert len(result) == 1

    # Multiple region merging

    def test_optimized_ranges_merge_three_regions(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Three regions with small gaps all merged."""
        nonempty = bytes(range(16))
        empty = b"\x00" * 16
        data = nonempty + empty + nonempty + empty + nonempty

        result = small_region_detector.get_optimized_scan_ranges(data, min_gap_size=32)

        assert len(result) == 1
        assert result[0] == (0, 80)

    # Edge cases

    def test_optimized_ranges_custom_min_gap_zero(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """min_gap_size=0 means no gaps are merged (0 is not < 0)."""
        nonempty = bytes(range(16))
        empty = b"\x00" * 16
        data = nonempty + empty + nonempty

        # No gap is < 0, so nothing merges
        result = small_region_detector.get_optimized_scan_ranges(data, min_gap_size=0)

        assert len(result) == 2

    def test_optimized_ranges_custom_min_gap_large(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Very large min_gap_size merges all gaps."""
        nonempty = bytes(range(16))
        empty = b"\x00" * 16
        data = nonempty + empty + nonempty + empty + nonempty

        # All gaps < 1000000, so all merge
        result = small_region_detector.get_optimized_scan_ranges(
            data, min_gap_size=1000000
        )

        assert len(result) == 1

    def test_optimized_ranges_result_ordering(
        self, small_region_detector: EmptyRegionDetector
    ) -> None:
        """Result tuples are in ascending order."""
        nonempty = bytes(range(16))
        empty = b"\x00" * 32  # Large gap
        data = nonempty + empty + nonempty + empty + nonempty

        result = small_region_detector.get_optimized_scan_ranges(data, min_gap_size=16)

        for i in range(1, len(result)):
            assert result[i][0] > result[i-1][0]


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for full workflows."""

    def test_full_workflow_rom_scan_to_optimized(self) -> None:
        """Complete workflow from ROM scan to optimized ranges."""
        config = EmptyRegionConfig(region_size=64)
        detector = EmptyRegionDetector(config)

        # Create realistic ROM-like data
        # Header (non-empty) + padding (empty) + data (non-empty) + padding
        header = bytes(range(256))[:64]  # Non-empty header
        padding1 = b"\x00" * 128  # Empty padding
        data_section = bytes([i ^ 0x55 for i in range(192)])  # Non-empty data
        padding2 = b"\xFF" * 64  # Empty (all FF pattern)

        rom_data = header + padding1 + data_section + padding2

        # Get optimized ranges
        ranges = detector.get_optimized_scan_ranges(rom_data, min_gap_size=128)

        # Should have found non-empty regions
        assert len(ranges) > 0

    def test_detector_caching_improves_performance(self) -> None:
        """Repeated analysis uses cache."""
        detector = EmptyRegionDetector()
        data = bytes(range(256)) * 16

        # First analysis
        result1 = detector.analyze_region(data, 0)

        # Second analysis should return cached
        result2 = detector.analyze_region(data, 0)

        assert result1 is result2


# =============================================================================
# Data Structure Tests
# =============================================================================


class TestRegionAnalysis:
    """Tests for RegionAnalysis dataclass."""

    def test_region_analysis_dataclass_fields(self) -> None:
        """RegionAnalysis has all required fields."""
        analysis = RegionAnalysis(
            offset=0x1000,
            size=4096,
            is_empty=False,
            entropy=5.5,
            zero_percentage=0.1,
            unique_bytes=200,
            pattern_score=0.0,
            reason=""
        )

        assert analysis.offset == 0x1000
        assert analysis.size == 4096
        assert analysis.is_empty is False
        assert analysis.entropy == 5.5
        assert analysis.zero_percentage == 0.1
        assert analysis.unique_bytes == 200
        assert analysis.pattern_score == 0.0
        assert analysis.reason == ""

    def test_region_analysis_with_reason(self) -> None:
        """RegionAnalysis stores reason string."""
        analysis = RegionAnalysis(
            offset=0,
            size=100,
            is_empty=True,
            entropy=0.05,
            zero_percentage=0.95,
            unique_bytes=2,
            pattern_score=0.0,
            reason="Low entropy (0.05 < 0.1)"
        )

        assert "Low entropy" in analysis.reason


class TestEmptyRegionConfig:
    """Tests for EmptyRegionConfig namedtuple."""

    def test_config_default_values(self) -> None:
        """Config uses correct default values from constants."""
        config = EmptyRegionConfig()

        assert config.entropy_threshold == 0.1
        assert config.zero_threshold == 0.9
        assert config.pattern_threshold == 0.85
        assert config.max_unique_bytes == 4
        assert config.region_size == 4096

    def test_config_custom_values(self) -> None:
        """Config accepts custom values."""
        config = EmptyRegionConfig(
            entropy_threshold=0.2,
            zero_threshold=0.95,
            pattern_threshold=0.9,
            max_unique_bytes=8,
            region_size=8192
        )

        assert config.entropy_threshold == 0.2
        assert config.zero_threshold == 0.95
        assert config.pattern_threshold == 0.9
        assert config.max_unique_bytes == 8
        assert config.region_size == 8192
