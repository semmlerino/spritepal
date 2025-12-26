"""
Injection Operations Manager.

Handles ROM and VRAM injection validation and status checking.
This is a focused sub-manager delegated from CoreOperationsManager.

Note: Worker lifecycle remains in CoreOperationsManager because workers
receive a manager reference and call methods on it. Moving worker management
here would require updating worker contracts.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QObject, QThread, Signal

from core.exceptions import ValidationError
from utils.file_validator import FileValidator
from utils.validation import validate_range, validate_required_params, validate_type

if TYPE_CHECKING:
    from core.services.rom_cache import ROMCache


class InjectionOperationsManager(QObject):
    """
    Manages injection validation and status for ROM and VRAM data.

    Responsibilities:
    - Injection parameter validation
    - Injection status checking

    Note: Worker lifecycle management remains in CoreOperationsManager
    to maintain backward compatibility with worker contracts.

    Thread-safe: Worker access is protected by a lock.
    """

    # Injection signals
    injection_progress = Signal(str)  # progress message
    injection_finished = Signal(bool, str)  # success, message
    compression_info = Signal(object)  # compression statistics
    progress_percent = Signal(int)  # percent (for progress bars)

    def __init__(
        self,
        *,
        rom_cache: ROMCache | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initialize injection operations manager.

        Args:
            rom_cache: Cache for ROM data (for invalidation after injection)
            parent: Qt parent object
        """
        super().__init__(parent)
        self._logger = logging.getLogger(__name__)

        # Dependencies
        self._rom_cache = rom_cache

        # Worker management (tracked here for status, lifecycle in facade)
        self._current_worker: QThread | None = None
        self._lock = threading.RLock()

    # ========== Validation ==========

    def validate_injection_params(self, params: Mapping[str, object]) -> None:
        """
        Validate injection parameters.

        Args:
            params: Parameters to validate

        Raises:
            ValidationError: If parameters are invalid
        """
        # Check required common parameters
        required = ["mode", "sprite_path", "offset"]
        validate_required_params(params, required)

        validate_type(params["mode"], "mode", str)
        validate_type(params["sprite_path"], "sprite_path", str)
        validate_type(params["offset"], "offset", int)

        # Use FileValidator for sprite file validation
        sprite_path = cast(str, params["sprite_path"])
        sprite_result = FileValidator.validate_image_file(sprite_path)
        if not sprite_result.is_valid:
            raise ValidationError(f"Sprite file validation failed: {sprite_result.error_message}")

        offset = cast(int, params["offset"])
        validate_range(offset, "offset", min_val=0)

        # Check mode-specific parameters
        mode = cast(str, params["mode"])
        if mode == "vram":
            vram_required = ["input_vram", "output_vram"]
            validate_required_params(params, vram_required)

            input_vram = cast(str, params["input_vram"])
            vram_result = FileValidator.validate_vram_file(input_vram)
            if not vram_result.is_valid:
                raise ValidationError(f"Input VRAM file validation failed: {vram_result.error_message}")

        elif mode == "rom":
            rom_required = ["input_rom", "output_rom"]
            validate_required_params(params, rom_required)

            input_rom = cast(str, params["input_rom"])
            rom_result = FileValidator.validate_rom_file(input_rom)
            if not rom_result.is_valid:
                raise ValidationError(f"Input ROM file validation failed: {rom_result.error_message}")

            # Validate optional fast_compression parameter
            if "fast_compression" in params:
                validate_type(params["fast_compression"], "fast_compression", bool)
        else:
            raise ValidationError(f"Invalid injection mode: {mode}")

        # Validate optional metadata_path
        metadata_path_val = params.get("metadata_path")
        if metadata_path_val:
            metadata_path = cast(str, metadata_path_val)
            metadata_result = FileValidator.validate_json_file(metadata_path)
            if not metadata_result.is_valid:
                raise ValidationError(f"Metadata file validation failed: {metadata_result.error_message}")

    # ========== Status ==========

    def is_injection_active(self) -> bool:
        """Check if an injection worker is currently running."""
        with self._lock:
            return self._current_worker is not None and self._current_worker.isRunning()

    # ========== State Management ==========

    def reset_state(self) -> None:
        """Reset internal state for test isolation."""
        with self._lock:
            if self._current_worker is not None:
                self._logger.debug("Cleaning up worker during reset_state")
                # Best-effort cleanup
                if self._current_worker.isRunning():
                    self._current_worker.quit()
                    self._current_worker.wait(1000)
                self._current_worker = None
