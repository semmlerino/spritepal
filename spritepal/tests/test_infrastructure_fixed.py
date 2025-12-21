"""
Test infrastructure fixes and verification
"""

import pytest

pytestmark = [pytest.mark.headless]


@pytest.mark.no_manager_setup
def test_circular_import_prevention():
    """Test that circular imports are prevented"""
    # This should not raise ImportError
    from core.controller import ExtractionController
    from ui.main_window import MainWindow

    assert MainWindow is not None
    assert ExtractionController is not None
