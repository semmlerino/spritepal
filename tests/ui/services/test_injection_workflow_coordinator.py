"""Comprehensive tests for InjectionWorkflowCoordinator.

Tests the injection workflow orchestration including:
- Injection start and completion
- Signal emission and handling
- Error handling and cleanup
"""

from __future__ import annotations

import pytest


class TestInjectionWorkflowCoordinatorStart:
    """Tests for injection workflow start."""

    def test_can_start_injection(self, app_context, tmp_path):
        """Test that coordinator can initiate injection."""
        from ui.services.injection_workflow_coordinator import (
            InjectionWorkflowCoordinator,
        )

        coordinator = InjectionWorkflowCoordinator(app_context)

        # Track signal emissions
        signals_emitted: list[str] = []
        coordinator.injection_started.connect(lambda: signals_emitted.append("started"))

        # Create dummy files for injection
        sprite_file = tmp_path / "sprite.png"
        sprite_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # Minimal PNG header

        input_vram = tmp_path / "input.vram"
        input_vram.write_bytes(b"\x00" * 65536)

        output_vram = tmp_path / "output.vram"

        # Create valid injection params (VRAM mode)
        params = {
            "mode": "vram",
            "sprite_path": str(sprite_file),
            "input_vram": str(input_vram),
            "output_vram": str(output_vram),
            "offset": 0x2000,
        }

        # Start injection (will fail due to invalid sprite, but should emit started signal)
        coordinator.start_injection(params)

        # Verify started signal was emitted
        assert "started" in signals_emitted

    def test_injection_validates_required_params(self, app_context, tmp_path):
        """Test that coordinator validates required parameters."""
        from ui.services.injection_workflow_coordinator import (
            InjectionWorkflowCoordinator,
        )

        coordinator = InjectionWorkflowCoordinator(app_context)

        # Track signal emissions
        signals_emitted: list[tuple[str, str]] = []
        coordinator.injection_finished.connect(lambda success, msg: signals_emitted.append(("finished", msg)))

        # Create invalid params (missing sprite_path)
        params = {
            "mode": "vram",
            "input_vram": str(tmp_path / "input.vram"),
            "output_vram": str(tmp_path / "output.vram"),
            "offset": 0x2000,
        }

        # Start injection - should fail validation
        result = coordinator.start_injection(params)

        # Should return False for validation failure
        assert result is False

    def test_injection_returns_false_on_failure(self, app_context, tmp_path):
        """Test that coordinator returns False when injection fails to start."""
        from ui.services.injection_workflow_coordinator import (
            InjectionWorkflowCoordinator,
        )

        coordinator = InjectionWorkflowCoordinator(app_context)

        # Create params with nonexistent files
        params = {
            "mode": "vram",
            "sprite_path": "/nonexistent/sprite.png",
            "input_vram": "/nonexistent/input.vram",
            "output_vram": str(tmp_path / "output.vram"),
            "offset": 0x2000,
        }

        # Start injection - should fail
        result = coordinator.start_injection(params)

        # Should return False
        assert result is False


class TestInjectionWorkflowCoordinatorSignals:
    """Tests for coordinator signal emissions."""

    def test_signals_defined(self):
        """Test that coordinator has all required signals."""
        from ui.services.injection_workflow_coordinator import (
            InjectionWorkflowCoordinator,
        )

        # Check that signals exist
        assert hasattr(InjectionWorkflowCoordinator, "injection_started")
        assert hasattr(InjectionWorkflowCoordinator, "injection_progress")
        assert hasattr(InjectionWorkflowCoordinator, "injection_finished")

    def test_progress_signal_forwarded(self, app_context, tmp_path):
        """Test that progress signal is forwarded from manager."""
        from ui.services.injection_workflow_coordinator import (
            InjectionWorkflowCoordinator,
        )

        coordinator = InjectionWorkflowCoordinator(app_context)

        # Track signal emissions
        progress_messages: list[str] = []
        coordinator.injection_progress.connect(lambda msg: progress_messages.append(msg))

        # Manually emit progress through the coordinator's handler
        coordinator._on_progress("Test progress message")

        # Verify progress was forwarded
        assert "Test progress message" in progress_messages

    def test_finished_signal_forwarded(self, app_context, tmp_path):
        """Test that finished signal is forwarded from manager."""
        from ui.services.injection_workflow_coordinator import (
            InjectionWorkflowCoordinator,
        )

        coordinator = InjectionWorkflowCoordinator(app_context)

        # Track signal emissions
        finished_results: list[tuple[bool, str]] = []
        coordinator.injection_finished.connect(lambda success, msg: finished_results.append((success, msg)))

        # Manually call the finished handler
        coordinator._on_finished(True, "Success message")

        # Verify finished was forwarded
        assert (True, "Success message") in finished_results


class TestInjectionWorkflowCoordinatorCleanup:
    """Tests for coordinator cleanup and resource management."""

    def test_coordinator_can_be_destroyed(self, app_context):
        """Test that coordinator can be properly destroyed."""
        from ui.services.injection_workflow_coordinator import (
            InjectionWorkflowCoordinator,
        )

        coordinator = InjectionWorkflowCoordinator(app_context)
        # Should not raise
        coordinator.deleteLater()

    def test_multiple_coordinators_can_coexist(self, app_context):
        """Test that multiple coordinators can be created without interference."""
        from ui.services.injection_workflow_coordinator import (
            InjectionWorkflowCoordinator,
        )

        coord1 = InjectionWorkflowCoordinator(app_context)
        coord2 = InjectionWorkflowCoordinator(app_context)

        # Both should have independent signals
        assert coord1 is not coord2
        assert coord1.injection_started is not coord2.injection_started

    def test_coordinator_provides_access_to_core_operations_manager(self, app_context):
        """Test that coordinator exposes core_operations_manager for signal connections."""
        from ui.services.injection_workflow_coordinator import (
            InjectionWorkflowCoordinator,
        )

        coordinator = InjectionWorkflowCoordinator(app_context)

        # Should expose the manager
        assert coordinator.core_operations_manager is not None
        assert coordinator.core_operations_manager is app_context.core_operations_manager

    def test_cleanup_connections_handles_fresh_coordinator(self, app_context):
        """Test that cleanup handles fresh coordinator gracefully."""
        from ui.services.injection_workflow_coordinator import (
            InjectionWorkflowCoordinator,
        )

        coordinator = InjectionWorkflowCoordinator(app_context)

        # Calling cleanup on a fresh coordinator should not raise
        # (no connections have been established yet)
        coordinator._cleanup_connections()

        # Coordinator should still be usable after cleanup
        # Verify by checking that signals are still defined
        assert coordinator.injection_started is not None
        assert coordinator.injection_progress is not None
        assert coordinator.injection_finished is not None
