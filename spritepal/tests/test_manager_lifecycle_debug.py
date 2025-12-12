"""
Debug test to investigate manager lifecycle issues.
"""

import tempfile

import pytest

from core.di_container import inject
from core.managers import cleanup_managers, initialize_managers
from core.managers.registry import ManagerRegistry
from core.protocols.manager_protocols import ExtractionManagerProtocol


def are_managers_initialized() -> bool:
    """Check if managers are initialized."""
    return ManagerRegistry().is_initialized()

pytestmark = [
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.no_qt,
    pytest.mark.rom_data,
]
class TestManagerLifecycle:
    """Debug tests for manager lifecycle issues."""

    def test_manager_direct_usage(self):
        """Test using manager directly without workers."""
        # Clean up any existing managers
        if are_managers_initialized():
            cleanup_managers()

        # Initialize managers
        initialize_managers()

        # Get manager
        manager = inject(ExtractionManagerProtocol)
        print(f"DEBUG: Manager created: {manager}")
        print(f"DEBUG: Manager type: {type(manager)}")
        print(f"DEBUG: Manager name: {manager.get_name()}")

        # Try to access manager methods
        try:
            # This should work without throwing the Qt deletion error
            name = manager.get_name()
            print(f"DEBUG: Manager name access successful: {name}")

            # Try a simple operation that doesn't require files
            initialized = manager.is_initialized()
            print(f"DEBUG: Manager initialization check: {initialized}")

            print("DEBUG: Direct manager usage successful")

        except Exception as e:
            print(f"DEBUG: Manager access failed: {e}")
            raise

        # Clean up
        if are_managers_initialized():
            cleanup_managers()

    def test_manager_with_fake_files(self):
        """Test manager with non-existent files to see if deletion happens during validation."""
        # Clean up any existing managers
        if are_managers_initialized():
            cleanup_managers()

        # Initialize managers
        initialize_managers()

        # Get manager
        manager = inject(ExtractionManagerProtocol)
        print(f"DEBUG: Manager created for file test: {manager}")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_base = f"{temp_dir}/test_output"

            try:
                # This should fail with a validation error, not a Qt deletion error
                files = manager.extract_from_vram(
                    vram_path="/nonexistent/file.dmp",
                    output_base=output_base
                )
                print(f"DEBUG: Unexpected success: {files}")

            except Exception as e:
                print(f"DEBUG: Expected error: {type(e).__name__}: {e}")
                # Check if it's the Qt deletion error or a proper validation error
                if "wrapped C/C++ object" in str(e):
                    print("DEBUG: Qt deletion error occurred!")
                    raise
                print("DEBUG: Proper validation error occurred")

        # Clean up
        if are_managers_initialized():
            cleanup_managers()

    def test_manager_singleton_stability(self):
        """Test that manager singleton remains stable."""
        # Clean up any existing managers
        if are_managers_initialized():
            cleanup_managers()

        # Initialize managers
        initialize_managers()

        # Get manager multiple times
        manager1 = inject(ExtractionManagerProtocol)
        manager2 = inject(ExtractionManagerProtocol)
        manager3 = inject(ExtractionManagerProtocol)

        print(f"DEBUG: Manager1 id: {id(manager1)}")
        print(f"DEBUG: Manager2 id: {id(manager2)}")
        print(f"DEBUG: Manager3 id: {id(manager3)}")

        # All should be the same instance
        assert manager1 is manager2
        assert manager2 is manager3

        print("DEBUG: Singleton stability test passed")

        # Clean up
        if are_managers_initialized():
            cleanup_managers()
