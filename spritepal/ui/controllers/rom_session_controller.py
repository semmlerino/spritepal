"""
Controller for ROM session lifecycle and settings.

Manages ROM file loading, settings persistence, and header formatting.
Does not directly interact with UI - emits signals for panel to handle.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from utils.constants import ROM_SIZE_4MB
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.rom_validator import ROMHeader

logger = get_logger(__name__)

# Settings namespace and keys for ROM session
SETTINGS_NS_ROM_INJECTION = "rom_injection"
SETTINGS_KEY_LAST_INPUT_ROM = "last_input_rom"


@dataclass(frozen=True)
class ROMInfo:
    """Immutable ROM information.

    Attributes:
        path: Path to the ROM file
        size: Size of the ROM file in bytes
        suggested_output: Suggested output name based on ROM filename
    """

    path: str
    size: int
    suggested_output: str


@dataclass(frozen=True)
class HeaderDisplayInfo:
    """Formatted header information for display.

    Attributes:
        title: ROM title from header
        checksum: ROM checksum as hex string
        has_config: Whether sprite configuration was found
        html: Full formatted HTML for display
    """

    title: str
    checksum: str
    has_config: bool
    html: str


class ROMSessionController(QObject):
    """Controller for managing ROM session state and settings.

    This controller handles ROM file loading logic including:
    - Loading last used ROM from settings
    - Reading ROM size
    - Saving ROM to settings
    - Formatting header information for display
    - Generating suggested output names

    The panel is responsible for:
    - Triggering worker orchestration
    - Updating UI widgets
    - Connecting to this controller's signals

    Signals:
        rom_loaded: Emitted when ROM info is ready.
            Args: (ROMInfo) containing path, size, suggested name
        header_formatted: Emitted when header HTML is ready.
            Args: (HeaderDisplayInfo) containing formatted display info
        error_occurred: Emitted when an error occurs.
            Args: (str) error message

    Example usage:
        controller = ROMSessionController(settings_manager)
        controller.rom_loaded.connect(panel.on_rom_loaded)
        controller.header_formatted.connect(panel.update_header_display)

        # Load ROM and get info
        info = controller.load_rom_file("/path/to/rom.sfc")

        # Format header for display
        display_info = controller.format_header(header, has_configs=True)
    """

    rom_loaded = Signal(object)  # ROMInfo
    header_formatted = Signal(object)  # HeaderDisplayInfo
    error_occurred = Signal(str)

    def __init__(
        self,
        parent: QObject | None = None,
    ) -> None:
        """Initialize the controller.

        Args:
            parent: Parent QObject for proper Qt lifecycle management
        """
        super().__init__(parent)
        self._current_rom_path: str = ""
        self._current_rom_size: int = 0

    @property
    def rom_path(self) -> str:
        """Current ROM path."""
        return self._current_rom_path

    @property
    def rom_size(self) -> int:
        """Current ROM size in bytes."""
        return self._current_rom_size

    def get_last_rom_path(self) -> str | None:
        """Get the last used ROM path from settings.

        Returns:
            Path to last ROM if it exists, None otherwise
        """
        try:
            from core.app_context import get_app_context

            settings = get_app_context().application_state_manager
            last_rom = settings.get(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, "")

            if last_rom and isinstance(last_rom, str) and Path(last_rom).exists():
                logger.debug(f"Found last used ROM: {last_rom}")
                return last_rom
            if last_rom:
                logger.warning(f"Last used ROM not found on disk: {last_rom}")
            else:
                logger.debug("No last used ROM in settings")
            return None
        except Exception:
            logger.exception("Error reading last ROM from settings")
            return None

    def load_rom_file(self, filename: str) -> ROMInfo | None:
        """Load a ROM file and prepare session info.

        This method:
        1. Validates the file exists
        2. Reads the ROM size
        3. Saves to settings
        4. Generates suggested output name

        The panel should call this, then:
        1. Update its UI state
        2. Trigger worker orchestration for header loading

        Args:
            filename: Path to the ROM file

        Returns:
            ROMInfo if successful, None on error
        """
        try:
            if not filename:
                logger.debug("load_rom_file: No filename provided")
                return None

            rom_path = Path(filename)
            if not rom_path.exists():
                logger.warning(f"ROM file not found: {filename}")
                self.error_occurred.emit(f"ROM file not found: {filename}")
                return None

            logger.info(f"Loading ROM file: {filename}")

            # Read ROM size
            try:
                rom_size = rom_path.stat().st_size
                logger.debug(f"ROM size: {rom_size} bytes (0x{rom_size:X})")
            except Exception as e:
                logger.warning(f"Could not determine ROM size: {e}")
                rom_size = ROM_SIZE_4MB  # Default 4MB

            # Save to settings
            self._save_to_settings(filename)

            # Generate suggested output name
            suggested_name = self._generate_output_name(filename)

            # Update internal state
            self._current_rom_path = filename
            self._current_rom_size = rom_size

            # Create and emit info
            info = ROMInfo(
                path=filename,
                size=rom_size,
                suggested_output=suggested_name,
            )
            self.rom_loaded.emit(info)
            logger.info(f"Successfully prepared ROM: {rom_path.name}")

            return info

        except Exception:
            logger.exception("Error loading ROM file %s", filename)
            self._current_rom_path = ""
            self._current_rom_size = 0
            self.error_occurred.emit(f"Error loading ROM: {filename}")
            return None

    def _save_to_settings(self, filename: str) -> None:
        """Save ROM path to settings.

        Args:
            filename: Path to the ROM file
        """
        try:
            from core.app_context import get_app_context

            settings = get_app_context().application_state_manager
            settings.set(SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, filename)
            settings.set_last_used_directory(str(Path(filename).parent))
            logger.debug(f"Saved ROM to settings: {filename}")
        except Exception:
            logger.exception("Error saving ROM to settings")

    def _generate_output_name(self, rom_path: str) -> str:
        """Generate a suggested output name from ROM filename.

        Args:
            rom_path: Path to the ROM file

        Returns:
            Suggested output name (e.g., "rom_name_sprites")
        """
        rom_stem = Path(rom_path).stem
        return f"{rom_stem}_sprites"

    def format_header(
        self,
        header: ROMHeader | None,
        *,
        has_sprite_configs: bool,
    ) -> HeaderDisplayInfo:
        """Format ROM header information for display.

        Args:
            header: ROM header data, or None if loading failed
            has_sprite_configs: Whether sprite configurations were found

        Returns:
            HeaderDisplayInfo with formatted HTML
        """
        if header is None:
            display_info = HeaderDisplayInfo(
                title="Unknown",
                checksum="0000",
                has_config=False,
                html='<span style="color: red;">Error reading ROM header</span>',
            )
            self.header_formatted.emit(display_info)
            return display_info

        # Build info HTML
        checksum_hex = f"0x{header.checksum:04X}"
        html_parts = [
            f"<b>Title:</b> {header.title}<br>",
            f"<b>Checksum:</b> {checksum_hex}<br>",
        ]

        if has_sprite_configs:
            html_parts.append('<span style="color: green;"><b>Status:</b> Configuration found</span>')
        else:
            html_parts.append(
                '<span style="color: orange;"><b>Status:</b> Unknown ROM version - '
                'use "Find Sprites" to scan</span>'
            )

        html = "".join(html_parts)

        display_info = HeaderDisplayInfo(
            title=header.title,
            checksum=checksum_hex,
            has_config=has_sprite_configs,
            html=html,
        )
        self.header_formatted.emit(display_info)
        return display_info

    def clear(self) -> None:
        """Clear the current ROM session state."""
        self._current_rom_path = ""
        self._current_rom_size = 0
        logger.debug("ROM session cleared")
