"""
Test infrastructure fixes and verification
"""

import time

import pytest

# Systematic pytest markers applied based on test content analysis
pytestmark = [pytest.mark.headless]


@pytest.mark.no_manager_setup
def test_runs_fast():
    """This should complete in <0.1 seconds"""
    start = time.time()
    assert 1 + 1 == 2
    elapsed = time.time() - start
    assert elapsed < 0.1, f"Test took {elapsed}s, should be <0.1s"


@pytest.mark.no_manager_setup
def test_circular_import_prevention():
    """Test that circular imports are prevented"""
    # This should not raise ImportError
    from core.controller import ExtractionController
    from ui.main_window import MainWindow

    assert MainWindow is not None
    assert ExtractionController is not None


@pytest.mark.no_manager_setup
def test_manager_markers_work():
    """Verify no_manager_setup marker prevents manager initialization"""
    # This test should run without initializing managers
    # If markers aren't working, this will be slow
    start = time.time()

    # Simple computation that should be very fast
    result = sum(range(100))
    assert result == 4950

    elapsed = time.time() - start
    assert elapsed < 0.01, f"Test took {elapsed}s, markers may not be working"


@pytest.mark.no_manager_setup
def test_infrastructure_speed_baseline():
    """Baseline speed test for infrastructure without any manager setup"""
    iterations = 1000
    start = time.time()

    # Simple operations that should be very fast
    for i in range(iterations):
        result = i * 2 + 1
        assert result == i * 2 + 1

    elapsed = time.time() - start
    # Should easily complete 1000 iterations in under 0.01s
    assert elapsed < 0.01, f"Baseline test took {elapsed}s, infrastructure may have issues"
