"""
Lightweight state entry class for state management.

This module provides reusable building blocks for state management:
- StateEntry: Wrapper for values with metadata (TTL, access tracking)
"""
from __future__ import annotations

import pickle
import sys
import time
from typing import Any


class StateEntry:
    """
    Wrapper for stored state values with metadata.

    Tracks creation time, access patterns, and optional TTL for automatic expiry.
    """

    def __init__(self, value: Any, ttl_seconds: float | None = None) -> None:  # pyright: ignore[reportExplicitAny] - Generic state value
        """
        Initialize a state entry.

        Args:
            value: The value to store
            ttl_seconds: Optional time-to-live in seconds
        """
        self.value = value
        self.created_at = time.time()
        self.accessed_at = time.time()
        self.ttl_seconds = ttl_seconds
        self.access_count = 0

        # Track size for memory management
        try:
            # Use pickle to get accurate size for complex objects
            self.size_bytes = len(pickle.dumps(value))
        except (TypeError, pickle.PicklingError):
            # Fall back to sys.getsizeof for unpickleable objects
            self.size_bytes = sys.getsizeof(value)

    def is_expired(self) -> bool:
        """
        Check if this entry has expired based on TTL.

        Returns:
            True if expired, False otherwise
        """
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    def touch(self) -> None:
        """Update access time and increment counter."""
        self.accessed_at = time.time()
        self.access_count += 1
