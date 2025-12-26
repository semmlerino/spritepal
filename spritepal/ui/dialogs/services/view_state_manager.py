"""
View State Manager

Handles window state management for ManualOffsetDialog including fullscreen mode
and position persistence. Extracted from ManualOffsetDialog to separate window
management concerns from business logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from core.managers.application_state_manager import ApplicationStateManager
else:
    from PySide6.QtWidgets import QWidget

from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import QGuiApplication

from utils.logging_config import get_logger

logger = get_logger(__name__)


class ViewStateManager(QObject):
    """
    Manages window state for ManualOffsetDialog.

    Responsibilities:
    - Fullscreen mode toggle
    - Window position save/restore
    - Size constraints and parent centering
    - Window title management
    """

    # Signals for state changes
    fullscreen_toggled = Signal(bool)  # is_fullscreen
    title_changed = Signal(str)  # new_title

    def __init__(
        self,
        dialog_widget: QWidget,
        parent: QObject | None = None,
        *,
        settings_manager: ApplicationStateManager,
    ) -> None:
        super().__init__(parent)

        self.dialog_widget = dialog_widget
        self.settings_manager = settings_manager

        # Fullscreen state
        self._is_fullscreen = False
        self._normal_geometry: QRect | None = None
        self._original_window_flags = dialog_widget.windowFlags()

        # Base titles
        self._base_title = "Manual Offset Control - SpritePal"
        self._fullscreen_title = "Manual Offset Control - SpritePal (Fullscreen - F11 or Esc to exit)"

    def toggle_fullscreen(self) -> None:
        """Toggle between fullscreen and normal window mode"""
        if self._is_fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self) -> None:
        """Enter fullscreen mode"""
        if self._is_fullscreen:
            return

        # Save current geometry
        self._normal_geometry = self.dialog_widget.geometry()
        logger.debug(f"GEOMETRY: Entering fullscreen, saved normal geometry: {self._normal_geometry}")

        # Use clean window flags for true fullscreen
        self.dialog_widget.setWindowFlags(Qt.WindowType.Window)
        self.dialog_widget.showFullScreen()

        self._is_fullscreen = True
        self.dialog_widget.setWindowTitle(self._fullscreen_title)

        self.fullscreen_toggled.emit(True)
        self.title_changed.emit(self._fullscreen_title)
        logger.debug(f"GEOMETRY: Entered fullscreen mode, new geometry: {self.dialog_widget.geometry()}")

    def _exit_fullscreen(self) -> None:
        """Exit fullscreen mode"""
        if not self._is_fullscreen:
            return

        logger.debug(f"GEOMETRY: Exiting fullscreen, current geometry: {self.dialog_widget.geometry()}")

        # Restore original window flags and geometry
        self.dialog_widget.setWindowFlags(self._original_window_flags)
        self.dialog_widget.showNormal()

        if self._normal_geometry is not None:
            self.dialog_widget.setGeometry(self._normal_geometry)
            logger.debug(f"GEOMETRY: Restored normal geometry: {self._normal_geometry}")

        self._is_fullscreen = False
        self.dialog_widget.setWindowTitle(self._base_title)

        self.fullscreen_toggled.emit(False)
        self.title_changed.emit(self._base_title)
        logger.debug(f"GEOMETRY: Exited fullscreen mode, final geometry: {self.dialog_widget.geometry()}")

    def is_fullscreen(self) -> bool:
        """Check if currently in fullscreen mode"""
        return self._is_fullscreen

    def update_title_with_rom(self, rom_path: str) -> None:
        """Update window title with ROM name"""
        if rom_path:
            rom_name = Path(rom_path).name
            title = f"Manual Offset Control - {rom_name}"
        else:
            title = self._base_title

        self._base_title = title

        # Update current title if not in fullscreen
        if not self._is_fullscreen:
            self.dialog_widget.setWindowTitle(title)
            self.title_changed.emit(title)

    def _is_position_valid(self, x: int, y: int, width: int, height: int) -> bool:
        """Validate that window position and size are reasonable and safe to save"""
        # Check for negative coordinates
        if x < 0 or y < 0:
            logger.debug(f"Invalid position: negative coordinates x={x}, y={y}")
            return False

        # Check for unreasonably large coordinates (likely corruption)
        if x > 10000 or y > 10000:
            logger.debug(f"Invalid position: excessive coordinates x={x}, y={y}")
            return False

        # Check for unreasonably large dimensions
        if width > 5000 or height > 5000:
            logger.debug(f"Invalid size: excessive dimensions {width}x{height}")
            return False

        # Check for minimum reasonable size
        if width < 200 or height < 150:
            logger.debug(f"Invalid size: too small {width}x{height}")
            return False

        # Ensure position is actually visible on screen
        if not self._is_position_on_screen(x, y, width, height):
            logger.debug(f"Invalid position: off-screen {x},{y} {width}x{height}")
            return False

        return True

    def save_window_position(self) -> None:
        """Save the current window position to settings with validation"""
        if self._is_fullscreen:
            # Don't save position in fullscreen mode
            return

        try:
            pos = self.dialog_widget.pos()
            size = self.dialog_widget.size()
            x, y = pos.x(), pos.y()
            width, height = size.width(), size.height()

            # Validate position before saving
            if not self._is_position_valid(x, y, width, height):
                logger.warning(f"Refusing to save invalid window position: {x},{y} {width}x{height}")
                return

            settings_manager = self.settings_manager
            settings_manager.set("manual_offset_dialog", "x", x)
            settings_manager.set("manual_offset_dialog", "y", y)
            settings_manager.set("manual_offset_dialog", "width", width)
            settings_manager.set("manual_offset_dialog", "height", height)

            logger.debug(f"Saved valid window position: {x},{y} size: {width}x{height}")
        except Exception as e:
            logger.warning(f"Failed to save window position: {e}")

    def _is_position_on_screen(self, x: int, y: int, width: int, height: int) -> bool:
        """Check if a window position is reasonably visible on any screen"""
        window_rect = QRect(x, y, width, height)

        # Check if window intersects with any available screen
        for screen in QGuiApplication.screens():
            screen_geometry = screen.availableGeometry()
            if window_rect.intersects(screen_geometry):
                intersection = window_rect.intersected(screen_geometry)

                # Require at least 80% of the dialog to be visible to avoid "too high" positioning
                required_width = int(width * 0.8)
                required_height = int(height * 0.8)

                if intersection.width() >= required_width and intersection.height() >= required_height:
                    # Additional check: ensure the dialog isn't positioned too high
                    # The top of the dialog should be at least 50px from the top of screen
                    if y >= screen_geometry.y() + 50:
                        return True
                    logger.debug(f"Dialog positioned too high: y={y}, screen_top={screen_geometry.y()}")

        return False

    def restore_window_position(self) -> bool:
        """
        Restore window position from settings with comprehensive validation.

        Uses the robust _is_position_valid() method to ensure only safe positions
        are restored, preventing corruption issues.

        Returns:
            True if position was restored, False otherwise
        """
        try:
            settings_manager = self.settings_manager

            # Get saved position values
            x = settings_manager.get("manual_offset_dialog", "x", None)
            y = settings_manager.get("manual_offset_dialog", "y", None)
            width = settings_manager.get("manual_offset_dialog", "width", None)
            height = settings_manager.get("manual_offset_dialog", "height", None)

            # Require all values to be present
            if any(val is None for val in [x, y, width, height]):
                logger.debug("Incomplete saved position data - using safe positioning")
                return False

            # Convert to integers and validate
            try:
                x, y, width, height = int(x), int(y), int(width), int(height)  # type: ignore[arg-type]
            except (ValueError, TypeError):
                logger.debug("Invalid saved position data types - using safe positioning")
                return False

            # Use comprehensive validation
            if not self._is_position_valid(x, y, width, height):
                logger.debug(f"Saved position failed validation: {x},{y} {width}x{height} - using safe positioning")
                return False

            # Position is valid - restore it
            self.dialog_widget.move(x, y)
            # Don't restore size for manual offset dialog - use dialog's preferred size
            if "Manual Offset" not in self.dialog_widget.windowTitle():
                self.dialog_widget.resize(width, height)
                logger.debug(f"Successfully restored window position: {x},{y} size: {width}x{height}")
            else:
                logger.debug(f"Successfully restored window position: {x},{y} (keeping dialog's preferred size)")
            return True

        except Exception as e:
            logger.warning(f"Error restoring window position: {e} - using safe positioning")
            return False

    def center_on_screen(self) -> None:
        """Center the dialog on the primary screen as a safe fallback"""
        try:
            primary_screen = QGuiApplication.primaryScreen()
            if primary_screen:
                screen_geometry = primary_screen.availableGeometry()
                dialog_width = self.dialog_widget.width()
                dialog_height = self.dialog_widget.height()

                # Check if dialog is larger than available screen space
                if dialog_width > screen_geometry.width() or dialog_height > screen_geometry.height():
                    # Resize dialog to fit screen with some margin
                    max_width = max(800, screen_geometry.width() - 100)  # At least 800px wide, with 100px margin
                    max_height = max(600, screen_geometry.height() - 100)  # At least 600px high, with 100px margin

                    new_width = min(dialog_width, max_width)
                    new_height = min(dialog_height, max_height)

                    self.dialog_widget.resize(new_width, new_height)
                    logger.debug(f"Resized dialog to fit screen: {new_width}x{new_height}")

                    # Update dimensions after resize
                    dialog_width = new_width
                    dialog_height = new_height

                # Calculate center position
                center_x = screen_geometry.x() + (screen_geometry.width() - dialog_width) // 2
                center_y = screen_geometry.y() + (screen_geometry.height() - dialog_height) // 2

                # Ensure dialog stays within screen bounds with extra safety margins
                margin = 50  # Extra safety margin
                center_x = max(
                    screen_geometry.x() + margin,
                    min(center_x, screen_geometry.x() + screen_geometry.width() - dialog_width - margin),
                )
                center_y = max(
                    screen_geometry.y() + margin,
                    min(center_y, screen_geometry.y() + screen_geometry.height() - dialog_height - margin),
                )

                # Extra safety: never allow negative or zero positions
                center_x = max(100, center_x)
                center_y = max(100, center_y)

                self.dialog_widget.move(center_x, center_y)
                logger.debug(
                    f"GEOMETRY: Centered dialog on screen at {center_x},{center_y} (screen: {screen_geometry.width()}x{screen_geometry.height()})"
                )
                logger.debug(f"GEOMETRY: Final centered geometry: {self.dialog_widget.geometry()}")
            else:
                # Last resort - move to top-left with small offset
                self.dialog_widget.move(100, 100)
                logger.debug("No screen found, positioned dialog at 100,100")
        except Exception as e:
            logger.warning(f"Failed to center on screen: {e}")
            # Ultimate fallback
            self.dialog_widget.move(100, 100)

    def center_on_parent(self) -> bool:
        """
        Center the dialog on its parent window.

        Returns:
            True if successfully centered on parent, False otherwise
        """
        if not self.dialog_widget.parent():
            return False

        try:
            parent = self.dialog_widget.parent()
            # QObject.window() returns QWidget for QWidget instances
            parent_window = parent.window()  # type: ignore[attr-defined]
            if not parent_window or not parent_window.isVisible():
                return False

            parent_rect = parent_window.frameGeometry()

            # Validate parent geometry is reasonable
            if parent_rect.width() <= 0 or parent_rect.height() <= 0:
                return False

            center_x = parent_rect.x() + (parent_rect.width() - self.dialog_widget.width()) // 2
            center_y = parent_rect.y() + (parent_rect.height() - self.dialog_widget.height()) // 2

            # Validate the calculated position is on screen
            if self._is_position_on_screen(center_x, center_y, self.dialog_widget.width(), self.dialog_widget.height()):
                self.dialog_widget.move(center_x, center_y)
                logger.debug(f"GEOMETRY: Centered dialog on parent at {center_x},{center_y}")
                logger.debug(f"GEOMETRY: Final parent-centered geometry: {self.dialog_widget.geometry()}")
                return True
            logger.debug(f"GEOMETRY: Calculated parent center position {center_x},{center_y} is off-screen")
            return False

        except Exception as e:
            logger.warning(f"Failed to center on parent: {e}")
            return False

    def handle_show_event(self) -> None:
        """Handle dialog show event with robust positioning fallbacks"""
        # Try to restore saved position first (with comprehensive validation)
        if self.restore_window_position():
            return

        # Try to center on parent window
        if self.center_on_parent():
            return

        # Final fallback - center on screen (will always work)
        self.center_on_screen()

    def handle_hide_event(self) -> None:
        """Handle dialog hide event - save current position"""
        self.save_window_position()

    def reset_to_safe_position(self) -> None:
        """Reset dialog to a safe visible position - useful for debugging positioning issues"""
        logger.info("Resetting dialog to safe position")
        self.center_on_screen()

    def handle_escape_key(self) -> bool:
        """
        Handle escape key press.

        Returns:
            True if the key was handled (fullscreen exit), False otherwise
        """
        if self._is_fullscreen:
            self.toggle_fullscreen()
            return True
        return False
