"""
Tests for manager registry
"""
from __future__ import annotations

import pytest

from core.managers import (
    # Serial execution required: Thread safety concerns
    ExtractionManager,
    ManagerError,
    SessionManager,
    are_managers_initialized,
    cleanup_managers,
    get_extraction_manager,
    get_registry,
    get_session_manager,
    initialize_managers,
)
from core.managers.registry import ManagerRegistry

pytestmark = [

    pytest.mark.serial,
    pytest.mark.thread_safety,
    pytest.mark.ci_safe,
    pytest.mark.headless,
]
class TestManagerRegistry:
    """Test ManagerRegistry functionality"""

    @pytest.fixture(autouse=True)
    def cleanup_registry(self):
        """Ensure clean registry state for each test"""
        # Clean up before test
        if are_managers_initialized():
            cleanup_managers()

        yield

        # Clean up after test
        if are_managers_initialized():
            cleanup_managers()

    def test_singleton_pattern(self):
        """Test that registry is a singleton"""
        registry1 = ManagerRegistry()
        registry2 = ManagerRegistry()
        registry3 = get_registry()

        assert registry1 is registry2
        assert registry2 is registry3

    def test_managers_not_initialized_by_default(self):
        """Test managers are not initialized by default"""
        assert not are_managers_initialized()

        with pytest.raises(ManagerError, match="Session manager not initialized"):
            get_session_manager()

        with pytest.raises(ManagerError, match="Extraction manager not initialized"):
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
        """Test that registry verifies manager types"""
        registry = get_registry()

        # Manually add wrong type (for testing)
        registry._managers["session"] = "not_a_manager"

        with pytest.raises(ManagerError, match="Manager type mismatch"):
            registry.get_session_manager()

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
