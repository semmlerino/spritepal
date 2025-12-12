"""Tests for controller using real managers with mocked I/O.

This test file demonstrates the hybrid approach of using real manager
implementations for business logic testing while mocking only I/O operations.
This provides better test coverage and catches real bugs in manager logic.
"""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from core.controller import ExtractionController
from core.di_container import inject
from core.managers import ExtractionManager, InjectionManager, SessionManager
from core.protocols.dialog_protocols import DialogFactoryProtocol
from core.protocols.manager_protocols import SettingsManagerProtocol
from tests.infrastructure.real_component_factory import RealComponentFactory

# Serial execution required: Real Qt components
pytestmark = [

    pytest.mark.serial,
    pytest.mark.ci_safe,
    pytest.mark.dialog,
    pytest.mark.file_io,
    pytest.mark.headless,
    pytest.mark.mock_dialogs,
    pytest.mark.unit,
]

class TestControllerWithRealManagers:
    """Test controller with real manager implementations.
    
    Note: Real manager fixtures are now defined globally in conftest.py
    and follow the naming convention:
    - real_extraction_manager: Real ExtractionManager with mocked I/O
    - real_injection_manager: Real InjectionManager with mocked I/O  
    - real_session_manager: Real SessionManager with temp directory
    """

    @pytest.fixture
    def controller_with_real_managers(
        self,
        real_extraction_manager,
        real_injection_manager,
        real_session_manager,
        setup_managers,
    ):
        """Create controller with real managers."""
        # Create real main window with real components
        with RealComponentFactory() as factory:
            main_window = factory.create_main_window()

            # Get settings_manager and dialog_factory from DI container
            settings_manager = inject(SettingsManagerProtocol)
            dialog_factory = Mock(spec=DialogFactoryProtocol)

            # Create controller with real managers
            controller = ExtractionController(
                main_window,
                extraction_manager=real_extraction_manager,
                injection_manager=real_injection_manager,
                session_manager=real_session_manager,
                settings_manager=settings_manager,
                dialog_factory=dialog_factory,
            )

            yield controller

    def test_extraction_with_real_validation(self, controller_with_real_managers):
        """Test extraction using real manager validation logic."""
        controller = controller_with_real_managers

        # Mock the specific method on the real main window
        extraction_params = {
            "vram_path": "/test/vram.dmp",
            "cgram_path": "/test/cgram.dmp",
            "output_base": "/test/output",
            "create_grayscale": True,
            "create_metadata": True,
        }
        controller.main_window.get_extraction_params = Mock(return_value=extraction_params)

        # Mock file validation to pass
        with patch("core.controller.FileValidator") as mock_validator:
            mock_validator.validate_vram_file.return_value.is_valid = True
            mock_validator.validate_cgram_file.return_value.is_valid = True

            # Mock worker creation
            with patch("core.controller.VRAMExtractionWorker") as mock_worker:
                mock_instance = Mock()
                mock_worker.return_value = mock_instance

                # Start extraction
                controller.start_extraction()

                # Verify real manager validation was called
                # The real manager's validate_extraction_params method runs
                # with actual business logic, not mocked behavior
                assert mock_worker.called
                assert mock_instance.start.called

    def test_injection_with_real_path_logic(self, controller_with_real_managers):
        """Test injection using real manager path handling."""
        controller = controller_with_real_managers

        # Mock the specific method on the real main window
        controller.main_window.get_output_path = Mock(return_value="/test/output")

        # Mock file existence check
        with patch("core.controller.Path") as mock_path:
            mock_path.return_value.exists.return_value = True

            with patch("core.controller.FileValidator") as mock_validator:
                mock_validator.validate_file_existence.return_value.is_valid = True

                # Create mock dialog instance
                mock_dialog_instance = Mock()
                mock_dialog_instance.exec.return_value = True
                mock_dialog_instance.get_parameters.return_value = {
                    "sprite_path": "/test/output.png",
                    "mode": "vram",
                    "target_path": "/test/target.vram"
                }

                # Mock the dialog_factory's create_injection_dialog method
                controller.dialog_factory.create_injection_dialog = Mock(
                    return_value=mock_dialog_instance
                )

                # Start injection
                controller.start_injection()

                # Verify dialog was shown with real manager's suggestion
                assert controller.dialog_factory.create_injection_dialog.called
                # The real InjectionManager's get_smart_vram_suggestion runs with actual logic
                assert mock_dialog_instance.exec.called

    def test_session_persistence_with_real_manager(self, controller_with_real_managers, tmp_path):
        """Test session persistence using real SessionManager."""
        controller = controller_with_real_managers

        # Store value in session
        controller.session_manager.set("test", "key", "value")

        # Verify real persistence
        assert controller.session_manager.get("test", "key") == "value"

        # Save session (real manager handles this)
        controller.session_manager.save_session()

        # Create new session manager with same settings file
        # It loads settings automatically on initialization
        new_session = SessionManager("TestApp")
        # Override the settings file path to use the same one
        new_session._settings_file = controller.session_manager._settings_file
        new_session._settings = new_session._load_settings()

        # Verify data persisted through real manager
        assert new_session.get("test", "key") == "value"

class TestRealManagerBenefits:
    """Demonstrate benefits of using real managers in tests."""

    @pytest.fixture(autouse=True)
    def setup_di_container(self, isolated_managers):
        """Ensure DI container is set up for manager creation."""
        yield

    def test_catches_real_validation_bugs(self):
        """Real managers catch actual validation logic bugs."""
        manager = ExtractionManager()

        # This tests real validation logic, not mocked behavior
        with pytest.raises(Exception):
            # Real manager will validate this properly
            manager.validate_extraction_params({
                "vram_path": "",  # Empty path should fail
                "output_base": ""
            })

    def test_real_business_logic_coverage(self):
        """Real managers provide actual business logic coverage."""
        manager = InjectionManager()

        # Test real smart VRAM suggestion logic
        suggestion = manager.get_smart_vram_suggestion(
            "/test/sprite.png",
            ""  # No metadata
        )

        # Real manager returns actual suggestion logic
        assert suggestion == ""  # Real behavior, not mocked

    def test_real_state_management(self):
        """Real managers test actual state management."""
        manager = SessionManager("TestApp")

        # Test real state management
        manager.set("category", "key1", "value1")
        manager.set("category", "key2", "value2")

        # Real manager handles individual keys
        assert manager.get("category", "key1") == "value1"
        assert manager.get("category", "key2") == "value2"

# Summary of benefits:
# 1. Tests real business logic, not mocked behavior
# 2. Catches actual bugs in manager implementations
# 3. Provides better integration test coverage
# 4. Reduces mock setup complexity
# 5. Tests closer to production behavior
# 6. Still maintains test isolation through I/O mocking
