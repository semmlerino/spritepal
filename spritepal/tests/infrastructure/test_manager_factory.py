"""
Test Manager Factory for Dependency Injection Testing

This module provides utilities for creating properly configured test manager
instances that can be used in dependency injection contexts.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from core.managers.context import ManagerContext
from core.managers.extraction_manager import ExtractionManager

# Systematic pytest markers applied based on test content analysis
pytestmark = [
    pytest.mark.dialog,
    pytest.mark.headless,
    pytest.mark.mock_dialogs,
    pytest.mark.mock_only,
    pytest.mark.no_qt,
    pytest.mark.parallel_safe,
    pytest.mark.rom_data,
    pytest.mark.unit,
    pytest.mark.ci_safe,
]

class ManagerFactory:
    """
    Factory for creating properly configured test manager instances.
    
    These managers are designed to work in test environments and provide
    realistic behavior for unit and integration tests.
    """

    @staticmethod
    def create_test_extraction_manager() -> Mock:
        """
        Create a properly configured mock extraction manager.
        
        Returns:
            Mock ExtractionManager with realistic behavior
        """
        # Create mock without spec to avoid attribute restrictions
        mock = Mock()

        # Core state methods
        mock.is_initialized.return_value = True
        mock.cleanup.return_value = None

        # Extraction methods - return list[str] to match actual implementation
        mock.extract_from_vram.return_value = [
            "test_sprite.png",
            "test_sprite.pal.json",
            "test_sprite.metadata.json"
        ]

        mock.extract_from_rom.return_value = [
            "test_sprite.png",
            "test_sprite.pal.json"
        ]

        # Preview methods
        mock.generate_preview.return_value = {
            "success": True,
            "preview_data": b"\x00" * 1024,
            "dimensions": (64, 64)
        }

        # Validation methods - use real validation logic for parameter testing
        real_manager = ExtractionManager()
        mock.validate_extraction_params = real_manager.validate_extraction_params

        return mock

    @staticmethod
    def create_test_injection_manager() -> Mock:
        """
        Create a properly configured mock injection manager.
        
        Returns:
            Mock InjectionManager with realistic behavior
        """
        # Create mock without spec to avoid attribute restrictions
        mock = Mock()

        # Core state methods
        mock.is_initialized.return_value = True
        mock.cleanup.return_value = None

        # Injection methods
        mock.inject_to_vram.return_value = {
            "success": True,
            "output_file": "test_output.dmp",
            "bytes_written": 1024
        }

        mock.inject_to_rom.return_value = {
            "success": True,
            "output_file": "test_output.sfc",
            "bytes_written": 1024,
            "compression_ratio": 0.75
        }

        # Metadata methods
        mock.load_metadata.return_value = {
            "metadata": {"extraction": {"tile_count": 10}},
            "extraction_vram_offset": "0xC000",
            "rom_extraction_info": None,
            "source_type": "vram"
        }

        # Path suggestion methods
        mock.suggest_output_vram_path.return_value = "test_output.dmp"
        mock.suggest_output_rom_path.return_value = "test_output.sfc"
        mock.find_suggested_input_vram.return_value = "test_input.dmp"

        # ROM info methods
        mock.load_rom_info.return_value = {
            "header": {"title": "TEST ROM", "rom_type": 0x20, "checksum": 0x1234},
            "sprite_locations": {"Kirby": 0x8000, "Enemy": 0x9000}
        }

        # Settings methods
        mock.load_rom_injection_defaults.return_value = {
            "input_rom": "test.sfc",
            "output_rom": "test_output.sfc",
            "rom_offset": 0x8000,
            "custom_offset": "0x8000",
            "fast_compression": False
        }

        mock.restore_saved_sprite_location.return_value = {
            "sprite_location_index": 1,
            "custom_offset": None
        }

        mock.save_rom_injection_settings.return_value = None

        # Validation methods
        mock.validate_injection_params.return_value = (True, [])

        return mock

    @staticmethod
    def create_test_session_manager() -> Mock:
        """
        Create a properly configured mock session manager.
        
        Returns:
            Mock SessionManager with realistic behavior
        """
        # Create mock without spec to avoid attribute restrictions
        mock = Mock()

        # Core state methods
        mock.is_initialized.return_value = True
        mock.cleanup.return_value = None

        # Settings methods
        mock.get_setting.return_value = None
        mock.set_setting.return_value = None
        mock.save_settings.return_value = None
        mock.load_settings.return_value = None

        # Recent files methods
        mock.get_recent_files.return_value = []
        mock.add_recent_file.return_value = None
        mock.clear_recent_files.return_value = None

        # Window state methods
        mock.save_window_state.return_value = None
        mock.restore_window_state.return_value = None

        return mock

    @staticmethod
    def create_complete_test_context(name: str = "test") -> ManagerContext:
        """
        Create a complete test context with all managers.
        
        Args:
            name: Name for the context (for debugging)
            
        Returns:
            ManagerContext with all test managers configured
        """
        managers = {
            "extraction": ManagerFactory.create_test_extraction_manager(),
            "injection": ManagerFactory.create_test_injection_manager(),
            "session": ManagerFactory.create_test_session_manager(),
        }

        return ManagerContext(managers, name=name)

    @staticmethod
    def create_minimal_test_context(
        managers: list[str | None] | None = None,
        name: str = "minimal_test"
    ) -> ManagerContext:
        """
        Create a minimal test context with only specified managers.
        
        Args:
            managers: List of manager names to include ("extraction", "injection", "session")
            name: Name for the context
            
        Returns:
            ManagerContext with only the requested managers
        """
        if managers is None:
            managers = ["injection"]  # Most common for dialog tests

        context_managers = {}

        if "extraction" in managers:
            context_managers["extraction"] = ManagerFactory.create_test_extraction_manager()

        if "injection" in managers:
            context_managers["injection"] = ManagerFactory.create_test_injection_manager()

        if "session" in managers:
            context_managers["session"] = ManagerFactory.create_test_session_manager()

        return ManagerContext(context_managers, name=name)

    @staticmethod
    def create_failing_injection_manager() -> Mock:
        """
        Create a mock injection manager that simulates failures.
        
        Useful for testing error handling paths.
        
        Returns:
            Mock InjectionManager that fails operations
        """
        # Create mock without spec to avoid attribute restrictions
        mock = Mock()

        # Core state methods
        mock.is_initialized.return_value = True
        mock.cleanup.return_value = None

        # Failing injection methods
        mock.inject_to_vram.return_value = {
            "success": False,
            "error": "Test injection failure",
            "output_file": None
        }

        mock.inject_to_rom.return_value = {
            "success": False,
            "error": "Test ROM injection failure",
            "output_file": None
        }

        # Metadata methods return None (no metadata)
        mock.load_metadata.return_value = None

        # Path methods return empty strings
        mock.suggest_output_vram_path.return_value = ""
        mock.suggest_output_rom_path.return_value = ""
        mock.find_suggested_input_vram.return_value = ""

        # ROM info fails
        mock.load_rom_info.return_value = {
            "error": "Failed to load ROM",
            "error_type": "FileNotFoundError"
        }

        # Settings methods return empty/default values
        mock.load_rom_injection_defaults.return_value = {
            "input_rom": "",
            "output_rom": "",
            "rom_offset": None,
            "custom_offset": "",
            "fast_compression": False
        }

        mock.restore_saved_sprite_location.return_value = {
            "sprite_location_index": None,
            "custom_offset": ""
        }

        # Validation fails
        mock.validate_injection_params.return_value = (False, ["Validation failed"])

        return mock

    @staticmethod
    def create_custom_injection_manager(
        inject_to_vram_result: dict[str, Any] | None = None,
        inject_to_rom_result: dict[str, Any] | None = None,
        load_metadata_result: dict[str, Any] | None = None,
        **kwargs: Any
    ) -> Mock:
        """
        Create a custom injection manager with specific behavior.
        
        Args:
            inject_to_vram_result: Custom result for inject_to_vram
            inject_to_rom_result: Custom result for inject_to_rom  
            load_metadata_result: Custom result for load_metadata
            **kwargs: Additional method results
            
        Returns:
            Mock InjectionManager with custom behavior
        """
        mock = ManagerFactory.create_test_injection_manager()

        # Override specific behaviors
        if inject_to_vram_result is not None:
            mock.inject_to_vram.return_value = inject_to_vram_result

        if inject_to_rom_result is not None:
            mock.inject_to_rom.return_value = inject_to_rom_result

        if load_metadata_result is not None:
            mock.load_metadata.return_value = load_metadata_result

        # Apply any additional overrides
        for method_name, result in kwargs.items():
            if hasattr(mock, method_name):
                getattr(mock, method_name).return_value = result

        return mock
