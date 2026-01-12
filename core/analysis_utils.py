"""
Utilities for data analysis (entropy, patterns, etc.).
"""

from __future__ import annotations

from utils.math_utils import calculate_entropy as calc_entropy_math


def calculate_entropy(data: bytes) -> float:
    """
    Calculate Shannon entropy of data.

    Returns value between 0 (uniform) and 8 (random).
    """
    return calc_entropy_math(data)


def calculate_zero_percentage(data: bytes) -> float:
    """Calculate percentage of zero bytes in data."""
    if not data:
        return 1.0

    zero_count = data.count(b"\x00")
    return zero_count / len(data)


def detect_repeating_patterns(data: bytes) -> float:
    """
    Detect repeating patterns in data.

    Returns score between 0 (no patterns) and 1 (highly repetitive).
    """
    if len(data) < 16:
        return 0.0

    # Padding patterns indicate compressible/empty regions in ROM data
    common_patterns = [
        b"\x00" * 16,
        b"\xff" * 16,
        b"\x00\xff" * 8,
        b"\xff\x00" * 8,
    ]

    for pattern in common_patterns:
        pattern_len = len(pattern)
        matches = 0

        for i in range(0, len(data) - pattern_len + 1, pattern_len):
            if data[i : i + pattern_len] == pattern:
                matches += 1

        if matches > 0:
            coverage = (matches * pattern_len) / len(data)
            if coverage > 0.8:
                return coverage

    if len(data) >= 16:
        pattern_len = 4
        first_pattern = data[:pattern_len]
        matches = 0

        for i in range(0, len(data) - pattern_len + 1, pattern_len):
            if data[i : i + pattern_len] == first_pattern:
                matches += 1

        coverage = (matches * pattern_len) / len(data)
        if coverage > 0.9:  # 90% repetition
            return coverage

    return 0.0
