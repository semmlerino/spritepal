"""
Injection worker implementations using the new base classes.

These workers handle VRAM and ROM injection operations by delegating
to the InjectionManager while providing consistent threading interfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

try:
    from typing import override
except ImportError:
    from typing import override

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.managers.factory import ManagerFactory

from core.managers import InjectionManager
from utils.logging_config import get_logger

from .base import handle_worker_errors
from .specialized import (
    InjectionWorkerBase,
    SignalConnectionHelper,
    WorkerOwnedManagerMixin,
)

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

class VRAMInjectionWorker(InjectionWorkerBase):
    """
    Worker for VRAM injection operations using singleton InjectionManager.

    Handles injection of sprites into VRAM memory dumps using the global
    InjectionManager, providing progress updates during the injection process.
    """

    def __init__(
        self,
        params: VRAMInjectionParams,
        injection_manager: InjectionManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(injection_manager, parent)
        self.params = params
        self._operation_name = "VRAMInjectionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect injection manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        def _get_expected_manager() -> InjectionManager:
            from core.di_container import inject
            from core.protocols.manager_protocols import InjectionManagerProtocol
            return inject(InjectionManagerProtocol)  # type: ignore[return-value]
        if not helper.validate_manager_type(_get_expected_manager, "VRAM injection"):
            return

        # Type cast for better type checking
        injection_manager = cast(InjectionManager, self.manager)

        # Connect all standard signals using helper
        helper.connect_progress_signals("injection_progress", 50)
        helper.connect_injection_signals(injection_manager)
        helper.connect_completion_signals(injection_manager)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("VRAM injection")
    def perform_operation(self) -> None:
        """Perform VRAM injection via manager."""
        # Type cast for better type safety
        injection_manager = cast(InjectionManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting VRAM injection")
        self.emit_progress(10, "Starting VRAM injection...")

        # Perform injection using manager
        success = injection_manager.start_injection(dict(self.params))

        if success:
            logger.info(f"{self._operation_name}: Injection started successfully")
            # The manager will emit completion signals when done via connected signals
        else:
            error_msg = "Failed to start injection"
            logger.error(f"{self._operation_name}: {error_msg}")
            self.emit_error(error_msg)
            self.operation_finished.emit(False, error_msg)

class ROMInjectionWorker(InjectionWorkerBase):
    """
    Worker for ROM injection operations using singleton InjectionManager.

    Handles injection of sprites into ROM files using the global
    InjectionManager, providing progress updates and compression info.
    """

    def __init__(
        self,
        params: ROMInjectionParams,
        injection_manager: InjectionManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(injection_manager, parent)
        self.params = params
        self._operation_name = "ROMInjectionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect injection manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        def _get_expected_manager() -> InjectionManager:
            from core.di_container import inject
            from core.protocols.manager_protocols import InjectionManagerProtocol
            return inject(InjectionManagerProtocol)  # type: ignore[return-value]
        if not helper.validate_manager_type(_get_expected_manager, "ROM injection"):
            return

        # Type cast for better type checking
        injection_manager = cast(InjectionManager, self.manager)

        # Connect all standard signals using helper
        helper.connect_progress_signals("injection_progress", 50)
        helper.connect_injection_signals(injection_manager)
        helper.connect_completion_signals(injection_manager)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("ROM injection")
    def perform_operation(self) -> None:
        """Perform ROM injection via manager."""
        # Type cast for better type safety
        injection_manager = cast(InjectionManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting ROM injection")
        self.emit_progress(10, "Starting ROM injection...")

        # Perform injection using manager
        success = injection_manager.start_injection(dict(self.params))

        if success:
            logger.info(f"{self._operation_name}: ROM injection started successfully")
            # The manager will emit completion signals when done
        else:
            error_msg = "Failed to start ROM injection"
            logger.error(f"{self._operation_name}: {error_msg}")
            self.emit_error(error_msg)
            self.operation_finished.emit(False, error_msg)

# Worker-owned manager pattern (Phase 2 architecture)
class WorkerOwnedVRAMInjectionWorker(InjectionWorkerBase, WorkerOwnedManagerMixin):
    """
    VRAM injection worker that owns its own InjectionManager instance.

    This pattern provides perfect thread isolation and eliminates cross-thread
    issues by ensuring each worker has its own manager with proper Qt parent.
    Recommended for new code.
    """

    def __init__(
        self,
        params: VRAMInjectionParams,
        manager_factory: ManagerFactory | None = None,
        parent: QObject | None = None
    ) -> None:
        # Create manager using standardized worker-owned pattern
        manager = self.create_worker_owned_manager(
            manager_factory,
            lambda factory, parent: factory.create_injection_manager(parent=parent),
            parent
        )

        # Initialize parent class with the manager
        super().__init__(manager, parent)

        # Complete worker-owned manager setup
        self.setup_worker_owned_manager(manager)

        self.params = params
        self._operation_name = "WorkerOwnedVRAMInjectionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect injection manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        def _get_expected_manager() -> InjectionManager:
            from core.di_container import inject
            from core.protocols.manager_protocols import InjectionManagerProtocol
            return inject(InjectionManagerProtocol)  # type: ignore[return-value]
        if not helper.validate_manager_type(_get_expected_manager, "VRAM injection"):
            return

        # Type cast for better type checking
        injection_manager = cast(InjectionManager, self.manager)

        # Connect all standard signals using helper
        helper.connect_progress_signals("injection_progress", 50)
        helper.connect_injection_signals(injection_manager)
        helper.connect_completion_signals(injection_manager)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("VRAM injection")
    def perform_operation(self) -> None:
        """Perform VRAM injection via worker-owned manager."""
        # Type cast for better type safety
        injection_manager = cast(InjectionManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting VRAM injection")
        self.emit_progress(10, "Starting VRAM injection...")

        # Perform injection using manager
        success = injection_manager.start_injection(dict(self.params))

        if success:
            logger.info(f"{self._operation_name}: Injection started successfully")
            # The manager will emit completion signals when done via connected signals
        else:
            error_msg = "Failed to start injection"
            logger.error(f"{self._operation_name}: {error_msg}")
            self.emit_error(error_msg)
            self.operation_finished.emit(False, error_msg)

class WorkerOwnedROMInjectionWorker(InjectionWorkerBase, WorkerOwnedManagerMixin):
    """
    ROM injection worker that owns its own InjectionManager instance.

    This pattern provides perfect thread isolation and eliminates cross-thread
    issues by ensuring each worker has its own manager with proper Qt parent.
    Recommended for new code.
    """

    def __init__(
        self,
        params: ROMInjectionParams,
        manager_factory: ManagerFactory | None = None,
        parent: QObject | None = None
    ) -> None:
        # Create manager using standardized worker-owned pattern
        manager = self.create_worker_owned_manager(
            manager_factory,
            lambda factory, parent: factory.create_injection_manager(parent=parent),
            parent
        )

        # Initialize parent class with the manager
        super().__init__(manager, parent)

        # Complete worker-owned manager setup
        self.setup_worker_owned_manager(manager)

        self.params = params
        self._operation_name = "WorkerOwnedROMInjectionWorker"

    @override
    def connect_manager_signals(self) -> None:
        """Connect injection manager signals to worker signals."""
        helper = SignalConnectionHelper(self)

        # Validate manager type
        def _get_expected_manager() -> InjectionManager:
            from core.di_container import inject
            from core.protocols.manager_protocols import InjectionManagerProtocol
            return inject(InjectionManagerProtocol)  # type: ignore[return-value]
        if not helper.validate_manager_type(_get_expected_manager, "ROM injection"):
            return

        # Type cast for better type checking
        injection_manager = cast(InjectionManager, self.manager)

        # Connect all standard signals using helper
        helper.connect_progress_signals("injection_progress", 50)
        helper.connect_injection_signals(injection_manager)
        helper.connect_completion_signals(injection_manager)

        logger.debug(f"{self._operation_name}: Connected {len(self._connections)} manager signals")

    @override
    @handle_worker_errors("ROM injection")
    def perform_operation(self) -> None:
        """Perform ROM injection via worker-owned manager."""
        # Type cast for better type safety
        injection_manager = cast(InjectionManager, self.manager)

        # Check for cancellation before starting
        self.check_cancellation()

        logger.info(f"{self._operation_name}: Starting ROM injection")
        self.emit_progress(10, "Starting ROM injection...")

        # Perform injection using manager
        success = injection_manager.start_injection(dict(self.params))

        if success:
            logger.info(f"{self._operation_name}: ROM injection started successfully")
            # The manager will emit completion signals when done
        else:
            error_msg = "Failed to start ROM injection"
            logger.error(f"{self._operation_name}: {error_msg}")
            self.emit_error(error_msg)
            self.operation_finished.emit(False, error_msg)
