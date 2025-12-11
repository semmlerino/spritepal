"""
Worker Coordinator Component

Manages SimplePreviewCoordinator and all workers with thread safety.
Enhanced for superior visual design in composed implementation.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QMutex, QMutexLocker
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from core.managers.extraction_manager import ExtractionManager
    from ui.common.simple_preview_coordinator import SimplePreviewCoordinator
    from ui.components.visualization.rom_map_widget import ROMMapWidget
    from ui.widgets.sprite_preview_widget import SpritePreviewWidget

from utils.logging_config import get_logger

logger = get_logger(__name__)

class WorkerCoordinatorComponent:
    """
    Manages worker threads and preview coordination for the Manual Offset Dialog.

    Handles SimplePreviewCoordinator, preview workers, search workers, and
    ensures thread-safe operations.
    """

    def __init__(self, dialog: Any) -> None:
        """Initialize the worker coordinator."""
        self.dialog = dialog
        self._mutex = QMutex()
        self.preview_widget: SpritePreviewWidget | None = None
        self.mini_rom_map: ROMMapWidget | None = None
        self._preview_coordinator: SimplePreviewCoordinator | None = None
        self.preview_worker: Any | None = None
        self.search_worker: Any | None = None

    def create_right_panel(self) -> QWidget:
        """Create the right panel with preview widget."""
        with QMutexLocker(self._mutex):
            panel = QWidget()
            layout = QVBoxLayout(panel)

            # Apply enhanced layout for composed implementation
            if self._is_composed_implementation():
                # Enhanced spacing for better visual design
                layout.setContentsMargins(16, 16, 16, 16)  # More generous margins
                layout.setSpacing(12)                      # Better separation

                # Apply modern styling to panel
                panel.setStyleSheet("""
                    QWidget {
                        background-color: #fcfcfc;
                        color: #000000;
                        border-radius: 8px;
                    }
                """)
            else:
                # Legacy layout
                layout.setContentsMargins(6, 6, 6, 6)
                layout.setSpacing(6)

            # Create preview widget
            try:
                from ui.components.visualization.rom_map_widget import ROMMapWidget
                from ui.widgets.sprite_preview_widget import SpritePreviewWidget

                # Create preview widget (main component)
                self.preview_widget = SpritePreviewWidget()
                layout.addWidget(self.preview_widget, 1)  # Give it stretch to expand

                # Add mini ROM map widget (like original)
                try:
                    self.mini_rom_map = ROMMapWidget()
                    self.mini_rom_map.setMaximumHeight(50)  # Keep it small
                    layout.addWidget(self.mini_rom_map, 0)  # No stretch - fixed height
                    logger.debug("Added mini ROM map widget")
                except (ImportError, RuntimeError) as e:
                    logger.warning(f"Could not create ROM map widget: {e}")

            except ImportError as e:
                logger.warning(f"SpritePreviewWidget not found: {e}, using placeholder")
                self.preview_widget = QLabel("Preview Widget Not Available")  # type: ignore[assignment]
                if self.preview_widget:

                    layout.addWidget(self.preview_widget)

                else:

                    layout.addWidget(QLabel("Preview not available"))

            return panel

    def set_rom_data(self, rom_path: str, rom_size: int, extraction_manager: ExtractionManager) -> None:
        """Update worker coordinator with ROM data."""
        with QMutexLocker(self._mutex):
            # Set up preview coordinator with ROM data
            try:
                from ui.common.simple_preview_coordinator import (
                    SimplePreviewCoordinator,
                )
                from core.di_container import inject
                from core.protocols.manager_protocols import ROMCacheProtocol

                if not self._preview_coordinator:
                    self._preview_coordinator = SimplePreviewCoordinator(
                        self.dialog,
                        rom_cache=inject(ROMCacheProtocol)
                    )

                # Update preview widget if available
                if self.preview_widget and hasattr(self.preview_widget, 'set_rom_data'):
                    rom_extractor = extraction_manager.get_rom_extractor()
                    self.preview_widget.set_rom_data(rom_path, rom_extractor)  # type: ignore[attr-defined]

                # Update mini ROM map if available
                if self.mini_rom_map and hasattr(self.mini_rom_map, 'set_rom_data'):
                    self.mini_rom_map.set_rom_data(rom_path, rom_size)  # type: ignore[attr-defined]

            except ImportError as e:
                logger.warning(f"SimplePreviewCoordinator not available: {e}")
            except (AttributeError, RuntimeError) as e:
                logger.warning(f"Error setting up preview coordinator: {e}")

    def cleanup_workers(self) -> None:
        """Clean up all worker threads."""
        with QMutexLocker(self._mutex):
            logger.debug("Cleaning up workers")

            # Clean up preview coordinator
            if self._preview_coordinator and hasattr(self._preview_coordinator, 'cleanup'):
                try:
                    self._preview_coordinator.cleanup()
                except (RuntimeError, AttributeError) as e:
                    logger.debug(f"Error cleaning up preview coordinator: {e}")

            # Clean up individual workers
            if self.preview_worker:
                try:
                    from ui.common import WorkerManager
                    WorkerManager.cleanup_worker(self.preview_worker, timeout=2000)
                except (ImportError, RuntimeError, AttributeError) as e:
                    logger.debug(f"Error cleaning up preview worker: {e}")
                finally:
                    self.preview_worker = None

            if self.search_worker:
                try:
                    from ui.common import WorkerManager
                    WorkerManager.cleanup_worker(self.search_worker, timeout=2000)
                except (ImportError, RuntimeError, AttributeError) as e:
                    logger.debug(f"Error cleaning up search worker: {e}")
                finally:
                    self.search_worker = None

    def cleanup(self) -> None:
        """Clean up all resources."""
        self.cleanup_workers()
        with QMutexLocker(self._mutex):
            self._preview_coordinator = None

    def _is_composed_implementation(self) -> bool:
        """Check if we're using composed implementation."""
        flag_value = os.environ.get('SPRITEPAL_USE_COMPOSED_DIALOGS', '0').lower()
        return flag_value in ('1', 'true', 'yes', 'on')
