"""
Extraction worker implementations using the new base classes.

These workers handle VRAM and ROM extraction operations by delegating
to the ExtractionManager while providing consistent threading interfaces.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, TypedDict, cast

try:
    from typing import NotRequired
except ImportError:
    from typing import NotRequired

from typing_extensions import override

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.managers import ExtractionManager
    from core.managers.factory import ManagerFactory

from core.managers.extraction_manager import ExtractionManager
from utils.logging_config import get_logger

from .base import handle_worker_errors
from .specialized import (
    ExtractionWorkerBase,
    SignalConnectionHelper,
    WorkerOwnedManagerMixin,
)

logger = get_logger(__name__)

# Type definitions for extraction parameters
class VRAMExtractionParams(TypedDict):
    """Type definition for VRAM extraction parameters"""
    vram_path: str
    output_base: str
    create_grayscale: bool
    create_metadata: bool
    grayscale_mode: bool
    cgram_path: NotRequired[str | None]
    oam_path: NotRequired[str | None]
    vram_offset: NotRequired[int | None]

class ROMExtractionParams(TypedDict):
    """Type definition for ROM extraction parameters"""
    rom_path: str
    sprite_offset: int
    output_base: str
    sprite_name: str
    cgram_path: NotRequired[str | None]

class VRAMExtractionWorker(ExtractionWorkerBase):
    """
    Worker for VRAM extraction operations.

    Handles extraction of sprites from VRAM memory dumps using the
    ExtractionManager, providing progress updates and preview generation.
    """

    def __init__(
        self,
        params: VRAMExtractionParams,
        extraction_manager: ExtractionManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        if extraction_manager is None:
            warnings.warn(
                "VRAMExtractionWorker: extraction_manager parameter will become required. "
                "Pass extraction_manager explicitly instead of relying on DI.",
                DeprecationWarning,
                stacklevel=2,
            )
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            extraction_manager = cast(ExtractionManager, inject(ExtractionManagerProtocol))
        super().__init__(manager=extraction_manager, parent=parent)
        self.params = params
        self._operation_name = "VRAMExtractionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect extraction manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        def _get_extraction_manager() -> ExtractionManager:
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            return cast(ExtractionManager, inject(ExtractionManagerProtocol))
        if not helper.validate_manager_type(_get_extraction_manager, "VRAM extraction"):
            return

        # Type cast for better type checking - we know this is ExtractionManager from __init__
        extraction_manager = cast(ExtractionManager, self.manager)

        # Connect all standard signals using helper
        helper.connect_progress_signals("extraction_progress", 50)
        helper.connect_extraction_signals(extraction_manager)
        helper.connect_preview_signals(extraction_manager)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("VRAM extraction")
    def perform_operation(self) -> None:
        """Perform VRAM extraction via manager."""
        # Type cast for better type safety
        extraction_manager = cast(ExtractionManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting VRAM extraction")
        self.emit_progress(10, "Starting VRAM extraction...")

        # Perform extraction using manager
        extracted_files = extraction_manager.extract_from_vram(
            vram_path=self.params["vram_path"],
            output_base=self.params["output_base"],
            cgram_path=self.params.get("cgram_path"),
            oam_path=self.params.get("oam_path"),
            vram_offset=self.params.get("vram_offset"),
            create_grayscale=self.params.get("create_grayscale", True),
            create_metadata=self.params.get("create_metadata", True),
            grayscale_mode=self.params.get("grayscale_mode", False),
        )

        # Check for cancellation after extraction
        self.check_cancellation()

        # Emit completion signals
        self.extraction_finished.emit(extracted_files)
        self.operation_finished.emit(True, f"Successfully extracted {len(extracted_files)} files")

        logger.info(f"{self._operation_name}: Extraction completed successfully")

class ROMExtractionWorker(ExtractionWorkerBase):
    """
    Worker for ROM extraction operations.

    Handles extraction of sprites from ROM files using the ExtractionManager,
    providing progress updates during the extraction process.
    """

    def __init__(
        self,
        params: ROMExtractionParams,
        extraction_manager: ExtractionManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        if extraction_manager is None:
            warnings.warn(
                "ROMExtractionWorker: extraction_manager parameter will become required. "
                "Pass extraction_manager explicitly instead of relying on DI.",
                DeprecationWarning,
                stacklevel=2,
            )
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            extraction_manager = cast(ExtractionManager, inject(ExtractionManagerProtocol))
        super().__init__(manager=extraction_manager, parent=parent)
        self.params = params
        self._operation_name = "ROMExtractionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect extraction manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        def _get_extraction_manager() -> ExtractionManager:
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            return cast(ExtractionManager, inject(ExtractionManagerProtocol))
        if not helper.validate_manager_type(_get_extraction_manager, "ROM extraction"):
            return

        # Connect standard progress signal using helper
        helper.connect_progress_signals("extraction_progress", 50)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("ROM extraction")
    def perform_operation(self) -> None:
        """Perform ROM extraction via manager."""
        # Type cast for better type safety
        extraction_manager = cast(ExtractionManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting ROM extraction")
        self.emit_progress(10, "Starting ROM extraction...")

        # Perform extraction using manager
        extracted_files = extraction_manager.extract_from_rom(
            rom_path=self.params["rom_path"],
            offset=self.params["sprite_offset"],
            output_base=self.params["output_base"],
            sprite_name=self.params["sprite_name"],
            cgram_path=self.params.get("cgram_path"),
        )

        # Check for cancellation after extraction
        self.check_cancellation()

        # Emit completion signals
        self.extraction_finished.emit(extracted_files)
        self.operation_finished.emit(True, f"Successfully extracted {len(extracted_files)} files")

        logger.info(f"{self._operation_name}: ROM extraction completed successfully")

# Worker-owned manager pattern (Phase 2 architecture)
class WorkerOwnedVRAMExtractionWorker(ExtractionWorkerBase, WorkerOwnedManagerMixin):
    """
    VRAM extraction worker that owns its own ExtractionManager instance.

    This pattern provides perfect thread isolation and eliminates cross-thread
    issues by ensuring each worker has its own manager with proper Qt parent.
    Recommended for new code.
    """

    def __init__(
        self,
        params: VRAMExtractionParams,
        manager_factory: ManagerFactory | None = None,
        parent: QObject | None = None
    ) -> None:
        # Create manager using standardized worker-owned pattern
        manager = self.create_worker_owned_manager(
            manager_factory,
            lambda factory, parent: factory.create_extraction_manager(parent=parent),
            parent
        )

        # Initialize parent class with the manager
        super().__init__(manager=manager, parent=parent)

        # Complete worker-owned manager setup
        self.setup_worker_owned_manager(manager)

        self.params = params
        self._operation_name = "WorkerOwnedVRAMExtractionWorker"
    @override
    def connect_manager_signals(self) -> None:
        """Connect extraction manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        def _get_extraction_manager() -> ExtractionManager:
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            return cast(ExtractionManager, inject(ExtractionManagerProtocol))
        if not helper.validate_manager_type(_get_extraction_manager, "VRAM extraction"):
            return

        # Type cast for better type checking - we know this is ExtractionManager from __init__
        extraction_manager = cast(ExtractionManager, self.manager)

        # Connect all standard signals using helper
        helper.connect_progress_signals("extraction_progress", 50)
        helper.connect_extraction_signals(extraction_manager)
        helper.connect_preview_signals(extraction_manager)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("VRAM extraction")
    def perform_operation(self) -> None:
        """Perform VRAM extraction via worker-owned manager."""
        # Type cast for better type safety
        extraction_manager = cast(ExtractionManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting VRAM extraction")
        self.emit_progress(10, "Starting VRAM extraction...")

        # Perform extraction using manager
        extracted_files = extraction_manager.extract_from_vram(
            vram_path=self.params["vram_path"],
            output_base=self.params["output_base"],
            cgram_path=self.params.get("cgram_path"),
            oam_path=self.params.get("oam_path"),
            vram_offset=self.params.get("vram_offset"),
            create_grayscale=self.params.get("create_grayscale", True),
            create_metadata=self.params.get("create_metadata", True),
            grayscale_mode=self.params.get("grayscale_mode", False),
        )

        # Check for cancellation after extraction
        self.check_cancellation()

        # Emit completion signals
        self.extraction_finished.emit(extracted_files)
        self.operation_finished.emit(True, f"Successfully extracted {len(extracted_files)} files")

        logger.info(f"{self._operation_name}: Extraction completed successfully")

class WorkerOwnedROMExtractionWorker(ExtractionWorkerBase, WorkerOwnedManagerMixin):
    """
    ROM extraction worker that owns its own ExtractionManager instance.

    This pattern provides perfect thread isolation and eliminates cross-thread
    issues by ensuring each worker has its own manager with proper Qt parent.
    Recommended for new code.
    """

    def __init__(
        self,
        params: ROMExtractionParams,
        manager_factory: ManagerFactory | None = None,
        parent: QObject | None = None
    ) -> None:
        # Create manager using standardized worker-owned pattern
        manager = self.create_worker_owned_manager(
            manager_factory,
            lambda factory, parent: factory.create_extraction_manager(parent=parent),
            parent
        )

        # Initialize parent class with the manager
        super().__init__(manager=manager, parent=parent)

        # Complete worker-owned manager setup
        self.setup_worker_owned_manager(manager)

        self.params = params
        self._operation_name = "WorkerOwnedROMExtractionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect extraction manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        def _get_extraction_manager() -> ExtractionManager:
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            return cast(ExtractionManager, inject(ExtractionManagerProtocol))
        if not helper.validate_manager_type(_get_extraction_manager, "ROM extraction"):
            return

        # Connect standard progress signal using helper
        helper.connect_progress_signals("extraction_progress", 50)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("ROM extraction")
    def perform_operation(self) -> None:
        """Perform ROM extraction via worker-owned manager."""
        # Type cast for better type safety
        extraction_manager = cast(ExtractionManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting ROM extraction")
        self.emit_progress(10, "Starting ROM extraction...")

        # Perform extraction using manager
        extracted_files = extraction_manager.extract_from_rom(
            rom_path=self.params["rom_path"],
            offset=self.params["sprite_offset"],
            output_base=self.params["output_base"],
            sprite_name=self.params["sprite_name"],
            cgram_path=self.params.get("cgram_path"),
        )

        # Check for cancellation after extraction
        self.check_cancellation()

        # Emit completion signals
        self.extraction_finished.emit(extracted_files)
        self.operation_finished.emit(True, f"Successfully extracted {len(extracted_files)} files")

        logger.info(f"{self._operation_name}: ROM extraction completed successfully")
