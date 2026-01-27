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
import contextlib
import logging
import threading
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtCore import QObject

    from core.configuration_service import ConfigurationService
    from core.default_palette_loader import DefaultPaletteLoader
    from core.hal_compression import HALCompressor
    from core.managers.application_state_manager import ApplicationStateManager
    from core.managers.core_operations_manager import CoreOperationsManager
    from core.managers.sprite_preset_manager import SpritePresetManager
    from core.mesen_integration.log_watcher import LogWatcher
    from core.rom_extractor import ROMExtractor
    from core.services.preview_generator import PreviewGenerator
    from core.services.rom_cache import ROMCache
    from core.sprite_config_loader import SpriteConfigLoader
    from core.sprite_library import SpriteLibrary

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
        preview_generator: Preview image generation service (created on first access)
        log_watcher: Mesen2 log file watcher for sprite offset discovery (created on first access)
        sprite_library: Persistent storage for discovered sprites (created on first access)
        hal_compressor: HAL compression/decompression service (created on first access)
        sprite_config_loader: Sprite configuration loader (created on first access)
        default_palette_loader: Default palette loader (created on first access)
    """

    configuration_service: ConfigurationService
    application_state_manager: ApplicationStateManager
    sprite_preset_manager: SpritePresetManager
    core_operations_manager: CoreOperationsManager

    @property
    def session_manager(self) -> ApplicationStateManager:
        """Backward compatibility for session_manager (delegates to application_state_manager)."""
        return self.application_state_manager

    # Lazy-initialized (created on first access)
    _rom_cache: ROMCache | None = field(default=None, repr=False)
    _rom_extractor: ROMExtractor | None = field(default=None, repr=False)
    _preview_generator: PreviewGenerator | None = field(default=None, repr=False)
    _log_watcher: LogWatcher | None = field(default=None, repr=False)
    _sprite_library: SpriteLibrary | None = field(default=None, repr=False)
    _hal_compressor: HALCompressor | None = field(default=None, repr=False)
    _sprite_config_loader: SpriteConfigLoader | None = field(default=None, repr=False)
    _default_palette_loader: DefaultPaletteLoader | None = field(default=None, repr=False)

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
        """Lazy-initialize ROMExtractor on first access.

        Injects shared HALCompressor, SpriteConfigLoader, and DefaultPaletteLoader.
        """
        with self._lazy_lock:
            if self._rom_extractor is None:
                from core.rom_extractor import ROMExtractor

                self._rom_extractor = ROMExtractor(
                    rom_cache=self.rom_cache,
                    hal_compressor=self.hal_compressor,
                    sprite_config_loader=self.sprite_config_loader,
                    default_palette_loader=self.default_palette_loader,
                )
                logger.debug("Created ROMExtractor via lazy initialization")
            return self._rom_extractor

    @property
    def preview_generator(self) -> PreviewGenerator:
        """Lazy-initialize PreviewGenerator on first access.

        Automatically configures the generator with required managers.
        """
        with self._lazy_lock:
            if self._preview_generator is None:
                from core.services.preview_generator import PreviewGenerator

                self._preview_generator = PreviewGenerator()
                # Auto-configure with available managers
                self._preview_generator.set_managers(
                    extraction_manager=self.core_operations_manager,
                    rom_extractor=self.rom_extractor,
                )
                logger.debug("Created PreviewGenerator via lazy initialization")
            return self._preview_generator

    @property
    def log_watcher(self) -> LogWatcher:
        """Lazy-initialize LogWatcher on first access.

        Watches Mesen2's sprite_rom_finder.log for discovered ROM offsets.
        """
        with self._lazy_lock:
            if self._log_watcher is None:
                from core.mesen_integration.log_watcher import LogWatcher

                self._log_watcher = LogWatcher()
                logger.debug("Created LogWatcher via lazy initialization")
            return self._log_watcher

    @property
    def sprite_library(self) -> SpriteLibrary:
        """Lazy-initialize SpriteLibrary on first access.

        Provides persistent storage for discovered sprites.
        """
        with self._lazy_lock:
            if self._sprite_library is None:
                from core.sprite_library import SpriteLibrary

                self._sprite_library = SpriteLibrary()
                self._sprite_library.load()
                logger.debug("Created SpriteLibrary via lazy initialization")
            return self._sprite_library

    @property
    def hal_compressor(self) -> HALCompressor:
        """Lazy-initialize HALCompressor on first access.

        Provides HAL compression/decompression for sprite data.
        Shared across ROMExtractor, ROMInjector, and other components.
        """
        with self._lazy_lock:
            if self._hal_compressor is None:
                from core.hal_compression import HALCompressor

                self._hal_compressor = HALCompressor()
                logger.debug("Created HALCompressor via lazy initialization")
            return self._hal_compressor

    @property
    def sprite_config_loader(self) -> SpriteConfigLoader:
        """Lazy-initialize SpriteConfigLoader on first access.

        Loads sprite configuration from config/sprite_locations.json.
        Shared across ROMExtractor and ROMInjector.
        """
        with self._lazy_lock:
            if self._sprite_config_loader is None:
                from core.sprite_config_loader import SpriteConfigLoader

                self._sprite_config_loader = SpriteConfigLoader()
                logger.debug("Created SpriteConfigLoader via lazy initialization")
            return self._sprite_config_loader

    @property
    def default_palette_loader(self) -> DefaultPaletteLoader:
        """Lazy-initialize DefaultPaletteLoader on first access.

        Loads default palettes from config/default_palettes.json.
        Shared across ROMExtractor, EditingController, and other UI components.
        """
        with self._lazy_lock:
            if self._default_palette_loader is None:
                from core.default_palette_loader import DefaultPaletteLoader

                self._default_palette_loader = DefaultPaletteLoader()
                logger.debug("Created DefaultPaletteLoader via lazy initialization")
            return self._default_palette_loader

    def cleanup(self) -> None:
        """Cleanup all managers in reverse initialization order."""
        logger.info("Cleaning up AppContext...")

        # Cleanup lazy services first (they depend on managers)
        if self._sprite_library is not None:
            try:
                self._sprite_library.cleanup()
                logger.debug("Cleaned up SpriteLibrary")
            except Exception:
                logger.warning("Error cleaning up SpriteLibrary", exc_info=True)

        if self._log_watcher is not None:
            try:
                self._log_watcher.cleanup()
                logger.debug("Cleaned up LogWatcher")
            except Exception:
                logger.warning("Error cleaning up LogWatcher", exc_info=True)

        if self._preview_generator is not None:
            try:
                self._preview_generator.cleanup()
                logger.debug("Cleaned up PreviewGenerator")
            except Exception:
                logger.warning("Error cleaning up PreviewGenerator", exc_info=True)

        # Clear shared stateless services (no cleanup needed, just clear references)
        self._hal_compressor = None
        self._sprite_config_loader = None
        self._default_palette_loader = None
        logger.debug("Cleared shared service references")

        # Cleanup managers in reverse order of initialization
        for mgr in [
            self.core_operations_manager,
            self.sprite_preset_manager,
            self.application_state_manager,
        ]:
            try:
                mgr.cleanup()
                logger.debug("Cleaned up %s", type(mgr).__name__)
            except Exception:
                logger.warning("Error cleaning up %s", type(mgr).__name__, exc_info=True)

        logger.info("AppContext cleanup complete")


# Global context (for transition period and simplified access)
_app_context: AppContext | None = None
_context_lock = threading.RLock()
_cleanup_registered = False


def get_app_context() -> AppContext:
    """Get the global app context.

    Raises:
        RuntimeError: If AppContext was not initialized via create_app_context()
    """
    if _app_context is None:
        raise RuntimeError("AppContext not initialized. Call create_app_context() first.")
    return _app_context


def get_app_context_optional() -> AppContext | None:
    """Get the global app context if initialized, otherwise None."""
    return _app_context


def create_app_context(
    app_name: str = "SpritePal",
    settings_path: Path | None = None,
    configuration_service: ConfigurationService | None = None,
    qt_parent: QObject | None = None,
    *,
    hal_compressor: HALCompressor | None = None,
    sprite_config_loader: SpriteConfigLoader | None = None,
    default_palette_loader: DefaultPaletteLoader | None = None,
) -> AppContext:
    """
    Create and set the global AppContext.

    This is the new explicit initialization, replacing initialize_managers().

    ## Initialization Order (IMPORTANT)

    Managers must be created in this exact order due to dependencies:

    1. **ConfigurationService** - Provides paths for settings, cache, and logs.
       Must be first because all other components use it for path resolution.

    2. **ApplicationStateManager** - Loads settings and manages workflow state.
       Depends on ConfigurationService for settings file location.

    3. **SpritePresetManager** - Manages sprite preset configurations.
       Depends on ConfigurationService for preset file location.

    4. **ROMCache** - Caches extracted ROM data to avoid repeated disk reads.
       Depends on ApplicationStateManager for cache settings (enabled, location).

    5. **ROMExtractor** - Extracts sprite data from ROM files.
       Depends on ROMCache to check for cached data before extraction.

    6. **CoreOperationsManager** - Coordinates extraction and injection operations.
       Depends on all of the above for its operations.

    Changing this order will cause silent failures or runtime errors.
    Do not instantiate managers directly - always use this function.

    Args:
        app_name: Application name for settings
        settings_path: Optional custom path for settings file (for testing)
        configuration_service: Optional pre-created ConfigurationService
        qt_parent: Optional Qt parent for managers (uses QApplication.instance() if None)
        hal_compressor: Optional pre-created HALCompressor (for session-scoped caching in tests)
        sprite_config_loader: Optional pre-created SpriteConfigLoader (for session-scoped caching)
        default_palette_loader: Optional pre-created DefaultPaletteLoader (for session-scoped caching)

    Returns:
        The created AppContext
    """
    global _app_context, _cleanup_registered

    with _context_lock:
        if _app_context is not None:
            logger.debug("AppContext already exists, returning existing instance")
            return _app_context

        logger.info("Creating AppContext...")

        from PySide6.QtCore import QCoreApplication
        from PySide6.QtWidgets import QApplication

        from core.configuration_service import ConfigurationService as ConfigService
        from core.managers.application_state_manager import ApplicationStateManager
        from core.managers.core_operations_manager import CoreOperationsManager
        from core.managers.sprite_preset_manager import SpritePresetManager

        # Use QApplication instance if no parent provided
        if qt_parent is None:
            qt_parent = QApplication.instance()
            if qt_parent is None:
                logger.warning("No QApplication instance found - managers will have no Qt parent")

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

        # 4. Shared stateless services are now lazy-initialized
        # They can be pre-created and passed in for session-scoped caching in tests,
        # otherwise they'll be created on first use by ROMExtractor or AppContext properties.
        # This defers HALCompressor tool discovery (~200-500ms) until actually needed.
        if hal_compressor is not None:
            logger.debug("HALCompressor provided (cached)")
        if sprite_config_loader is not None:
            logger.debug("SpriteConfigLoader provided (cached)")
        if default_palette_loader is not None:
            logger.debug("DefaultPaletteLoader provided (cached)")

        # 5. Create ROMCache and ROMExtractor (needed by CoreOperationsManager)
        from core.rom_extractor import ROMExtractor
        from core.services.rom_cache import ROMCache

        rom_cache = ROMCache(state_manager=state_mgr)
        logger.debug("ROMCache created")

        rom_extractor = ROMExtractor(
            rom_cache=rom_cache,
            hal_compressor=hal_compressor,
            sprite_config_loader=sprite_config_loader,
            default_palette_loader=default_palette_loader,
        )
        logger.debug("ROMExtractor created")

        # 6. CoreOperationsManager (with explicit dependencies)
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
            _hal_compressor=hal_compressor,
            _sprite_config_loader=sprite_config_loader,
            _default_palette_loader=default_palette_loader,
        )

        # Register cleanup hooks
        if not _cleanup_registered:
            qt_app = qt_parent if isinstance(qt_parent, QCoreApplication) else None
            if qt_app is not None:
                qt_app.aboutToQuit.connect(_cleanup_app_context)
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


@contextlib.contextmanager
def suspend_app_context() -> Generator[None, None, None]:
    """Temporarily suspend the global app context.

    This context manager temporarily sets the global context to None
    without calling cleanup on it. The context is restored when the
    context manager exits.

    This is useful for testing scenarios where we need to test behavior
    when no context is initialized, but we don't want to destroy a
    session-scoped context that should persist across tests.

    WARNING: This is for test infrastructure only.
    Do not use in production code.

    Usage:
        with suspend_app_context():
            # _app_context is None here
            assert not is_context_initialized()
        # _app_context is restored here
    """
    global _app_context, _cleanup_registered

    saved_context = None
    saved_cleanup_registered = False

    with _context_lock:
        saved_context = _app_context
        saved_cleanup_registered = _cleanup_registered
        _app_context = None
        _cleanup_registered = False
        logger.debug("AppContext suspended (not cleaned up)")

    try:
        yield
    finally:
        # Clean up any context that was created during suspension
        with _context_lock:
            if _app_context is not None:
                _app_context.cleanup()  # pyright: ignore[reportUnreachable] - can be set during yield
            # Restore the original context
            _app_context = saved_context
            _cleanup_registered = saved_cleanup_registered
            logger.debug("AppContext restored from suspension")
