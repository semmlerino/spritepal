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

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.skip_thread_cleanup,
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
# STATE MODIFICATION TESTS - ISOLATED MANAGERS (SLOW BUT SAFE)
# ============================================================================

@pytest.mark.isolated_managers
class TestIsolatedManagerExamples:
    """Examples of tests that need fresh manager instances."""

    def test_manager_state_modification(self, isolated_managers):
        """Test that modifies manager state."""
        session_manager = isolated_managers.get_session_manager()

        # This test modifies state that could affect other tests
        # So it needs isolated managers
        session_manager.get("session", "some_setting", "default")

        # Modify state
        session_manager.set("session", "some_setting", "modified_value")

        # Verify modification
        assert session_manager.get("session", "some_setting", "default") == "modified_value"

        # This change won't affect other tests due to isolation

    def test_manager_cache_modification(self, isolated_managers):
        """Test that modifies manager caches."""
        extraction_manager = isolated_managers.get_extraction_manager()

        # Tests that modify internal caches, temporary state, etc.
        # need isolation to avoid affecting other tests
        assert extraction_manager is not None

        # Could modify extraction_manager caches here safely

    def test_error_state_recovery(self, isolated_managers):
        """Test error conditions that might leave managers in bad state."""
        injection_manager = isolated_managers.get_injection_manager()

        # Test error recovery scenarios that might affect manager state
        assert injection_manager is not None

        # Could test error recovery that leaves manager in modified state

# ============================================================================
# MIGRATION EXAMPLES
# ============================================================================

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


class TestMixedPatterns:
    """Show how different test types can coexist in same file."""

    @pytest.mark.no_manager_setup
    def test_fast_unit_check(self):
        """Fast unit test in mixed file."""
        assert 1 + 1 == 2

    def test_integration_check(self, managers):
        """Integration test in same file."""
        extraction_manager = managers.get_extraction_manager()
        assert extraction_manager is not None

    @pytest.mark.isolated_managers
    def test_isolated_check(self, isolated_managers):
        """Isolated test in same file."""
        session_manager = isolated_managers.get_session_manager()
        assert session_manager is not None
