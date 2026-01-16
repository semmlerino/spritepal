"""Comprehensive tests for ExtractionWorkflowCoordinator.

Tests the extraction workflow orchestration including:
- VRAM extraction start and completion
- ROM extraction start and completion
- Worker lifecycle management
- Signal emission and handling
- Error handling and cleanup
"""

from __future__ import annotations

import pytest


class TestExtractionWorkflowCoordinatorVRAMExtraction:
    """Tests for VRAM extraction workflow."""

    def test_can_start_vram_extraction(self, app_context, tmp_path):
        """Test that coordinator can initiate VRAM extraction."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        coordinator = ExtractionWorkflowCoordinator(app_context)

        # Track signal emissions
        signals_emitted: list[tuple[str, str]] = []
        coordinator.extraction_started.connect(
            lambda mode: signals_emitted.append(("started", mode))
        )

        # Create dummy VRAM file
        vram_file = tmp_path / "vram.bin"
        vram_file.write_bytes(b"\x00" * 65536)

        # Create valid extraction params
        params = {
            "vram_path": str(vram_file),
            "cgram_path": None,
            "oam_path": None,
            "vram_offset": 0x2000,
            "output_base": str(tmp_path / "output"),
            "create_grayscale": True,
            "create_metadata": True,
            "grayscale_mode": False,
        }

        # Start extraction
        coordinator.start_vram_extraction(params)

        # Verify signal was emitted
        assert ("started", "VRAM") in signals_emitted

    def test_vram_extraction_validates_vram_file(self, app_context, tmp_path):
        """Test that coordinator validates VRAM file exists."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        coordinator = ExtractionWorkflowCoordinator(app_context)

        # Track signal emissions
        signals_emitted: list[tuple[str, str]] = []
        coordinator.extraction_failed.connect(
            lambda msg: signals_emitted.append(("failed", msg))
        )

        # Create invalid extraction params (VRAM file doesn't exist)
        params = {
            "vram_path": "/nonexistent/vram.bin",
            "cgram_path": None,
            "oam_path": None,
            "vram_offset": 0x2000,
            "output_base": str(tmp_path / "output"),
            "create_grayscale": True,
            "create_metadata": True,
            "grayscale_mode": False,
        }

        # Start extraction - should fail
        coordinator.start_vram_extraction(params)

        # Verify failure signal was emitted
        assert len(signals_emitted) > 0
        assert signals_emitted[0][0] == "failed"

    def test_vram_extraction_handles_cgram_validation(self, app_context, tmp_path):
        """Test that coordinator validates CGRAM file when provided."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        coordinator = ExtractionWorkflowCoordinator(app_context)

        # Track signal emissions
        signals_emitted: list[tuple[str, str]] = []
        coordinator.extraction_failed.connect(
            lambda msg: signals_emitted.append(("failed", msg))
        )

        # Create valid VRAM file
        vram_file = tmp_path / "vram.bin"
        vram_file.write_bytes(b"\x00" * 65536)

        # Create invalid extraction params (CGRAM file doesn't exist)
        params = {
            "vram_path": str(vram_file),
            "cgram_path": "/nonexistent/cgram.bin",
            "oam_path": None,
            "vram_offset": 0x2000,
            "output_base": str(tmp_path / "output"),
            "create_grayscale": False,  # Not in grayscale mode, so CGRAM should be validated
            "create_metadata": True,
            "grayscale_mode": False,
        }

        # Start extraction - should fail
        coordinator.start_vram_extraction(params)

        # Verify failure signal was emitted
        assert len(signals_emitted) > 0
        assert signals_emitted[0][0] == "failed"

    def test_vram_extraction_cleanup_on_error(self, app_context, tmp_path):
        """Test that coordinator cleans up worker on error."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        coordinator = ExtractionWorkflowCoordinator(app_context)

        # Create invalid extraction params to trigger validation error
        params = {
            "vram_path": "/nonexistent/vram.bin",
            "cgram_path": None,
            "oam_path": None,
            "vram_offset": 0x2000,
            "output_base": str(tmp_path / "output"),
            "create_grayscale": True,
            "create_metadata": True,
            "grayscale_mode": False,
        }

        # Start extraction - should fail and cleanup
        coordinator.start_vram_extraction(params)

        # Verify worker is None after cleanup
        assert coordinator._vram_worker is None


class TestExtractionWorkflowCoordinatorROMExtraction:
    """Tests for ROM extraction workflow."""

    def test_can_start_rom_extraction(self, app_context, tmp_path):
        """Test that coordinator can initiate ROM extraction."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        coordinator = ExtractionWorkflowCoordinator(app_context)

        # Track signal emissions
        signals_emitted: list[tuple[str, str]] = []
        coordinator.extraction_started.connect(
            lambda mode: signals_emitted.append(("started", mode))
        )

        # Create dummy ROM file
        rom_file = tmp_path / "game.sfc"
        rom_file.write_bytes(b"\x00" * 1000000)

        # Create valid extraction params (matches ROMExtractionParams TypedDict)
        params = {
            "rom_path": str(rom_file),
            "sprite_offset": 0x0000,
            "sprite_name": "test_sprite",
            "output_base": str(tmp_path / "output"),
            "cgram_path": None,
        }

        # Start extraction
        coordinator.start_rom_extraction(params)

        # Verify signal was emitted
        assert ("started", "ROM") in signals_emitted

    def test_rom_extraction_validates_rom_file(self, app_context, tmp_path):
        """Test that coordinator validates ROM file exists."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        coordinator = ExtractionWorkflowCoordinator(app_context)

        # Track signal emissions
        signals_emitted: list[tuple[str, str]] = []
        coordinator.extraction_failed.connect(
            lambda msg: signals_emitted.append(("failed", msg))
        )

        # Create invalid extraction params (ROM file doesn't exist)
        params = {
            "rom_path": "/nonexistent/game.sfc",
            "sprite_offset": 0x0000,
            "sprite_name": "test_sprite",
            "output_base": str(tmp_path / "output"),
            "cgram_path": None,
        }

        # Start extraction - should fail
        coordinator.start_rom_extraction(params)

        # Verify failure signal was emitted
        assert len(signals_emitted) > 0
        assert signals_emitted[0][0] == "failed"


class TestExtractionWorkflowCoordinatorSignals:
    """Tests for coordinator signal emissions."""

    def test_signals_defined(self):
        """Test that coordinator has all required signals."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        # Check that signals exist
        assert hasattr(ExtractionWorkflowCoordinator, "extraction_started")
        assert hasattr(ExtractionWorkflowCoordinator, "extraction_failed")
        assert hasattr(ExtractionWorkflowCoordinator, "progress")
        assert hasattr(ExtractionWorkflowCoordinator, "vram_extraction_finished")
        assert hasattr(ExtractionWorkflowCoordinator, "rom_extraction_finished")

    def test_extraction_failed_signal_emitted_on_validation_error(
        self, app_context, tmp_path
    ):
        """Test that extraction_failed signal is emitted on validation error."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        coordinator = ExtractionWorkflowCoordinator(app_context)

        # Track signal emissions
        failed_signals: list[str] = []
        coordinator.extraction_failed.connect(lambda msg: failed_signals.append(msg))

        # Create invalid params
        params = {
            "vram_path": "/nonexistent/vram.bin",
            "cgram_path": None,
            "oam_path": None,
            "vram_offset": 0x2000,
            "output_base": str(tmp_path / "output"),
            "create_grayscale": True,
            "create_metadata": True,
            "grayscale_mode": False,
        }

        # Start extraction - should fail
        coordinator.start_vram_extraction(params)

        # Verify signal was emitted with error message
        assert len(failed_signals) > 0
        assert isinstance(failed_signals[0], str)
        assert len(failed_signals[0]) > 0


class TestExtractionWorkflowCoordinatorCleanup:
    """Tests for coordinator cleanup and resource management."""

    def test_coordinator_can_be_destroyed(self, app_context):
        """Test that coordinator can be properly destroyed."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        coordinator = ExtractionWorkflowCoordinator(app_context)
        # Should not raise
        coordinator.deleteLater()

    def test_multiple_coordinators_can_coexist(self, app_context):
        """Test that multiple coordinators can be created without interference."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        coord1 = ExtractionWorkflowCoordinator(app_context)
        coord2 = ExtractionWorkflowCoordinator(app_context)

        # Both should have independent signals
        assert coord1 is not coord2
        assert coord1.extraction_started is not coord2.extraction_started

    def test_coordinator_provides_access_to_core_operations_manager(self, app_context):
        """Test that coordinator exposes core_operations_manager for signal connections."""
        from ui.services.extraction_workflow_coordinator import (
            ExtractionWorkflowCoordinator,
        )

        coordinator = ExtractionWorkflowCoordinator(app_context)

        # Should expose the manager
        assert coordinator.core_operations_manager is not None
        assert coordinator.core_operations_manager is app_context.core_operations_manager
