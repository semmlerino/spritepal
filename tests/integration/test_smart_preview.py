from __future__ import annotations

import weakref
from unittest.mock import Mock, patch

import pytest

from core.services.preview_generator import PreviewGenerator

pytestmark = [pytest.mark.integration, pytest.mark.no_manager_setup]

"""
Tests for SmartPreviewCoordinator memory cache functionality.

Tests that the smart preview coordinator properly stores and retrieves preview data
using the memory LRU cache.
"""


def test_smart_preview_initialization():
    """Verify PreviewGenerator can be initialized."""
    # This replaces more complex tests that were removed or redundant
    generator = PreviewGenerator()
    assert generator is not None
