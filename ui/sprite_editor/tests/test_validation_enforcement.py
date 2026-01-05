#!/usr/bin/env python3
"""
Regression tests for PNG validation enforcement fixes (Task 4.1.C).

Tests verify that inject button is properly disabled until PNG validation
passes, and that injection workflow enforces validation status.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

    from pytestqt.qtbot import QtBot


class TestValidationEnforcement:
    """Tests for PNG validation enforcement in injection workflow."""

    def test_inject_button_disabled_on_invalid_png(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify inject button is disabled when validation fails.

        Bug: Inject button enabled even when PNG validation failed.

        Fix: InjectTab connects validation_completed signal to disable button on failure.
        """
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.sprite_editor.controllers.injection_controller import InjectionController
        from ui.sprite_editor.views.tabs.inject_tab import InjectTab

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create controller and tab
        controller = InjectionController()
        tab = InjectTab(settings_manager=settings_mgr)

        # Connect controller to tab (sets up validation signal)
        controller.set_view(tab)

        # Note: Inject button starts ENABLED by default in UI
        # It gets disabled when validation fails
        assert tab.inject_btn.isEnabled(), "Inject button starts enabled by default"

        # Emit validation_completed with failure
        controller.validation_completed.emit(False, "Invalid PNG: wrong dimensions")
        qtbot.wait(10)

        # Assert inject button is disabled
        assert not tab.inject_btn.isEnabled(), "Inject button should be disabled when validation fails"

        # Verify validation text shows error
        assert "Invalid" in tab.validation_text.text() or "wrong dimensions" in tab.validation_text.text()

    def test_inject_button_enabled_on_valid_png(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify inject button is enabled when validation passes.

        Fix: InjectTab connects validation_completed signal to enable button on success.
        """
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.sprite_editor.controllers.injection_controller import InjectionController
        from ui.sprite_editor.views.tabs.inject_tab import InjectTab

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create controller and tab
        controller = InjectionController()
        tab = InjectTab(settings_manager=settings_mgr)

        # Connect controller to tab
        controller.set_view(tab)

        # Emit validation_completed with success
        controller.validation_completed.emit(True, "✓ PNG is valid for SNES injection")
        qtbot.wait(10)

        # Assert inject button is enabled
        assert tab.inject_btn.isEnabled(), "Inject button should be enabled when validation passes"

        # Verify validation text shows success
        assert "valid" in tab.validation_text.text().lower()

    def test_inject_fails_without_validation(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify inject_sprites() fails early if PNG validation hasn't passed.

        Bug: Could call inject_sprites() before validation completed.

        Fix: InjectionController checks _png_validation_passed flag in inject_sprites().
        """
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.sprite_editor.controllers.injection_controller import InjectionController
        from ui.sprite_editor.views.tabs.inject_tab import InjectTab

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create temporary files (valid for params validation)
        png_file = tmp_path / "test.png"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        vram_file = tmp_path / "test_vram.dmp"
        vram_file.write_bytes(b"\x00" * 1024)

        # Create controller and tab
        controller = InjectionController()
        tab = InjectTab(settings_manager=settings_mgr)
        controller.set_view(tab)

        # Set file paths (but don't validate)
        tab.png_drop.set_file(str(png_file))
        tab.vram_drop.set_file(str(vram_file))

        # Force validation flag to False (simulate validation not run)
        controller._png_validation_passed = False

        # Try to inject without validation
        controller.inject_sprites()
        qtbot.wait(10)

        # Verify error was emitted
        # Check output text for error message
        output_text = tab.inject_output_text.toPlainText()
        assert "validation has not passed" in output_text.lower() or "cannot inject" in output_text.lower(), (
            "inject_sprites() should fail with error message when validation not passed"
        )

    def test_validation_resets_on_new_png(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify validation state resets when new PNG is selected.

        Bug: Old validation status persisted when selecting new PNG.

        Fix: InjectionController resets _png_validation_passed flag in set_source_image()
              and browse_png_file().
        """
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.sprite_editor.controllers.injection_controller import InjectionController
        from ui.sprite_editor.views.tabs.inject_tab import InjectTab

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create controller and tab
        controller = InjectionController()
        tab = InjectTab(settings_manager=settings_mgr)
        controller.set_view(tab)

        # Mock the validation method to control validation result
        with patch.object(controller.converter, "validate_png") as mock_validate:
            # First PNG validates successfully
            mock_validate.return_value = (True, [])

            png1 = tmp_path / "valid.png"
            png1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

            controller.set_source_image(str(png1))
            qtbot.wait(10)

            # Verify validation passed
            assert controller._png_validation_passed is True
            assert tab.inject_btn.isEnabled()

            # Second PNG validates as invalid
            mock_validate.return_value = (False, ["Wrong dimensions"])

            png2 = tmp_path / "invalid.png"
            png2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

            controller.set_source_image(str(png2))
            qtbot.wait(10)

            # Verify validation state reset and failed
            assert controller._png_validation_passed is False
            assert not tab.inject_btn.isEnabled(), "Inject button should be disabled after selecting invalid PNG"

    def test_set_png_file_disables_button_immediately(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify set_png_file() disables inject button immediately while validating.

        Fix: InjectTab.set_png_file() disables button and shows "Validating..." before
              calling controller validation.
        """
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.sprite_editor.views.tabs.inject_tab import InjectTab

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create tab
        tab = InjectTab(settings_manager=settings_mgr)

        # Create PNG file
        png_file = tmp_path / "test.png"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        # Enable button manually (simulate previous valid state)
        tab.inject_btn.setEnabled(True)

        # Call set_png_file
        tab.set_png_file(str(png_file))

        # Button should be immediately disabled
        assert not tab.inject_btn.isEnabled(), "Inject button should be disabled immediately when new PNG is selected"

        # Validation text should show "Validating..."
        assert "validating" in tab.validation_text.text().lower(), (
            "Validation text should show 'Validating...' while validation runs"
        )

    def test_validation_text_styling(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Verify validation text styling changes based on validation result.

        Valid: Green color
        Invalid: Red color
        """
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.sprite_editor.views.tabs.inject_tab import InjectTab

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create tab
        tab = InjectTab(settings_manager=settings_mgr)

        # Set validation text for valid PNG
        tab.set_validation_text("✓ PNG is valid", is_valid=True)

        # Check green color in stylesheet
        stylesheet = tab.validation_text.styleSheet()
        assert "#00ff00" in stylesheet.lower() or "green" in stylesheet.lower(), (
            "Valid validation should use green color"
        )

        # Set validation text for invalid PNG
        tab.set_validation_text("✗ PNG validation failed", is_valid=False)

        # Check red color in stylesheet
        stylesheet = tab.validation_text.styleSheet()
        assert "#ff0000" in stylesheet.lower() or "red" in stylesheet.lower(), "Invalid validation should use red color"

    def test_inject_button_state_after_validation_cycle(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Test complete validation cycle: disabled → validating → enabled/disabled.

        This tests the full workflow as a user would experience it.
        """
        from core.managers.application_state_manager import ApplicationStateManager
        from ui.sprite_editor.controllers.injection_controller import InjectionController
        from ui.sprite_editor.views.tabs.inject_tab import InjectTab

        # Create settings manager
        settings_mgr = ApplicationStateManager(app_name="TestApp", settings_path=tmp_path / "settings.json")

        # Create controller and tab
        controller = InjectionController()
        tab = InjectTab(settings_manager=settings_mgr)
        controller.set_view(tab)

        # Initial state: button enabled by default
        assert tab.inject_btn.isEnabled(), "Button starts enabled"

        # Mock validation to return success
        with patch.object(controller.converter, "validate_png") as mock_validate:
            mock_validate.return_value = (True, [])

            # Create and set PNG file
            png_file = tmp_path / "test.png"
            png_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

            # Trigger validation via controller (simulates user selecting file)
            controller.set_source_image(str(png_file))
            qtbot.wait(10)

            # After successful validation: button enabled
            assert tab.inject_btn.isEnabled(), "Button should be enabled after successful validation"
            assert controller._png_validation_passed is True

            # Now mock validation to fail for a different file
            mock_validate.return_value = (False, ["Invalid dimensions", "Wrong format"])

            png_file2 = tmp_path / "invalid.png"
            png_file2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

            controller.set_source_image(str(png_file2))
            qtbot.wait(10)

            # After failed validation: button disabled
            assert not tab.inject_btn.isEnabled(), "Button should be disabled after failed validation"
            assert controller._png_validation_passed is False
