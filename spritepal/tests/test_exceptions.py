"""Tests for custom exceptions - smoke tests only.

Individual exception type tests removed as they just verify Python's exception mechanism.
"""
from __future__ import annotations

import pytest

from core.exceptions import (
    ExtractionError,
    FileFormatError,
    InjectionError,
    SpritePalError,
    TileError,
    ValidationError,
)

pytestmark = [
    pytest.mark.headless,
    pytest.mark.no_manager_setup,
]


class TestExceptions:
    """Smoke tests for custom exception classes."""

    def test_sprite_pal_error_base(self):
        """Test base SpritePalError can be raised and caught."""
        with pytest.raises(SpritePalError) as exc_info:
            raise SpritePalError("Test error message")

        assert str(exc_info.value) == "Test error message"

    def test_exception_inheritance_chain(self):
        """Test that all custom exceptions inherit from SpritePalError."""
        exceptions = [
            ExtractionError("test"),
            InjectionError("test"),
            ValidationError("test"),
            FileFormatError("test"),
            TileError("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, SpritePalError)
            assert isinstance(exc, Exception)
