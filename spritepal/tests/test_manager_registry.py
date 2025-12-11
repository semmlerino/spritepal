"""
Tests for manager registry
"""
from __future__ import annotations

import pytest

from core.di_container import reset_container
from core.managers import (
    # Serial execution required: Thread safety concerns
    ExtractionManager,
    ManagerError,
    SessionManager,
    are_managers_initialized,
    cleanup_managers,
    get_registry,
    initialize_managers,
)
from core.managers.registry import ManagerRegistry


def get_session_manager():
    """Get session manager from registry (replaces deprecated function)."""
    return get_registry().get_session_manager()


def get_extraction_manager():
    """Get extraction manager from registry (replaces deprecated function)."""
    return get_registry().get_extraction_manager()

pytestmark = [
    pytest.mark.serial,
    pytest.mark.thread_safety,
    pytest.mark.ci_safe,
    pytest.mark.headless,
    pytest.mark.allows_registry_state,  # This file explicitly manages registry state
]
class TestManagerRegistry:
    """Test ManagerRegistry functionality"""

    @pytest.fixture(autouse=True)
    def cleanup_registry(self):
        """Ensure clean registry state for each test"""
        # Clean up before test - both manager registry and DI container
        if are_managers_initialized():
            cleanup_managers()
        reset_container()  # Clear DI container singletons

        yield

        # Clean up after test
        if are_managers_initialized():
            cleanup_managers()
        reset_container()  # Clear DI container singletons

    def test_singleton_pattern(self):
        """Test that registry is a singleton"""
        registry1 = ManagerRegistry()
        registry2 = ManagerRegistry()
        registry3 = get_registry()

        assert registry1 is registry2
        assert registry2 is registry3

    def test_managers_not_initialized_after_cleanup(self):
        """Test managers are not initialized after cleanup.

        Note: In a full test suite run with session_managers, managers may be
        pre-initialized. The cleanup_registry fixture ensures clean state before
        this test runs, so we verify the post-cleanup behavior.
        """
        # The cleanup_registry fixture should have cleaned up before this test
        # Verify we're in an uninitialized state
        assert not are_managers_initialized(), (
            "Managers should be uninitialized after cleanup_registry fixture runs"
        )

        with pytest.raises(ManagerError, match="SessionManager not initialized"):
            get_session_manager()

        with pytest.raises(ManagerError, match="ExtractionManager not initialized"):
            get_extraction_manager()

    def test_cleanup_managers(self):
        """Test cleaning up managers"""
        # Initialize first
        initialize_managers()
        assert are_managers_initialized()

        # Cleanup
        cleanup_managers()
        assert not are_managers_initialized()

        # Should not be able to get managers after cleanup
        with pytest.raises(ManagerError):
            get_session_manager()

    def test_get_all_managers(self):
        """Test getting all managers"""
        registry = get_registry()

        # Initially empty
        assert registry.get_all_managers() == {}

        # After initialization
        initialize_managers()
        all_managers = registry.get_all_managers()

        assert "session" in all_managers
        assert "extraction" in all_managers
        assert isinstance(all_managers["session"], SessionManager)
        assert isinstance(all_managers["extraction"], ExtractionManager)

    def test_double_initialization(self):
        """Test that double initialization doesn't create new instances"""
        # First initialization
        initialize_managers()
        session_mgr1 = get_session_manager()
        extraction_mgr1 = get_extraction_manager()

        # Second initialization
        initialize_managers()
        session_mgr2 = get_session_manager()
        extraction_mgr2 = get_extraction_manager()

        # Should be the same instances
        assert session_mgr1 is session_mgr2
        assert extraction_mgr1 is extraction_mgr2

    def test_manager_type_checking(self):
        """Test that registry raises appropriate error when managers not initialized"""
        # Ensure clean state - managers not initialized
        if are_managers_initialized():
            cleanup_managers()

        # Verify that getting a manager without initialization raises ManagerError
        with pytest.raises(ManagerError, match="not initialized"):
            get_session_manager()

    def test_concurrent_access(self):
        """Test thread-safe access to registry"""
        import threading

        # Ensure clean state before test
        if are_managers_initialized():
            cleanup_managers()

        results = []
        errors = []
        barrier = threading.Barrier(10)  # Synchronize thread start
        results_lock = threading.Lock()  # Protect shared lists

        def access_registry():
            try:
                # Wait for all threads to be ready
                barrier.wait()

                # Try to initialize
                initialize_managers()

                # Get managers
                session = get_session_manager()
                extraction = get_extraction_manager()

                # Store results with lock
                with results_lock:
                    results.append((session, extraction))
            except Exception as e:
                with results_lock:
                    errors.append(e)

        # Create multiple threads
        threads = []
        for _ in range(10):
            t = threading.Thread(target=access_registry)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # All threads should get the same manager instances
        if results:
            first_session, first_extraction = results[0]
            for i, (session, extraction) in enumerate(results[1:], 1):
                assert session is first_session, f"Result {i} session differs"
                assert extraction is first_extraction, f"Result {i} extraction differs"
