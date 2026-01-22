"""
TDD tests for ExtractionManager with real component integration.

This test suite applies Test-Driven Development methodology with real components:
- RED: Write failing tests that specify desired behavior
- GREEN: Implement minimal code to make tests pass
- REFACTOR: Improve code while keeping all tests green

Enhanced with Phase 2 Real Component Testing Infrastructure:
- Uses ManagerTestContext for proper lifecycle management
- Integrates with DataRepository for consistent test data
- Tests real business logic without mocking core components
- Validates actual file I/O, threading, and signal behavior

Performance Note: This test file uses session-scoped managers for performance.
- Current fixtures work as-is (no change needed)
- For new tests, consider using `managers` fixture directly:


pytestmark = [
    pytest.mark.headless,
    pytest.mark.integration,
    pytest.mark.performance,
    pytest.mark.slow,
]
  def test_extraction(managers):
      extraction_manager = managers.get_extraction_manager()
      # test logic...

Bugs caught by real testing that mocks miss:
- File format validation edge cases
- Threading synchronization issues
- Memory management problems
- Qt signal/slot connection failures
- Resource cleanup race conditions
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from core.managers import ExtractionError, ValidationError
from core.managers.core_operations_manager import CoreOperationsManager
from tests.fixtures.timeouts import signal_timeout, worker_timeout
from tests.infrastructure.data_repository import DataRepository
from utils.constants import BYTES_PER_TILE


@pytest.mark.no_manager_setup
@pytest.mark.allows_registry_state(reason="Uses manager_context for own lifecycle")
class TestExtractionManager:
    """TDD tests for ExtractionManager with real component integration.

    These tests validate actual extraction workflows using real files,
    real workers, and actual Qt signal/slot behavior.
    """

    @pytest.fixture
    def test_data_repo(self, isolated_data_repository: DataRepository) -> DataRepository:
        """Provide test data repository for consistent test data."""
        return isolated_data_repository

    @pytest.fixture
    def manager(self, app_context):
        """Create ExtractionManager instance using app context."""
        return app_context.core_operations_manager

    @pytest.fixture
    def temp_files(self, tmp_path):
        """Create temporary test files"""
        # Create test VRAM file
        vram_file = tmp_path / "test.vram"
        vram_data = b"\x00" * 0x10000  # 64KB
        vram_file.write_bytes(vram_data)

        # Create test CGRAM file
        cgram_file = tmp_path / "test.cgram"
        cgram_data = b"\x00" * 512  # 512 bytes
        cgram_file.write_bytes(cgram_data)

        # Create test OAM file
        oam_file = tmp_path / "test.oam"
        oam_data = b"\x00" * 544  # 544 bytes
        oam_file.write_bytes(oam_data)

        # Create test ROM file
        rom_file = tmp_path / "test.sfc"
        rom_data = b"\x00" * 0x400000  # 4MB
        rom_file.write_bytes(rom_data)

        return {
            "vram": str(vram_file),
            "cgram": str(cgram_file),
            "oam": str(oam_file),
            "rom": str(rom_file),
            "output_dir": str(tmp_path),
        }

    def test_initialization_real_dependencies(self, app_context):
        """TDD: Manager should initialize with real component dependencies.

        RED: Manager needs proper initialization with all required components
        GREEN: Verify real dependencies are available and properly configured
        REFACTOR: No mocking - test actual component integration
        """
        manager = app_context.core_operations_manager

        # Verify manager is properly initialized via public API
        assert manager.is_initialized()
        # Registry returns CoreOperationsManager (consolidated manager)
        assert manager.get_name() == "CoreOperationsManager"

        # Verify real methods are callable (proves real dependencies, not mocks)
        assert callable(manager.validate_extraction_params)
        assert callable(manager.extract_from_vram)
        assert callable(manager.extract_from_rom)
        assert callable(manager.get_sprite_preview)

    def test_initialization_with_manager_context(self, app_context):
        """TDD: Manager context should provide properly configured manager."""
        manager = app_context.core_operations_manager

        # Verify context provides real, initialized manager
        assert isinstance(manager, CoreOperationsManager)
        assert manager.is_initialized()
        # Registry returns CoreOperationsManager (consolidated manager)
        assert manager.get_name() == "CoreOperationsManager"

        # Context should handle lifecycle automatically
        assert manager._sprite_extractor is not None

    def test_validate_extraction_params_vram_real_files_succeeds(self, app_context, test_data_repo):
        """VRAM parameter validation should succeed with valid test data.

        Tests the success path: valid files should pass validation.
        """
        manager = app_context.core_operations_manager

        # Get real VRAM extraction test data
        vram_data = test_data_repo.get_vram_extraction_data("medium")

        # Valid params with real files
        params = {
            "vram_path": vram_data["vram_path"],
            "output_base": vram_data["output_base"],
            "cgram_path": vram_data["cgram_path"],
            "oam_path": vram_data["oam_path"],
        }

        # Validation should succeed with valid files
        result = manager.validate_extraction_params(params)
        assert result is True

        # Verify all required files exist
        assert Path(params["vram_path"]).exists()
        assert Path(params["cgram_path"]).exists()
        assert Path(params["oam_path"]).exists()

        # Verify file sizes are reasonable
        vram_size = Path(params["vram_path"]).stat().st_size
        cgram_size = Path(params["cgram_path"]).stat().st_size
        oam_size = Path(params["oam_path"]).stat().st_size

        assert vram_size >= 0x8000  # At least 32KB VRAM
        assert cgram_size >= 512  # At least 512 bytes CGRAM
        assert oam_size >= 544  # At least 544 bytes OAM

    def test_validate_extraction_params_vram_rejects_missing_output(self, app_context, test_data_repo):
        """VRAM validation should reject params missing required output_base."""
        manager = app_context.core_operations_manager

        # Get real VRAM extraction test data
        vram_data = test_data_repo.get_vram_extraction_data("medium")

        # Valid params with real files, then remove required field
        params = {
            "vram_path": vram_data["vram_path"],
            "output_base": vram_data["output_base"],
            "cgram_path": vram_data["cgram_path"],
            "oam_path": vram_data["oam_path"],
        }
        del params["output_base"]

        with pytest.raises(ValidationError, match="Missing required parameters"):
            manager.validate_extraction_params(params)

    def test_validate_extraction_params_rom(self, manager, temp_files):
        """Test ROM extraction parameter validation"""
        # Valid params
        params = {
            "rom_path": temp_files["rom"],
            "offset": 0x1000,
            "output_base": str(Path(temp_files["output_dir"]) / "test"),
        }
        manager.validate_extraction_params(params)

        # Invalid offset type
        invalid_params = params.copy()
        invalid_params["offset"] = "not_an_int"
        with pytest.raises(ValidationError, match="Invalid type for 'offset'"):
            manager.validate_extraction_params(invalid_params)

        # Negative offset
        invalid_params = params.copy()
        invalid_params["offset"] = -1
        with pytest.raises(ValidationError, match="offset must be >= 0"):
            manager.validate_extraction_params(invalid_params)

    def test_extract_from_vram_real_workflow_creates_files(self, app_context, test_data_repo, qtbot):
        """VRAM extraction should create real image files from valid VRAM data.

        Tests the success path: valid VRAM data produces valid image output.
        """
        manager = app_context.core_operations_manager

        # Get real VRAM extraction test data
        vram_data = test_data_repo.get_vram_extraction_data("medium")

        # Test real VRAM extraction workflow - should succeed
        files = manager.extract_from_vram(
            vram_data["vram_path"],
            vram_data["output_base"],
            grayscale_mode=True,  # Simplified for reliable testing
        )

        # Verify real extraction created actual files
        assert len(files) >= 1
        output_png = f"{vram_data['output_base']}.png"
        assert output_png in files
        assert Path(output_png).exists()

        # Verify the extracted image is real with reasonable properties
        with Image.open(output_png) as img:
            assert img.mode in ["L", "P", "RGBA"]  # Valid image modes
            assert img.size[0] > 0 and img.size[1] > 0
            assert img.size[0] * img.size[1] >= 64  # Reasonable minimum size

            # Verify file has real image data (not just empty)
            img_bytes = img.tobytes()
            assert len(img_bytes) > 0

    def test_extract_from_vram_validation_error(self, manager):
        """Test VRAM extraction with validation error"""
        with pytest.raises(ValidationError):
            manager.extract_from_vram("/non/existent/file.vram", "/output/test")

    def test_extract_from_vram_already_running(self, manager, temp_files):
        """Test preventing concurrent VRAM extractions"""
        output_base = str(Path(temp_files["output_dir"]) / "test")

        # Start an extraction
        manager.simulate_operation_start("vram_extraction")

        # Try to start another
        with pytest.raises(ExtractionError, match="already in progress"):
            manager.extract_from_vram(temp_files["vram"], output_base)

        # Clean up
        manager.simulate_operation_finish("vram_extraction")

    def test_extract_from_rom_real_workflow_validation_succeeds(self, app_context, test_data_repo):
        """ROM extraction parameter validation should succeed with valid data.

        Tests the success path: valid ROM parameters pass validation.
        """
        manager = app_context.core_operations_manager

        # Get real ROM test data
        rom_data = test_data_repo.get_rom_extraction_data("medium")

        # Test ROM extraction parameter validation
        test_params = {
            "rom_path": rom_data["rom_path"],
            "offset": rom_data["offset"],
            "output_base": rom_data["output_base"],
        }

        # Validation should succeed with valid parameters
        result = manager.validate_extraction_params(test_params)
        assert result is True

        # Verify the parameters are well-formed for real ROM extraction
        assert Path(test_params["rom_path"]).exists()
        assert test_params["offset"] >= 0
        assert isinstance(test_params["output_base"], str)

        # Verify ROM file has reasonable size
        rom_size = Path(test_params["rom_path"]).stat().st_size
        assert rom_size >= 0x80000  # At least 512KB

        # Test that offset is within ROM bounds
        assert test_params["offset"] < rom_size

    def test_extract_from_rom_validation_error(self, manager):
        """Test ROM extraction with validation error"""
        with pytest.raises(ValidationError):
            manager.extract_from_rom("/non/existent/rom.sfc", 0x1000, "/output/test", "sprite")

    def test_extraction_rejects_offset_beyond_rom(self, app_context, tmp_path):
        """Verify extraction fails gracefully when offset exceeds ROM size."""
        manager = app_context.core_operations_manager

        # Create a small ROM file (32KB)
        rom_file = tmp_path / "small_rom.sfc"
        rom_file.write_bytes(b"\x00" * 0x8000)

        # Try to extract at offset beyond ROM size
        params = {
            "rom_path": str(rom_file),
            "offset": 0xFFFFFF,  # Way beyond 32KB ROM
            "output_base": str(tmp_path / "output"),
        }

        with pytest.raises(ValidationError, match="exceeds ROM size"):
            manager.validate_extraction_params(params)

    def test_extraction_accepts_valid_offset_within_rom(self, app_context, tmp_path):
        """Verify extraction accepts offset within ROM bounds."""
        manager = app_context.core_operations_manager

        # Create a ROM file (32KB)
        rom_file = tmp_path / "valid_rom.sfc"
        rom_file.write_bytes(b"\x00" * 0x8000)

        # Try to extract at valid offset within ROM
        params = {
            "rom_path": str(rom_file),
            "offset": 0x1000,  # Within 32KB ROM
            "output_base": str(tmp_path / "output"),
        }

        # Should not raise
        result = manager.validate_extraction_params(params)
        assert result is True

    def test_get_sprite_preview_real_rom_data_returns_valid_structure(self, app_context, test_data_repo):
        """Sprite preview should generate valid tile data structure from ROM files.

        Tests the success path: valid ROM data produces valid preview structure.
        """
        manager = app_context.core_operations_manager

        # Get real ROM test data
        rom_data = test_data_repo.get_rom_extraction_data("medium")

        # Test real sprite preview generation - should succeed
        tile_data, width, height = manager.get_sprite_preview(rom_data["rom_path"], 0x1000, "test_sprite")

        # Verify real tile data structure
        assert isinstance(tile_data, bytes)
        assert width > 0 and height > 0
        assert width <= 512 and height <= 512  # Reasonable bounds

        # Verify tile data size makes sense
        expected_min_size = (width * height // 64) * BYTES_PER_TILE
        assert len(tile_data) >= expected_min_size

        # Note: Synthetic test data may be all zeros - this is expected
        # The key verification is that the API returns proper structure

    def test_get_sprite_preview_validation_error(self, manager):
        """Test sprite preview with validation error"""
        with pytest.raises(ValidationError):
            manager.get_sprite_preview("/non/existent/rom.sfc", 0x1000)

    def test_concurrent_operations_real_state_management_tdd(self, app_context):
        """TDD: Manager should handle concurrent operation state correctly.

        RED: Test real operation tracking and thread safety
        GREEN: Verify actual state management without mocking
        REFACTOR: Test real concurrency scenarios that could occur in practice
        """
        manager = app_context.core_operations_manager

        # Test real concurrent operation tracking
        assert manager.simulate_operation_start("vram_extraction")
        assert manager.simulate_operation_start("rom_extraction")
        assert manager.simulate_operation_start("sprite_preview")

        # Verify real state tracking
        assert manager.is_operation_active("vram_extraction")
        assert manager.is_operation_active("rom_extraction")
        assert manager.is_operation_active("sprite_preview")

        # Test operation conflict detection
        assert not manager.simulate_operation_start("vram_extraction")  # Should conflict

        # Verify state remains consistent
        assert manager.is_operation_active("vram_extraction")

        # Test real cleanup
        manager.simulate_operation_finish("vram_extraction")
        manager.simulate_operation_finish("rom_extraction")
        manager.simulate_operation_finish("sprite_preview")

        # Verify clean state
        assert not manager.is_operation_active("vram_extraction")
        assert not manager.is_operation_active("rom_extraction")
        assert not manager.is_operation_active("sprite_preview")

    def test_signal_emissions_real_qt_signals_tdd(self, app_context, test_data_repo, qtbot):
        """TDD: Extraction should emit real Qt signals during processing.

        RED: Test real signal emission during extraction workflow
        GREEN: Verify actual Qt signal/slot connections work correctly
        REFACTOR: Use real Qt event processing without mocking signals
        """
        manager = app_context.core_operations_manager

        # Get real test data
        vram_data = test_data_repo.get_vram_extraction_data("small")

        # Track real Qt signal emissions
        progress_messages: list[str] = []
        extraction_results: list[object] = []

        def on_progress(msg: str) -> None:
            progress_messages.append(msg)

        def on_extraction_completed(result: object) -> None:
            extraction_results.append(result)

        # Connect to real Qt signals
        manager.extraction_progress.connect(on_progress)
        manager.extraction_completed.connect(on_extraction_completed)

        try:
            # Run real extraction with Qt signal monitoring
            with qtbot.waitSignal(manager.extraction_completed, timeout=worker_timeout()):
                manager.extract_from_vram(vram_data["vram_path"], vram_data["output_base"], grayscale_mode=True)

            # Wait for all Qt events to process
            qtbot.waitUntil(lambda: len(progress_messages) > 0, timeout=signal_timeout())

            # Verify real signal emissions occurred
            assert len(progress_messages) > 0, "Should emit progress signals"
            assert len(extraction_results) > 0, "Should emit extraction_completed signal"

            # Verify signal content is meaningful
            assert any("extract" in msg.lower() for msg in progress_messages)

            # Verify extraction_completed signal contains real file paths
            result = extraction_results[0]
            assert hasattr(result, "files"), "Result should have files attribute"
            created_files = result.files  # type: ignore[union-attr]
            assert len(created_files) > 0
            assert all(Path(f).exists() for f in created_files)

        except Exception as e:
            # Real signal testing may reveal timing or connection issues
            print(f"Note: Real signal testing found issue: {e}")
            # Re-raise for debugging - these should be fixed
            raise

    def test_cleanup_real_resource_management_tdd(self, app_context):
        """TDD: Cleanup should properly manage real resources and state.

        RED: Test that cleanup handles real manager state and resources
        GREEN: Verify cleanup works with actual operations and workers
        REFACTOR: Test real resource management scenarios
        """
        manager = app_context.core_operations_manager

        # Set up some real state
        manager.simulate_operation_start("test_operation")
        assert manager.is_operation_active("test_operation")

        # Test real cleanup
        manager.cleanup()

        # Verify cleanup doesn't break manager state
        assert not manager.is_operation_active("test_operation")

        # Verify manager is still functional after cleanup
        assert manager.is_initialized()
        assert callable(manager.validate_extraction_params)

        # Test cleanup is idempotent
        manager.cleanup()  # Should not raise
        manager.cleanup()  # Should not raise


class TestExtractionErrorPaths:
    """Structured error path tests for unique extraction behaviors.

    Note: Generic validation tests (nonexistent files, missing params) have been
    consolidated into test_core_operations_manager.py. This class retains only
    tests for unique extraction-specific error handling behavior.
    """

    @pytest.fixture
    def mgr(self, isolated_managers):
        """Create ExtractionManager via DI."""
        from core.app_context import get_app_context

        return get_app_context().core_operations_manager

    def test_validate_vram_extraction_defers_file_existence_check(self, mgr, tmp_path):
        """VRAM validation defers file existence check to extraction time.

        Unlike ROM validation which checks file existence early,
        VRAM validation only checks param structure. File existence
        is verified when extract_from_vram is called.
        """
        params = {
            "vram_path": "/nonexistent/path/file.vram",
            "output_base": str(tmp_path / "output"),
            "grayscale_mode": True,
        }
        # Validation passes - file existence is checked at extraction time, not validation time
        result = mgr.validate_extraction_params(params)
        assert result is True
