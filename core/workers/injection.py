"""
Injection worker implementations.

These workers handle VRAM and ROM injection operations by delegating
to the CoreOperationsManager while providing consistent threading interfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast, override

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

from PySide6.QtCore import Signal

from core.managers.base_manager import BaseManager
from core.managers.core_operations_manager import CoreOperationsManager
from utils.logging_config import get_logger

from .base import ManagedWorker, handle_worker_errors
from .specialized import SignalConnectionHelper

logger = get_logger(__name__)


# Type definitions for injection parameters
class VRAMInjectionParams(TypedDict, total=False):
    """Type definition for VRAM injection parameters"""

    mode: str  # "vram"
    sprite_path: str
    input_vram: str
    output_vram: str
    offset: int
    metadata_path: str | None


class ROMInjectionParams(TypedDict, total=False):
    """Type definition for ROM injection parameters"""

    mode: str  # "rom"
    sprite_path: str
    input_rom: str
    output_rom: str
    offset: int
    fast_compression: bool
    metadata_path: str | None


class VRAMInjectionWorker(ManagedWorker):
    """
    Worker for VRAM injection operations.

    Handles injection of sprites into VRAM memory dumps using
    CoreOperationsManager, providing progress updates during the injection process.
    """

    # Injection-specific signals
    progress_percent = Signal(int)  # Progress percentage (0-100)
    compression_info = Signal(object)  # Compression statistics
    injection_finished = Signal(bool, str)  # success, message

    def __init__(
        self,
        params: VRAMInjectionParams,
        injection_manager: BaseManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(manager=injection_manager, parent=parent)
        self.params = params
        self._operation_name = "VRAMInjectionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect injection manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        if not helper.validate_manager_type(CoreOperationsManager, "VRAM injection"):
            return

        # Type cast for better type checking
        injection_manager = cast(CoreOperationsManager, self.manager)

        # Connect all standard signals using helper
        helper.connect_progress_signals("injection_progress", 50)
        helper.connect_injection_signals(injection_manager)
        helper.connect_completion_signals(injection_manager)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("VRAM injection")
    def perform_operation(self) -> None:
        """Perform VRAM injection using SpriteInjector directly.

        This method calls the actual injection business logic instead of delegating
        back to the manager (which would cause infinite recursion by creating another worker).
        """
        from core.injector import SpriteInjector

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting VRAM injection")
        self.emit_progress(10, "Starting VRAM injection...")

        # Create injector instance
        injector = SpriteInjector()

        # Load metadata if provided
        metadata_path = self.params.get("metadata_path")
        if metadata_path:
            self.emit_progress(20, "Loading metadata...")
            injector.load_metadata(metadata_path)

        self.check_cancellation()
        self.emit_progress(40, "Injecting sprite into VRAM...")

        # Extract parameters
        sprite_path = self.params.get("sprite_path", "")
        input_vram = self.params.get("input_vram", "")
        output_vram = self.params.get("output_vram", "")
        offset = self.params.get("offset")

        # Perform the actual injection
        success, message = injector.inject_sprite(
            sprite_path=sprite_path,
            vram_path=input_vram,
            output_path=output_vram,
            offset=offset,
        )

        self.emit_progress(100, "VRAM injection complete")

        if success:
            logger.info(f"{self._operation_name}: {message}")
            self.injection_finished.emit(True, message)
            self.operation_finished.emit(True, message)
        else:
            logger.error(f"{self._operation_name}: {message}")
            self.emit_error(message)
            self.injection_finished.emit(False, message)
            self.operation_finished.emit(False, message)


class ROMInjectionWorker(ManagedWorker):
    """
    Worker for ROM injection operations.

    Handles injection of sprites into ROM files using
    CoreOperationsManager, providing progress updates and compression info.
    """

    # Injection-specific signals
    progress_percent = Signal(int)  # Progress percentage (0-100)
    compression_info = Signal(object)  # Compression statistics
    injection_finished = Signal(bool, str)  # success, message

    def __init__(
        self,
        params: ROMInjectionParams,
        injection_manager: BaseManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(manager=injection_manager, parent=parent)
        self.params = params
        self._operation_name = "ROMInjectionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect injection manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        if not helper.validate_manager_type(CoreOperationsManager, "ROM injection"):
            return

        # Type cast for better type checking
        injection_manager = cast(CoreOperationsManager, self.manager)

        # Connect all standard signals using helper
        helper.connect_progress_signals("injection_progress", 50)
        helper.connect_injection_signals(injection_manager)
        helper.connect_completion_signals(injection_manager)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("ROM injection")
    def perform_operation(self) -> None:
        """Perform ROM injection using ROMInjector directly.

        This method calls the actual injection business logic instead of delegating
        back to the manager (which would cause infinite recursion by creating another worker).
        """
        # Type cast for better type safety
        injection_manager = cast(CoreOperationsManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting ROM injection")
        self.emit_progress(10, "Starting ROM injection...")

        # Access the ROMInjector through the manager's rom_extractor
        # The rom_extractor is a required dependency of CoreOperationsManager
        rom_extractor = injection_manager._rom_extractor
        if rom_extractor is None:
            error_msg = "ROM extractor not initialized"
            logger.error(f"{self._operation_name}: {error_msg}")
            self.emit_error(error_msg)
            self.injection_finished.emit(False, error_msg)
            self.operation_finished.emit(False, error_msg)
            return

        rom_injector = rom_extractor.rom_injector

        self.check_cancellation()
        self.emit_progress(30, "Compressing and injecting sprite into ROM...")

        # Extract parameters
        sprite_path = self.params.get("sprite_path", "")
        input_rom = self.params.get("input_rom", "")
        output_rom = self.params.get("output_rom", "")
        offset = self.params.get("offset", 0)
        fast_compression = self.params.get("fast_compression", False)

        # Perform the actual injection
        success, message = rom_injector.inject_sprite_to_rom(
            sprite_path=sprite_path,
            rom_path=input_rom,
            output_path=output_rom,
            sprite_offset=offset,
            fast_compression=fast_compression,
        )

        self.emit_progress(100, "ROM injection complete")

        if success:
            logger.info(f"{self._operation_name}: {message}")
            self.injection_finished.emit(True, message)
            self.operation_finished.emit(True, message)
        else:
            logger.error(f"{self._operation_name}: {message}")
            self.emit_error(message)
            self.injection_finished.emit(False, message)
            self.operation_finished.emit(False, message)
