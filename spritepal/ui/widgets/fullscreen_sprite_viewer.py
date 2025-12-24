"""
Fullscreen sprite viewer widget for SpritePal.
Provides fullscreen display of sprites with navigation controls.

FULLSCREEN IMPLEMENTATION NOTES:
===============================

This implementation uses a multi-strategy approach to ensure reliable fullscreen
behavior across different platforms and window managers:

1. FIXED ISSUES:
   - Removed manual geometry setting that conflicted with showFullScreen()
   - Cleaned up window flags to avoid window manager conflicts
   - Added platform-specific fallback strategies
   - Enhanced debugging for troubleshooting

2. STRATEGIES USED:
   - Primary: Standard Qt showFullScreen() (recommended)
   - Fallback 1: setWindowState(WindowFullScreen)
   - Fallback 2: Manual geometry + show() for problematic platforms
   - Recovery: Platform-specific recovery attempts

3. KEY PRINCIPLES:
   - Let Qt handle geometry when using showFullScreen()
   - Use minimal window flags to avoid conflicts
   - Create without parent to avoid fullscreen constraints
   - Comprehensive logging for debugging platform issues

4. PLATFORM HANDLING:
   - Windows: Uses window state transitions for recovery
   - Linux: Uses show state cycling for recovery
   - Generic: Fallback approach for other platforms

This should resolve the "partial screen coverage" issue that was caused by
manual geometry setting interfering with Qt's internal fullscreen logic.
"""

from __future__ import annotations

import platform
import weakref
from typing import TYPE_CHECKING, Any, override

if TYPE_CHECKING:
    from core.protocols.manager_protocols import ROMExtractorProtocol

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QFont, QGuiApplication, QKeyEvent, QMouseEvent, QPixmap, QScreen, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.common.spacing_constants import FULLSCREEN_MARGINS
from ui.styles.theme import COLORS
from utils.logging_config import get_logger

logger = get_logger(__name__)

class FullscreenSpriteViewer(QWidget):
    """Fullscreen sprite viewer with keyboard navigation."""

    # Signals
    sprite_changed = Signal(int)  # Emits current sprite offset
    viewer_closed = Signal()  # Emits when viewer is closed

    def __init__(self, parent: QWidget | None = None):
        """
        Initialize the fullscreen sprite viewer.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        # Data
        self.sprites_data: list[dict[str, Any]] = []  # pyright: ignore[reportExplicitAny] - sprite metadata
        self.current_index: int = 0
        self.rom_path: str | None = None
        self.rom_extractor: ROMExtractorProtocol | None = None

        # UI Components
        self.sprite_label: QLabel | None = None
        self.info_overlay: QLabel | None = None
        self.status_label: QLabel | None = None

        # Settings
        self.show_info = True
        self.smooth_scaling = True

        # Timer for smooth transitions
        self.transition_timer = QTimer()
        self.transition_timer.setSingleShot(True)
        self.transition_timer.timeout.connect(self._update_sprite_display)

        self._setup_ui()
        self._setup_fullscreen()

        # Set focus to receive keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _setup_ui(self):
        """Setup the fullscreen viewer UI."""
        # Main layout - center everything
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(
            FULLSCREEN_MARGINS, FULLSCREEN_MARGINS,
            FULLSCREEN_MARGINS, FULLSCREEN_MARGINS
        )
        main_layout.setSpacing(0)

        # Sprite display area (centered)
        sprite_container = QHBoxLayout()
        sprite_container.addStretch(1)

        self.sprite_label = QLabel()
        self.sprite_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.sprite_label:
            self.sprite_label.setStyleSheet(f"""
            QLabel {{
                background-color: transparent;
                border: 2px solid {COLORS["border"]};
                border-radius: 8px;
            }}
        """)
        self.sprite_label.setMinimumSize(200, 200)

        sprite_container.addWidget(self.sprite_label)
        sprite_container.addStretch(1)

        # Add sprite container with stretch to center vertically
        main_layout.addStretch(1)
        main_layout.addLayout(sprite_container)

        # Info overlay (bottom area)
        self.info_overlay = QLabel()
        self.info_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.info_overlay:
            self.info_overlay.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(0, 0, 0, 180);
                color: {COLORS["text_primary"]};
                padding: 15px 30px;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }}
        """)
        self.info_overlay.hide()  # Initially hidden

        # Status bar (top area for navigation hints)
        self.status_label = QLabel("← → Navigate • ESC Exit • I Toggle Info")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(12)
        self.status_label.setFont(font)
        if self.status_label:
            self.status_label.setStyleSheet(f"""
            QLabel {{
                background-color: rgba(0, 0, 0, 150);
                color: {COLORS["text_secondary"]};
                padding: 10px 20px;
                border-radius: 6px;
            }}
        """)

        # Add status at top
        status_container = QHBoxLayout()
        status_container.addStretch(1)
        status_container.addWidget(self.status_label)
        status_container.addStretch(1)

        main_layout.insertLayout(0, status_container)

        # Add info overlay at bottom
        info_container = QHBoxLayout()
        info_container.addStretch(1)
        info_container.addWidget(self.info_overlay)
        info_container.addStretch(1)

        main_layout.addLayout(info_container)
        main_layout.addStretch(1)

        self.setLayout(main_layout)

    def _setup_fullscreen(self):
        """Configure widget for fullscreen display."""
        # Use clean, minimal window flags to avoid conflicts with window managers
        # Removed WindowStaysOnTopHint and WindowMaximizeButtonHint that can interfere
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint
        )

        # Ensure window can expand to full screen on any monitor
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        # Dark background
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLORS["preview_background"]};
                color: {COLORS["text_primary"]};
            }}
        """)

        # Set cursor to hidden after a delay - use weakref to avoid preventing GC
        self.cursor_timer = QTimer(self)  # Parent ensures cleanup
        self.cursor_timer.setSingleShot(True)
        weak_self = weakref.ref(self)

        def hide_cursor() -> None:
            """Hide cursor if viewer still exists."""
            viewer = weak_self()
            if viewer is not None:
                viewer.setCursor(Qt.CursorShape.BlankCursor)

        self.cursor_timer.timeout.connect(hide_cursor)
        self.cursor_timer.start(3000)

    def set_sprite_data(self, sprites_data: list[dict[str, Any]], current_offset: int,  # pyright: ignore[reportExplicitAny] - sprite metadata
                       rom_path: str, rom_extractor: ROMExtractorProtocol | None) -> bool:
        """
        Set the sprite data for the viewer.

        Args:
            sprites_data: List of sprite dictionaries
            current_offset: Offset of currently selected sprite
            rom_path: Path to ROM file
            rom_extractor: ROM extractor instance

        Returns:
            True if data was set successfully, False otherwise
        """
        if not sprites_data:
            logger.warning("No sprite data provided to fullscreen viewer")
            return False

        self.sprites_data = sprites_data
        self.rom_path = rom_path
        self.rom_extractor = rom_extractor

        # Find current sprite index
        self.current_index = 0
        for i, sprite in enumerate(sprites_data):
            if sprite.get('offset', 0) == current_offset:
                self.current_index = i
                break

        logger.info(f"Fullscreen viewer initialized with {len(sprites_data)} sprites, "
                   f"starting at index {self.current_index}")

        # Load current sprite
        self._update_sprite_display()
        self._update_info_overlay()

        return True

    def _update_sprite_display(self):
        """Update the sprite display with the current sprite."""
        if not self.sprites_data or self.current_index >= len(self.sprites_data):
            return

        current_sprite = self.sprites_data[self.current_index]
        offset = current_sprite.get('offset', 0)

        logger.debug(f"Displaying sprite at offset 0x{offset:06X}")

        # Try to get sprite pixmap from various sources
        sprite_pixmap = self._get_sprite_pixmap(offset)

        if sprite_pixmap and not sprite_pixmap.isNull():
            # Scale sprite to fit screen while maintaining aspect ratio
            scaled_pixmap = self._scale_sprite_to_screen(sprite_pixmap)
            if self.sprite_label:
                self.sprite_label.setPixmap(scaled_pixmap)
        else:
            # Show placeholder
            if self.sprite_label:
                self.sprite_label.setText(f"Loading sprite...\n0x{offset:06X}")
            if self.sprite_label:
                self.sprite_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {COLORS["background"]};
                    border: 2px solid {COLORS["border"]};
                    border-radius: 8px;
                    color: {COLORS["text_muted"]};
                    font-size: 18px;
                }}
            """)

        # Update info overlay
        self._update_info_overlay()

        # Emit signal
        self.sprite_changed.emit(offset)

    def _get_sprite_pixmap(self, offset: int) -> QPixmap | None:
        """
        Get sprite pixmap from available sources.

        Args:
            offset: Sprite offset

        Returns:
            QPixmap if found, None otherwise
        """
        # Try to get from parent gallery if available
        if self.parent():
            gallery_window = self.parent()
            if (hasattr(gallery_window, "gallery_widget") and
                    gallery_window.gallery_widget):  # type: ignore[attr-defined]
                gallery = gallery_window.gallery_widget  # type: ignore[attr-defined]

                # New API - check if gallery has get_sprite_pixmap method
                if hasattr(gallery, 'get_sprite_pixmap'):
                    return gallery.get_sprite_pixmap(offset)

                # Old API - check thumbnails dict
                if hasattr(gallery, 'thumbnails') and offset in gallery.thumbnails:
                    thumbnail = gallery.thumbnails[offset]
                    if hasattr(thumbnail, 'sprite_pixmap'):
                        return thumbnail.sprite_pixmap

        # If no pixmap found, could implement direct extraction here
        # For now, return None to show placeholder
        return None

    def _get_target_screen(self) -> QScreen:
        """
        Get the screen where this fullscreen viewer should appear.

        Returns:
            QScreen: The screen to use for fullscreen display
        """
        # Try to get screen based on parent window position
        if self.parent() and hasattr(self.parent(), 'geometry'):
            parent_center = self.parent().geometry().center()  # type: ignore[union-attr]
            logger.debug(f"Parent window center: {parent_center}")

            app = QApplication.instance()
            if app:
                for i, screen in enumerate(QGuiApplication.screens()):
                    screen_geom = screen.geometry()
                    if screen_geom.contains(parent_center):
                        logger.debug(f"Found target screen {i}: {screen_geom}")
                        return screen

                # Log all available screens for debugging
                logger.debug(f"Available screens: {[s.geometry() for s in QGuiApplication.screens()]}")

        # Fallback to primary screen
        primary_screen = QApplication.primaryScreen()
        logger.debug("Using primary screen as fallback for fullscreen viewer")
        return primary_screen

    def _scale_sprite_to_screen(self, pixmap: QPixmap) -> QPixmap:
        """
        Scale sprite to fit screen while maintaining aspect ratio.

        Args:
            pixmap: Original sprite pixmap

        Returns:
            Scaled pixmap
        """
        if not pixmap or pixmap.isNull():
            return pixmap

        # Get the correct screen and use full geometry for true fullscreen
        screen = self._get_target_screen()
        screen_rect = screen.geometry()  # Use full geometry, not availableGeometry
        max_width = screen_rect.width() - 200  # Leave 100px margin on each side
        max_height = screen_rect.height() - 200  # Leave 100px margin top/bottom

        # Scale maintaining aspect ratio
        if self.smooth_scaling:
            scaled = pixmap.scaled(
                max_width, max_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            scaled = pixmap.scaled(
                max_width, max_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )

        return scaled

    def _update_info_overlay(self):
        """Update the information overlay."""
        if not self.sprites_data or self.current_index >= len(self.sprites_data):
            return

        current_sprite = self.sprites_data[self.current_index]
        offset = current_sprite.get('offset', 0)
        name = current_sprite.get('name', f"Sprite_0x{offset:06X}")
        size = current_sprite.get('decompressed_size', 0)
        tiles = current_sprite.get('tile_count', 0)

        info_text = f"{name}\n"
        info_text += f"Offset: 0x{offset:06X}\n"
        if size > 0:
            info_text += f"Size: {size} bytes\n"
        if tiles > 0:
            info_text += f"Tiles: {tiles}\n"
        info_text += f"Sprite {self.current_index + 1} of {len(self.sprites_data)}"

        if self.info_overlay:
            self.info_overlay.setText(info_text)

        # Show/hide based on setting
        if self.info_overlay:
            if self.show_info:
                self.info_overlay.show()
            else:
                self.info_overlay.hide()

    def _navigate_to_sprite(self, direction: int):
        """
        Navigate to previous (-1) or next (1) sprite.

        Args:
            direction: -1 for previous, 1 for next
        """
        if not self.sprites_data:
            return

        # Calculate new index with wrapping
        new_index = (self.current_index + direction) % len(self.sprites_data)

        if new_index != self.current_index:
            self.current_index = new_index
            logger.debug(f"Navigated to sprite index {self.current_index}")

            # Small delay for smooth transition feel
            self.transition_timer.start(50)

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard events."""
        key = event.key()

        if key == Qt.Key.Key_Escape:
            # Close fullscreen viewer
            self.close()
        elif key == Qt.Key.Key_Left:
            # Previous sprite
            self._navigate_to_sprite(-1)
        elif key == Qt.Key.Key_Right:
            # Next sprite
            self._navigate_to_sprite(1)
        elif key == Qt.Key.Key_I:
            # Toggle info overlay
            self.show_info = not self.show_info
            self._update_info_overlay()
        elif key == Qt.Key.Key_S:
            # Toggle smooth scaling
            self.smooth_scaling = not self.smooth_scaling
            self._update_sprite_display()
        else:
            # Pass to parent
            super().keyPressEvent(event)

        event.accept()

    @override
    def showEvent(self, event: QShowEvent) -> None:
        """Handle show event with robust fullscreen implementation."""
        super().showEvent(event)

        # Apply fullscreen with multiple fallback strategies
        self._apply_fullscreen_with_fallbacks()

        # Set focus and cursor
        self.setFocus()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        # Reuse the cursor timer if it exists
        if hasattr(self, 'cursor_timer'):
            self.cursor_timer.stop()
            self.cursor_timer.start(3000)

    def _apply_fullscreen_with_fallbacks(self):
        """Apply fullscreen using multiple strategies with fallbacks."""
        target_screen = self._get_target_screen()
        screen_geometry = target_screen.geometry() if target_screen else None

        logger.info(f"Attempting fullscreen on screen: {screen_geometry}")

        # Strategy 1: Standard Qt fullscreen (recommended approach)
        success = self._try_standard_fullscreen()

        if not success:
            logger.warning("Standard fullscreen failed, trying fallback strategies")

            # Strategy 2: Use window state method
            success = self._try_window_state_fullscreen()

        if not success:
            logger.warning("Window state fullscreen failed, trying manual geometry")

            # Strategy 3: Manual geometry as last resort
            success = self._try_manual_geometry_fullscreen(screen_geometry)

        # Log final result for debugging
        if self:  # Check if object still exists
            QTimer.singleShot(100, self._log_fullscreen_result)

        if not success:
            logger.error("All fullscreen strategies failed!")

    def _try_standard_fullscreen(self) -> bool:
        """Try the standard Qt showFullScreen approach."""
        try:
            logger.debug("Trying standard showFullScreen()")
            self.showFullScreen()
            return True
        except Exception as e:
            logger.error(f"Standard fullscreen failed: {e}")
            return False

    def _try_window_state_fullscreen(self) -> bool:
        """Try using setWindowState for fullscreen."""
        try:
            logger.debug("Trying setWindowState(WindowFullScreen)")
            self.setWindowState(Qt.WindowState.WindowFullScreen)
            self.show()
            return True
        except Exception as e:
            logger.error(f"Window state fullscreen failed: {e}")
            return False

    def _try_manual_geometry_fullscreen(self, screen_geometry: QRect | None) -> bool:
        """Try manual geometry setting as last resort."""
        try:
            if not screen_geometry:
                logger.error("No screen geometry available for manual fullscreen")
                return False

            logger.debug(f"Trying manual geometry fullscreen: {screen_geometry}")

            # Set geometry to exact screen bounds
            self.setGeometry(screen_geometry)

            # Show window normally (not showFullScreen to avoid conflicts)
            self.show()

            # Try to raise and activate
            self.raise_()
            self.activateWindow()

            return True
        except Exception as e:
            logger.error(f"Manual geometry fullscreen failed: {e}")
            return False

    def _log_fullscreen_result(self):
        """Log the final fullscreen result for debugging."""
        try:
            actual_geometry = self.geometry()
            window_state = self.windowState()
            is_fullscreen = self.isFullScreen()

            target_screen = self._get_target_screen()
            expected_geometry = target_screen.geometry() if target_screen else None

            logger.info("Fullscreen Result:")
            logger.info(f"  Window geometry: {actual_geometry}")
            logger.info(f"  Expected geometry: {expected_geometry}")
            logger.info(f"  Window state: {window_state}")
            logger.info(f"  isFullScreen(): {is_fullscreen}")

            # Check if we actually cover the full screen
            if expected_geometry and actual_geometry:
                covers_full_screen = (
                    actual_geometry.width() >= expected_geometry.width() and
                    actual_geometry.height() >= expected_geometry.height()
                )
                logger.info(f"  Covers full screen: {covers_full_screen}")

                if not covers_full_screen:
                    logger.warning("FULLSCREEN ISSUE: Window does not cover full screen!")
                    self._try_fullscreen_recovery()

        except Exception as e:
            logger.error(f"Error logging fullscreen result: {e}")

    def _try_fullscreen_recovery(self):
        """Attempt to recover from partial fullscreen coverage."""
        logger.info("Attempting fullscreen recovery...")

        try:
            # Get the target screen again
            target_screen = self._get_target_screen()
            if not target_screen:
                return

            screen_geometry = target_screen.geometry()

            # Try different recovery strategies based on platform
            system = platform.system().lower()

            if system == "windows":
                # Windows-specific recovery
                logger.debug("Applying Windows fullscreen recovery")
                self.setWindowState(Qt.WindowState.WindowNoState)
                # Use a safer timer with weakref to avoid use-after-free
                weak_self = weakref.ref(self)
                def set_fullscreen() -> None:
                    widget = weak_self()
                    if widget is not None:
                        widget.setWindowState(Qt.WindowState.WindowFullScreen)
                QTimer.singleShot(50, set_fullscreen)

            elif system == "linux":
                # Linux-specific recovery
                logger.debug("Applying Linux fullscreen recovery")
                self.showNormal()
                # Use a safer timer with weakref to avoid use-after-free
                weak_self = weakref.ref(self)
                def show_fullscreen() -> None:
                    widget = weak_self()
                    if widget is not None:
                        widget.showFullScreen()
                QTimer.singleShot(50, show_fullscreen)

            else:
                # Generic recovery
                logger.debug("Applying generic fullscreen recovery")
                self.showNormal()
                self.setGeometry(screen_geometry)
                self.showFullScreen()

        except Exception as e:
            logger.error(f"Fullscreen recovery failed: {e}")

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle close event."""
        logger.info("Fullscreen sprite viewer closing")

        # Stop all timers to prevent accessing deleted object
        if hasattr(self, 'cursor_timer'):
            self.cursor_timer.stop()
        if hasattr(self, 'transition_timer'):
            self.transition_timer.stop()

        # Show cursor again
        self.setCursor(Qt.CursorShape.ArrowCursor)

        # Emit closed signal
        self.viewer_closed.emit()

        super().closeEvent(event)

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press - show cursor and controls."""
        self.setCursor(Qt.CursorShape.ArrowCursor)

        # Hide cursor again after delay
        if hasattr(self, 'cursor_timer'):
            self.cursor_timer.stop()
            self.cursor_timer.start(3000)

        super().mousePressEvent(event)

