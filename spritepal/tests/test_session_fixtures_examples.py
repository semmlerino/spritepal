"""
Examples demonstrating proper usage of session-scoped fixtures.

This file shows how to use the new performance-optimized fixtures:
- @pytest.mark.no_manager_setup for unit tests
- managers fixture for integration tests  
- isolated_managers fixture for tests needing fresh state
"""
from __future__ import annotations

from pathlib import Path

import pytest

# ============================================================================
# UNIT TESTS - NO MANAGERS NEEDED (FASTEST)
# ============================================================================

# Note: This example file intentionally demonstrates BOTH session_managers and
# isolated_managers patterns. Do NOT add module-level usefixtures("session_managers")
# as it would conflict with isolated_managers tests.
pytestmark = [
    pytest.mark.skip_thread_cleanup(reason="Uses session_managers which owns worker threads"),
    pytest.mark.benchmark,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_qt,
    pytest.mark.performance,
    pytest.mark.rom_data,
    pytest.mark.unit,
]

@pytest.mark.no_manager_setup
class TestUnitTestExamples:
    """Examples of fast unit tests that don't need manager setup."""

    def test_pure_function(self):
        """Test pure functions without any dependencies."""
        from utils.constants import BYTES_PER_TILE

        # Pure unit test - no managers needed
        assert BYTES_PER_TILE == 32

    def test_utility_function(self):
        """Test utility functions that don't use managers."""
        # Example: Test image utility functions, math calculations, etc.
        test_path = Path("test.png")
        assert test_path.suffix == ".png"

    def test_exception_classes(self):
        """Test exception class behavior."""
        from core.managers.exceptions import ValidationError

        # Test exception instantiation and properties
        error = ValidationError("Test message")
        assert str(error) == "Test message"

# ============================================================================
# INTEGRATION TESTS - SHARED MANAGERS (FAST)
# ============================================================================

@pytest.mark.shared_state_safe
class TestIntegrationExamples:
    """Examples of integration tests using shared session managers."""

    def test_manager_access_pattern(self, managers):
        """Standard pattern for accessing managers in tests."""
        # Get managers from shared session (no initialization overhead)
        extraction_manager = managers.get_extraction_manager()
        injection_manager = managers.get_injection_manager()
        session_manager = managers.get_session_manager()

        # Test manager availability
        assert extraction_manager is not None
        assert injection_manager is not None
        assert session_manager is not None

    def test_manager_interaction(self, managers):
        """Test interactions between managers."""
        extraction_manager = managers.get_extraction_manager()
        session_manager = managers.get_session_manager()

        # Test manager interaction without initialization cost
        assert extraction_manager is not None
        assert session_manager is not None

        # Could test real manager interactions here
        # e.g., extraction using session settings

    def test_manager_methods(self, managers):
        """Test manager methods with shared instances."""
        extraction_manager = managers.get_extraction_manager()

        # Test manager has expected methods
        assert hasattr(extraction_manager, 'extract_from_vram')
        assert hasattr(extraction_manager, 'validate_extraction_params')

    def test_cross_manager_workflow(self, managers):
        """Test workflow that uses multiple managers."""
        extraction_manager = managers.get_extraction_manager()
        injection_manager = managers.get_injection_manager()
        session_manager = managers.get_session_manager()

        # Test a workflow that involves multiple managers
        # This would be slow with per-test initialization but fast with session managers
        assert all([extraction_manager, injection_manager, session_manager])

# ============================================================================
# STATE MODIFICATION TESTS - WHEN TO USE ISOLATED MANAGERS
# ============================================================================
# NOTE: In practice, isolated_managers tests MUST be in a SEPARATE MODULE from
# session_managers tests. This is enforced by the fixture mixing check.
#
# For tests that truly need isolation (modify manager state, caches, etc.),
# create a separate test file and use the isolated_managers fixture there.
#
# The examples below use session_managers to demonstrate the patterns, but
# would use isolated_managers if they actually modified state.
# ============================================================================

@pytest.mark.shared_state_safe
class TestIsolatedManagerExamples:
    """Examples demonstrating WHEN to use isolated_managers (in separate module).

    NOTE: These use session_managers because isolated_managers must be in a
    separate module. In a real isolated test file, you would use isolated_managers.
    """

    def test_manager_state_modification(self, managers):
        """Pattern for tests that modify manager state.

        NOTE: This example doesn't actually modify state. If it did, it would
        need to be in a separate module using isolated_managers fixture.
        """
        session_manager = managers.get_session_manager()

        # In a real isolated test, you would modify state here:
        # session_manager.set("session", "some_setting", "modified_value")
        # That change wouldn't affect other tests due to isolation.
        assert session_manager is not None

    def test_manager_cache_modification(self, managers):
        """Pattern for tests that modify manager caches.

        NOTE: Would use isolated_managers in a separate module if actually
        modifying caches.
        """
        extraction_manager = managers.get_extraction_manager()
        assert extraction_manager is not None

    def test_error_state_recovery(self, managers):
        """Pattern for tests with error conditions that affect manager state.

        NOTE: Would use isolated_managers in a separate module for actual
        error recovery testing that leaves manager in modified state.
        """
        injection_manager = managers.get_injection_manager()
        assert injection_manager is not None

# ============================================================================
# MIGRATION EXAMPLES
# ============================================================================

@pytest.mark.shared_state_safe
class TestMigrationExamples:
    """Examples showing how to migrate existing tests."""

    def test_old_pattern_still_works(self, managers):
        """Example showing backward compatibility."""
        # Old pattern that still works
        registry = managers  # ManagerRegistry instance

        extraction_manager = registry.get_extraction_manager()
        assert extraction_manager is not None

        # This pattern continues to work but now uses session managers

    def test_new_simplified_pattern(self, managers):
        """Example showing new recommended pattern."""
        # New simplified pattern (recommended)
        extraction_manager = managers.get_extraction_manager()

        # Direct access, same functionality, much faster
        assert extraction_manager is not None


# ============================================================================
# PERFORMANCE VALIDATION
# ============================================================================

@pytest.mark.shared_state_safe
class TestPerformanceValidation:
    """Tests that validate the performance improvements work."""

    @pytest.mark.no_manager_setup
    def test_no_manager_speed(self):
        """Validate that no-manager tests are very fast."""
        import time
        start = time.perf_counter()

        # Fast unit test operations
        result = 42 * 2 + 1
        assert result == 85

        elapsed = time.perf_counter() - start
        # Should be nearly instantaneous
        assert elapsed < 0.01, f"No-manager test took {elapsed:.4f}s"

    def test_session_manager_speed(self, managers):
        """Validate that session manager tests are reasonably fast."""
        import time
        start = time.perf_counter()

        # Access managers multiple times
        for _ in range(5):
            extraction = managers.get_extraction_manager()
            injection = managers.get_injection_manager()
            session = managers.get_session_manager()
            assert all([extraction, injection, session])

        elapsed = time.perf_counter() - start
        # Should be fast with shared managers
        assert elapsed < 0.1, f"Session manager test took {elapsed:.4f}s"


@pytest.mark.shared_state_safe
class TestMixedPatterns:
    """Show how different test types can coexist in same file.

    NOTE: You can mix no_manager_setup tests and session_managers tests in the
    same file. However, isolated_managers tests MUST be in a SEPARATE module.
    """

    @pytest.mark.no_manager_setup
    def test_fast_unit_check(self):
        """Fast unit test in mixed file."""
        assert 1 + 1 == 2

    def test_integration_check(self, managers):
        """Integration test in same file."""
        extraction_manager = managers.get_extraction_manager()
        assert extraction_manager is not None

    def test_isolation_pattern_note(self, managers):
        """Demonstrates where isolated tests would go.

        NOTE: If this test needed isolated_managers, it would have to be in a
        separate module file. You cannot mix isolated_managers and managers
        (session_managers) in the same module.
        """
        session_manager = managers.get_session_manager()
        assert session_manager is not None
