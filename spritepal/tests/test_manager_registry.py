"""
Tests for manager registry

NOTE: This file intentionally uses deprecated ManagerRegistry.get_*_manager() methods
to test that they still work correctly (raising proper errors when not initialized).
The deprecation warnings are suppressed since we're testing the deprecated API.
"""
from __future__ import annotations

import warnings

import pytest

# Suppress deprecation warnings for get_*_manager methods we're intentionally testing
warnings.filterwarnings(
    "ignore",
    message=r"ManagerRegistry\.get_\w+_manager\(\) is deprecated",
    category=DeprecationWarning,
)

from core.di_container import reset_container
from core.managers import (
    # Serial execution required: Thread safety concerns
    ManagerError,
    cleanup_managers,
    initialize_managers,
)
from core.managers.application_state_manager import ApplicationStateManager
from core.managers.core_operations_manager import CoreOperationsManager
from core.managers.registry import ManagerRegistry


def are_managers_initialized() -> bool:
    """Check if managers are initialized."""
    return ManagerRegistry().is_initialized()


def get_session_manager():
    """Get session manager from registry."""
    return ManagerRegistry().get_session_manager()


def get_extraction_manager():
    """Get extraction manager from registry."""
    return ManagerRegistry().get_extraction_manager()

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
        """Ensure clean registry state for each test.

        IMPORTANT: If session_managers fixture is active, we skip cleanup
        to avoid breaking the session fixture's DI container registrations.
        """
        from tests.fixtures.core_fixtures import is_session_managers_active

        # Skip cleanup if session_managers is active - it owns the lifecycle
        if is_session_managers_active():
            yield
            return

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
        registry3 = ManagerRegistry()

        assert registry1 is registry2
        assert registry2 is registry3

    def test_managers_not_initialized_after_cleanup(self):
        """Test managers are not initialized after cleanup.

        Note: This test requires exclusive control of the manager registry state.
        When session_managers is active, the cleanup_registry fixture skips cleanup
        to avoid breaking other tests, so this test cannot run.
        """
        from tests.fixtures.core_fixtures import is_session_managers_active

        if is_session_managers_active():
            pytest.skip("Cannot test uninitialized state while session_managers is active")

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
        from tests.fixtures.core_fixtures import is_session_managers_active

        if is_session_managers_active():
            pytest.skip("Cannot test cleanup_managers while session_managers is active")

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
        from tests.fixtures.core_fixtures import is_session_managers_active

        if is_session_managers_active():
            pytest.skip("Cannot test initial empty state while session_managers is active")

        registry = ManagerRegistry()

        # Initially empty
        assert registry.get_all_managers() == {}

        # After initialization
        initialize_managers()
        all_managers = registry.get_all_managers()

        # Keys are now protocol names (DI container is single source of truth)
        assert "ApplicationStateManagerProtocol" in all_managers
        assert "ExtractionManagerProtocol" in all_managers
        # Consolidated architecture: state returns ApplicationStateManager
        assert isinstance(all_managers["ApplicationStateManagerProtocol"], ApplicationStateManager)
        # Consolidated architecture: extraction returns CoreOperationsManager
        assert isinstance(all_managers["ExtractionManagerProtocol"], CoreOperationsManager)

    def test_double_initialization(self):
        """Test that double initialization doesn't create new instances"""
        from tests.fixtures.core_fixtures import is_session_managers_active

        if is_session_managers_active():
            pytest.skip("Cannot test double initialization while session_managers is active")

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
        from tests.fixtures.core_fixtures import is_session_managers_active

        if is_session_managers_active():
            pytest.skip("Cannot test uninitialized error while session_managers is active")

        # Ensure clean state - managers not initialized
        if are_managers_initialized():
            cleanup_managers()

        # Verify that getting a manager without initialization raises ManagerError
        with pytest.raises(ManagerError, match="not initialized"):
            get_session_manager()

    def test_concurrent_access(self):
        """Test thread-safe access to registry"""
        import threading

        from tests.fixtures.core_fixtures import is_session_managers_active

        if is_session_managers_active():
            pytest.skip("Cannot test concurrent initialization while session_managers is active")

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
