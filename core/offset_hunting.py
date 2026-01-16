"""Offset hunting utilities for HAL decompression.

When sprites are captured via Lua DMA interception, slight timing variations
can cause the captured offset to be off by a few bytes. This module provides
utilities to try nearby offsets to find valid HAL compression headers.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# Default delta values to try when offset hunting
# Positive deltas first (likely to be off by a few bytes forward),
# then negative (less common but possible)
DEFAULT_DELTAS = [2, 4, 6, 8, -2, -4, -6, -8, 10, 12, 14, 16, -10, -12, -14, -16]


def get_offset_candidates(
    base_offset: int,
    rom_size: int | None = None,
    max_delta: int = 16,
) -> list[int]:
    """Generate offset candidates for HAL decompression hunting.

    Returns the base offset first, followed by nearby offsets within
    the specified range. The order alternates between positive and
    negative deltas to try more likely adjustments first.

    Args:
        base_offset: Starting offset to try
        rom_size: ROM size for bounds checking (None to skip bounds check)
        max_delta: Maximum delta from base offset (default 16 bytes)

    Returns:
        List of offsets to try, starting with base_offset
    """
    candidates = [base_offset]

    for delta in DEFAULT_DELTAS:
        if abs(delta) > max_delta:
            continue
        adjusted = base_offset + delta
        if adjusted < 0:
            continue
        if rom_size is not None and adjusted >= rom_size:
            continue
        candidates.append(adjusted)

    return candidates


def has_nonzero_content(data: bytes | memoryview, threshold: float = 0.1) -> bool:
    """Check if data has meaningful non-zero content.

    Used to validate decompressed sprite data isn't just empty/black tiles.

    Args:
        data: Byte data to check
        threshold: Minimum fraction of non-zero bytes (default 10%)

    Returns:
        True if data has sufficient non-zero content
    """
    if not data:
        return False

    sample_size = min(100, len(data))
    non_zero_count = sum(1 for b in data[:sample_size] if b != 0)

    return non_zero_count >= sample_size * threshold
