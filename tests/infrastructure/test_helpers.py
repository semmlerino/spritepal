# pyright: recommended
"""
Simple helper functions for common test needs.

These replace the factory pattern with straightforward functions.
All functions take explicit dependencies (AppContext) - no global state.

Usage:
    def test_extraction(app_context, isolated_data_repository):
        params = isolated_data_repository.get_vram_extraction_data("small")
        worker = create_extraction_worker(app_context, params)
        with qtbot.waitSignal(worker.finished):
            worker.start()
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.app_context import AppContext
    from core.tile_renderer import TileRenderer
    from core.workers import ROMExtractionWorker, VRAMExtractionWorker, VRAMInjectionWorker
    from ui.main_window import MainWindow

    from .data_repository import DataRepository


def create_main_window(context: AppContext) -> MainWindow:
    """
    Create a MainWindow with proper dependencies from AppContext.

    Args:
        context: The test AppContext

    Returns:
        MainWindow instance ready for testing
    """
    from ui.main_window import MainWindow

    return MainWindow(
        settings_manager=context.application_state_manager,
        rom_cache=context.rom_cache,
        session_manager=context.application_state_manager,  # type: ignore[arg-type]
    )


def create_extraction_worker(
    context: AppContext,
    params: dict[str, Any] | None = None,
    worker_type: str = "vram",
    *,
    data_repository: DataRepository | None = None,
) -> VRAMExtractionWorker | ROMExtractionWorker:
    """
    Create an extraction worker with proper manager dependencies.

    Args:
        context: The test AppContext
        params: Optional extraction parameters (defaults to small test data)
        worker_type: "vram" or "rom"
        data_repository: Optional DataRepository for default params (preferred over singleton)

    Returns:
        Extraction worker instance
    """
    from core.workers import ROMExtractionWorker, VRAMExtractionWorker

    if params is None:
        if data_repository is not None:
            data_repo = data_repository
        else:
            # Deprecated fallback to singleton
            from .data_repository import get_test_data_repository

            warnings.warn(
                "Calling create_extraction_worker without params or data_repository "
                "uses deprecated singleton. Pass data_repository=isolated_data_repository.",
                DeprecationWarning,
                stacklevel=2,
            )
            data_repo = get_test_data_repository()

        if worker_type == "vram":
            params = data_repo.get_vram_extraction_data("small")
        else:
            params = data_repo.get_rom_extraction_data("small")

    extraction_manager = context.core_operations_manager

    if worker_type == "vram":
        return VRAMExtractionWorker(params, extraction_manager=extraction_manager)
    else:
        return ROMExtractionWorker(params, extraction_manager=extraction_manager)


def create_injection_worker(
    context: AppContext,
    params: dict[str, Any] | None = None,
    *,
    data_repository: DataRepository | None = None,
) -> VRAMInjectionWorker:
    """
    Create an injection worker with proper manager dependencies.

    Args:
        context: The test AppContext
        params: Optional injection parameters (defaults to small test data)
        data_repository: Optional DataRepository for default params (preferred over singleton)

    Returns:
        VRAMInjectionWorker instance
    """
    from core.workers import VRAMInjectionWorker

    if params is None:
        if data_repository is not None:
            data_repo = data_repository
        else:
            # Deprecated fallback to singleton
            from .data_repository import get_test_data_repository

            warnings.warn(
                "Calling create_injection_worker without params or data_repository "
                "uses deprecated singleton. Pass data_repository=isolated_data_repository.",
                DeprecationWarning,
                stacklevel=2,
            )
            data_repo = get_test_data_repository()

        params = data_repo.get_injection_data("small")

    injection_manager = context.core_operations_manager

    return VRAMInjectionWorker(params, injection_manager=injection_manager)


def create_tile_renderer() -> TileRenderer:
    """
    Create a TileRenderer for testing.

    Returns:
        TileRenderer instance with default palettes
    """
    from core.tile_renderer import TileRenderer

    return TileRenderer()
