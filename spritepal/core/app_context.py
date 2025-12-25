"""Application context for explicit dependency wiring.

This module provides AppContext, a dataclass that holds all application-level
dependencies with explicit wiring. It replaces the DI container with a simpler,
more transparent approach.

Usage:
    # In launch_spritepal.py
    context = create_app_context('SpritePal', settings_path=config.settings_file)
    app = SpritePalApp(sys.argv)
    app.main_window = MainWindow(context=context)

    # Access managers via context
    state_manager = context.application_state_manager
    operations = context.core_operations_manager
"""
from __future__ import annotations

import atexit
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.configuration_service import ConfigurationService
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.managers.sprite_preset_manager import SpritePresetManager
    from core.rom_extractor import ROMExtractor
    from core.services.rom_cache import ROMCache

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """
    Holds all application-level dependencies with explicit wiring.

    This replaces the DI container with a simple, explicit object.
    Dependencies are created in order and passed explicitly.

    Attributes:
        configuration_service: Configuration and paths
        application_state_manager: Session, settings, and state management
        sprite_preset_manager: Sprite preset management
        core_operations_manager: Extraction and injection operations

    Lazy-initialized (via properties):
        rom_cache: ROM caching service (created on first access)
        rom_extractor: ROM extraction service (created on first access)
    """

    configuration_service: ConfigurationService
    application_state_manager: ApplicationStateManager
    sprite_preset_manager: SpritePresetManager
    core_operations_manager: CoreOperationsManager

    # Lazy-initialized (created on first access)
    _rom_cache: ROMCache | None = field(default=None, repr=False)
    _rom_extractor: ROMExtractor | None = field(default=None, repr=False)

    # Thread safety for lazy initialization
    _lazy_lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def rom_cache(self) -> ROMCache:
        """Lazy-initialize ROMCache on first access."""
        with self._lazy_lock:
            if self._rom_cache is None:
                from core.services.rom_cache import ROMCache

                self._rom_cache = ROMCache(state_manager=self.application_state_manager)
                logger.debug("Created ROMCache via lazy initialization")
            return self._rom_cache

    @property
    def rom_extractor(self) -> ROMExtractor:
        """Lazy-initialize ROMExtractor on first access."""
        with self._lazy_lock:
            if self._rom_extractor is None:
                from core.rom_extractor import ROMExtractor

                self._rom_extractor = ROMExtractor(rom_cache=self.rom_cache)
                logger.debug("Created ROMExtractor via lazy initialization")
            return self._rom_extractor

    def cleanup(self) -> None:
        """Cleanup all managers in reverse initialization order."""
        logger.info("Cleaning up AppContext...")

        # Cleanup in reverse order of initialization
        for mgr in [
            self.core_operations_manager,
            self.sprite_preset_manager,
            self.application_state_manager,
        ]:
            if hasattr(mgr, "cleanup"):
                try:
                    mgr.cleanup()
                    logger.debug("Cleaned up %s", type(mgr).__name__)
                except Exception:
                    logger.warning(
                        "Error cleaning up %s", type(mgr).__name__, exc_info=True
                    )

        logger.info("AppContext cleanup complete")


# Global context (for transition period and simplified access)
_app_context: AppContext | None = None
_context_lock = threading.RLock()
_cleanup_registered = False


def get_app_context() -> AppContext:
    """Get the global app context.

    Raises:
        RuntimeError: If AppContext not initialized (call create_app_context first)
    """
    if _app_context is None:
        raise RuntimeError(
            "AppContext not initialized. Call create_app_context() first."
        )
    return _app_context


def get_app_context_optional() -> AppContext | None:
    """Get the global app context if initialized, otherwise None."""
    return _app_context


def create_app_context(
    app_name: str = "SpritePal",
    settings_path: Path | None = None,
    configuration_service: ConfigurationService | None = None,
    qt_parent: QObject | None = None,
) -> AppContext:
    """
    Create and set the global AppContext.

    This is the new explicit initialization, replacing initialize_managers().
    Creates all managers in dependency order:
    1. ConfigurationService (if not provided)
    2. ApplicationStateManager
    3. SpritePresetManager
    4. CoreOperationsManager
    5. ROMCache and ROMExtractor (lazy, on first access)

    Args:
        app_name: Application name for settings
        settings_path: Optional custom path for settings file (for testing)
        configuration_service: Optional pre-created ConfigurationService
        qt_parent: Optional Qt parent for managers (uses QApplication.instance() if None)

    Returns:
        The created AppContext
    """
    global _app_context, _cleanup_registered

    with _context_lock:
        if _app_context is not None:
            logger.debug("AppContext already exists, returning existing instance")
            return _app_context

        logger.info("Creating AppContext...")

        from PySide6.QtWidgets import QApplication

        from core.configuration_service import ConfigurationService as ConfigService
        from core.managers.application_state_manager import ApplicationStateManager
        from core.managers.core_operations_manager import CoreOperationsManager
        from core.managers.sprite_preset_manager import SpritePresetManager

        # Use QApplication instance if no parent provided
        if qt_parent is None:
            qt_parent = QApplication.instance()
            if qt_parent is None:
                logger.warning(
                    "No QApplication instance found - managers will have no Qt parent"
                )

        # 1. ConfigurationService
        if configuration_service is None:
            configuration_service = ConfigService()
        logger.debug("ConfigurationService ready")

        # 2. ApplicationStateManager (no deps on other managers)
        state_mgr = ApplicationStateManager(
            app_name,
            settings_path,
            parent=qt_parent,
            configuration_service=configuration_service,
        )
        logger.debug("ApplicationStateManager created")

        # 3. SpritePresetManager (no deps on other managers)
        preset_mgr = SpritePresetManager(
            config_service=configuration_service,
            parent=qt_parent,
        )
        logger.debug("SpritePresetManager created")

        # 4. Create ROMCache and ROMExtractor first (needed by CoreOperationsManager)
        from core.rom_extractor import ROMExtractor
        from core.services.rom_cache import ROMCache

        rom_cache = ROMCache(state_manager=state_mgr)
        logger.debug("ROMCache created")

        rom_extractor = ROMExtractor(rom_cache=rom_cache)
        logger.debug("ROMExtractor created")

        # 5. CoreOperationsManager (with explicit dependencies)
        core_ops = CoreOperationsManager(
            parent=qt_parent,
            session_manager=state_mgr,
            rom_cache=rom_cache,
            rom_extractor=rom_extractor,
        )
        logger.debug("CoreOperationsManager created")

        # Create the context with pre-created components
        _app_context = AppContext(
            configuration_service=configuration_service,
            application_state_manager=state_mgr,
            sprite_preset_manager=preset_mgr,
            core_operations_manager=core_ops,
            _rom_cache=rom_cache,
            _rom_extractor=rom_extractor,
        )

        # Register cleanup hooks
        if not _cleanup_registered:
            if qt_parent is not None:
                qt_parent.aboutToQuit.connect(_cleanup_app_context)  # type: ignore[union-attr]
            atexit.register(_cleanup_app_context)
            _cleanup_registered = True
            logger.debug("Cleanup hooks registered")

        logger.info("AppContext created successfully")
        return _app_context


def _cleanup_app_context() -> None:
    """Internal cleanup callback for atexit and Qt aboutToQuit."""
    global _app_context

    with _context_lock:
        if _app_context is not None:
            _app_context.cleanup()
            _app_context = None


def reset_app_context() -> None:
    """Reset the global app context.

    WARNING: This method is for test infrastructure only.
    Do not use in production code.
    """
    global _app_context, _cleanup_registered

    with _context_lock:
        if _app_context is not None:
            _app_context.cleanup()
            _app_context = None
        _cleanup_registered = False
        logger.debug("AppContext reset")


def is_context_initialized() -> bool:
    """Check if AppContext is initialized."""
    return _app_context is not None
