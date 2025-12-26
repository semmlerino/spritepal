"""Math utility functions - shared mathematical operations.

This module consolidates common mathematical operations used across the codebase.
"""

from __future__ import annotations

import math
from collections import Counter


def calculate_entropy(data: bytes) -> float:
    """Calculate Shannon entropy of byte data.

    Shannon entropy measures the randomness/information content of data.
    For byte data, returns a value between 0 (uniform, all same byte) and
    8 (maximum randomness, all bytes equally likely).

    Args:
        data: Byte data to analyze.

    Returns:
        Entropy value between 0.0 and 8.0.
    """
    if not data:
        return 0.0

    # Count byte frequencies using Counter (efficient for sparse data)
    byte_counts = Counter(data)
    data_len = len(data)

    # Calculate Shannon entropy: -sum(p * log2(p))
    entropy = 0.0
    for count in byte_counts.values():
        if count > 0:
            probability = count / data_len
            entropy -= probability * math.log2(probability)

    return entropy
