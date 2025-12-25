"""
Manager classes for SpritePal business logic.

This package provides the consolidated manager architecture. The recommended
way to access managers is via dependency injection::

    from core.di_container import inject
    from core.managers import ApplicationStateManager, CoreOperationsManager

    state_mgr = inject(ApplicationStateManager)
    ops_mgr = inject(CoreOperationsManager)

Architecture:
    - ApplicationStateManager: Consolidated manager for session, settings, state
    - CoreOperationsManager: Consolidated manager for extraction, injection, palette
"""
from __future__ import annotations

import atexit
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from core.exceptions import (
    ExtractionError,
    FileOperationError,
    InjectionError,
    ManagerError,
    NavigationError,
    PreviewError,
    SessionError,
    ValidationError,
)
from utils.logging_config import get_logger

from .application_state_manager import ApplicationStateManager
from .base_manager import BaseManager
from .core_operations_manager import CoreOperationsManager
from .sprite_preset_manager import SpritePresetManager
from .workflow_manager import ExtractionState
from .workflow_state_manager import WorkflowStateManager

if TYPE_CHECKING:
    from core.configuration_service import ConfigurationService

_logger = get_logger("managers")

# Module-level state
_initialized = False
_cleanup_registered = False
_lock = threading.RLock()


def initialize_managers(
    app_name: str = "SpritePal",
    settings_path: Path | None = None,
    configuration_service: ConfigurationService | None = None,
) -> None:
    """
    Initialize all managers in dependency order.

    Uses the consolidated manager architecture where:
    - ApplicationStateManager handles session, settings, state, and history
    - CoreOperationsManager handles extraction and injection operations

    Args:
        app_name: Application name for settings
        settings_path: Optional custom settings path (for testing)
        configuration_service: Optional pre-created ConfigurationService instance
    """
    global _initialized, _cleanup_registered

    with _lock:
        if _initialized:
            _logger.debug("Managers already initialized, skipping")
            return

        _logger.info("Initializing managers...")

        from PySide6.QtWidgets import QApplication

        from core.configuration_service import ConfigurationService as ConfigService
        from core.di_container import register_factory, register_singleton
        from core.rom_extractor import ROMExtractor
        from core.services.rom_cache import ROMCache

        qt_parent = QApplication.instance()
        if not qt_parent:
            _logger.warning("No QApplication instance found - managers will have no Qt parent")

        try:
            # 1. ConfigurationService
            if configuration_service is None:
                configuration_service = ConfigService()
            register_singleton(ConfigService, configuration_service)

            # 2. ApplicationStateManager (no deps on other managers)
            state_mgr = ApplicationStateManager(
                app_name,
                settings_path,
                parent=qt_parent,
                configuration_service=configuration_service,
            )
            register_singleton(ApplicationStateManager, state_mgr)
            _logger.debug("ApplicationStateManager created and registered")

            # 3. SpritePresetManager (no deps on other managers)
            preset_mgr = SpritePresetManager(
                config_service=configuration_service,
                parent=qt_parent,
            )
            register_singleton(SpritePresetManager, preset_mgr)
            _logger.debug("SpritePresetManager created and registered")

            # 4. Register lazy factories BEFORE CoreOperationsManager
            # (CoreOperationsManager._initialize() calls inject(ROMExtractor))
            def _create_rom_cache() -> ROMCache:
                from core.di_container import inject

                return ROMCache(state_manager=inject(ApplicationStateManager))

            register_factory(ROMCache, _create_rom_cache)

            def _create_rom_extractor() -> ROMExtractor:
                from core.di_container import inject

                return ROMExtractor(rom_cache=inject(ROMCache))

            register_factory(ROMExtractor, _create_rom_extractor)
            _logger.debug("ROMCache and ROMExtractor factories registered")

            # 5. CoreOperationsManager (accesses ROMExtractor via inject internally)
            core_ops = CoreOperationsManager(parent=qt_parent)
            register_singleton(CoreOperationsManager, core_ops)
            _logger.debug("CoreOperationsManager created and registered")

            _initialized = True
            _logger.info("All managers initialized successfully")

            # Register cleanup hooks
            if not _cleanup_registered:
                if qt_parent is not None:
                    qt_parent.aboutToQuit.connect(cleanup_managers)
                    # Sync with ManagerRegistry class variable for backwards compat
                    ManagerRegistry._cleanup_registered = True
                atexit.register(cleanup_managers)
                _cleanup_registered = True
                _logger.debug("Cleanup hooks registered")

        except Exception as e:
            _logger.exception(f"Manager initialization failed: {e}")
            # Cleanup any partial registrations
            _cleanup_partial()
            raise ManagerError(f"Failed to initialize managers: {e}") from e


def _cleanup_partial() -> None:
    """Clean up partial registrations after failed initialization."""
    from core.di_container import get_container, reset_container

    container = get_container()
    for mgr_type in [CoreOperationsManager, SpritePresetManager, ApplicationStateManager]:
        mgr = container.get_optional(mgr_type)
        if mgr is not None:
            try:
                mgr.cleanup()
            except Exception:
                pass
    reset_container()


def cleanup_managers() -> None:
    """Cleanup all managers in reverse initialization order."""
    global _initialized

    with _lock:
        if not _initialized:
            return

        _logger.info("Cleaning up managers...")

        from core.di_container import get_container, reset_container

        container = get_container()

        # Cleanup in reverse order
        for mgr_type in [CoreOperationsManager, SpritePresetManager, ApplicationStateManager]:
            mgr = container.get_optional(mgr_type)
            if mgr is not None:
                try:
                    mgr.cleanup()
                    _logger.debug("Cleaned up %s", mgr_type.__name__)
                except Exception:
                    _logger.warning("Error cleaning up %s", mgr_type.__name__, exc_info=True)

        reset_container()
        _initialized = False
        _logger.info("All managers cleaned up")


def is_initialized() -> bool:
    """Check if managers are initialized."""
    return _initialized


def validate_manager_dependencies() -> bool:
    """
    Validate that all managers and their dependencies are properly initialized.

    Returns:
        True if all dependencies are satisfied, False otherwise
    """
    if not _initialized:
        _logger.warning("Managers not initialized, cannot validate dependencies")
        return False

    from core.di_container import get_container

    container = get_container()

    try:
        for mgr_type in [ApplicationStateManager, SpritePresetManager, CoreOperationsManager]:
            mgr = container.get_optional(mgr_type)
            if mgr is None:
                raise ManagerError(f"{mgr_type.__name__} not registered")
            if not mgr.is_initialized():
                raise ManagerError(f"{mgr_type.__name__} not properly initialized")

        _logger.debug("All manager dependencies validated successfully")
        return True

    except Exception as e:
        _logger.exception(f"Manager dependency validation failed: {e}")
        return False


def reset_for_tests() -> None:
    """Reset manager state for test isolation.

    WARNING: This method is for test infrastructure only.
    Do not use in production code.
    """
    global _initialized, _cleanup_registered

    with _lock:
        from core.di_container import reset_container

        reset_container()
        _initialized = False
        _cleanup_registered = False


# Backwards compatibility shim - kept for test infrastructure that still uses the class
# TODO: Refactor tests/infrastructure/* to use module-level functions, then remove this
class ManagerRegistry:
    """Minimal backwards-compatible shim for test infrastructure.

    DEPRECATED: Use module-level functions instead:
        - initialize_managers()
        - cleanup_managers()
        - is_initialized()
        - reset_for_tests()
    """

    _instance: ManagerRegistry | None = None
    _lock: threading.RLock = threading.RLock()
    _cleanup_registered: bool = False

    def __new__(cls) -> ManagerRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        pass

    def initialize_managers(
        self,
        app_name: str = "SpritePal",
        settings_path: Path | None = None,
        configuration_service: ConfigurationService | None = None,
    ) -> None:
        initialize_managers(app_name, settings_path, configuration_service)

    def cleanup_managers(self) -> None:
        cleanup_managers()

    def is_initialized(self) -> bool:
        return is_initialized()

    @classmethod
    def is_clean(cls) -> bool:
        return not _initialized

    @classmethod
    def reset_for_tests(cls) -> None:
        with cls._lock:
            reset_for_tests()
            cls._instance = None
            cls._cleanup_registered = False


__all__ = [
    "ApplicationStateManager",
    "BaseManager",
    "CoreOperationsManager",
    "ExtractionError",
    "ExtractionState",
    "FileOperationError",
    "InjectionError",
    "ManagerError",
    "ManagerRegistry",
    "NavigationError",
    "PreviewError",
    "SessionError",
    "SpritePresetManager",
    "ValidationError",
    "WorkflowStateManager",
    "cleanup_managers",
    "initialize_managers",
    "is_initialized",
    "reset_for_tests",
    "validate_manager_dependencies",
]
