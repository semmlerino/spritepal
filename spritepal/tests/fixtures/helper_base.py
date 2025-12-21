"""Base classes and mixins for test helper consolidation.

This module provides reusable mixins to eliminate duplicate code across
test helper classes, following KISS/DRY principles.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any


class SignalTrackingMixin:
    """Mixin providing signal emission tracking for test helpers.

    Classes using this mixin must initialize:
        self.signal_emissions: dict[str, list[Any]] = {...}

    Usage:
        class MyHelper(QObject, SignalTrackingMixin):
            def __init__(self):
                super().__init__()
                self.signal_emissions = {"my_signal": []}
    """

    signal_emissions: dict[str, list[Any]]

    def get_signal_emissions(self) -> dict[str, list[Any]]:
        """Get copy of signal emissions for testing."""
        return {key: value.copy() for key, value in self.signal_emissions.items()}

    def clear_signal_tracking(self) -> None:
        """Clear all signal emission tracking."""
        for key in self.signal_emissions:
            self.signal_emissions[key].clear()


class TempDirectoryMixin:
    """Mixin providing temp directory lifecycle management.

    Classes using this mixin should:
    1. Call _init_temp_dir() in __init__
    2. Call cleanup_temp_dir() in cleanup() method

    Usage:
        class MyHelper(TempDirectoryMixin):
            def __init__(self, temp_dir: str | None = None):
                self._init_temp_dir(temp_dir)

            def cleanup(self):
                self.cleanup_temp_dir()
    """

    temp_dir: str
    temp_path: Path

    def _init_temp_dir(self, temp_dir: str | None = None) -> None:
        """Initialize temp directory. Call from __init__."""
        self.temp_dir = temp_dir or tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def cleanup_temp_dir(self) -> None:
        """Clean up temp directory. Call from cleanup() method."""
        try:
            if hasattr(self, "temp_path") and self.temp_path.exists():
                shutil.rmtree(self.temp_path)
            elif hasattr(self, "temp_dir"):
                shutil.rmtree(self.temp_dir)
        except Exception:
            pass  # Best effort cleanup
