"""
Manager for handling all injection operations (VRAM and ROM)
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from typing_extensions import override
except ImportError:
    from typing_extensions import override

from PySide6.QtCore import QObject, QThread, Signal

if TYPE_CHECKING:
    from .session_manager import SessionManager

from utils.constants import (
    SETTINGS_KEY_FAST_COMPRESSION,
    SETTINGS_KEY_LAST_CUSTOM_OFFSET,
    SETTINGS_KEY_LAST_INPUT_ROM,
    SETTINGS_KEY_LAST_INPUT_VRAM,
    SETTINGS_KEY_LAST_SPRITE_LOCATION,
    SETTINGS_KEY_VRAM_PATH,
    SETTINGS_NS_ROM_INJECTION,
)
from utils.file_validator import FileValidator
from utils.rom_cache import get_rom_cache

from .base_manager import BaseManager
from .exceptions import ValidationError


class InjectionManager(BaseManager):
    """Manages all injection workflows (VRAM and ROM)"""

    # Additional signals specific to injection
    injection_progress: Signal = Signal(str)  # Progress message
    injection_finished: Signal = Signal(bool, str)  # Success, message
    compression_info: Signal = Signal(dict)  # ROM compression statistics
    progress_percent: Signal = Signal(int)  # Progress percentage (0-100)
    cache_saved: Signal = Signal(str, int)  # Cache type, number of items saved

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the injection manager"""
        # Declare instance variables with type hints
        self._current_worker: QThread | None = None

        super().__init__("InjectionManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize injection components"""
        self._current_worker = None
        self._is_initialized = True
        self._logger.info("InjectionManager initialized")

    @override
    def cleanup(self) -> None:
        """Cleanup injection resources"""
        if self._current_worker:
            from core.services.worker_lifecycle import WorkerManager

            self._logger.info("Stopping active injection worker")
            WorkerManager.cleanup_worker(self._current_worker, timeout=5000)
        self._current_worker = None
        # Mark injection operation as finished so new injections can start
        self._finish_operation("injection")

    def reset_state(self, full_reset: bool = False) -> None:
        """Reset internal state for test isolation.

        This method resets mutable state without fully re-initializing the manager.
        Use this for test isolation when you need to clear caches and counters
        but don't want the overhead of full manager re-initialization.

        Args:
            full_reset: If True, also reset initialization state, requiring
                       re-initialization before the manager can be used again.
        """
        # Stop any active worker
        if self._current_worker:
            from core.services.worker_lifecycle import WorkerManager

            self._logger.debug("Stopping active worker during reset_state")
            WorkerManager.cleanup_worker(self._current_worker, timeout=1000)
            self._current_worker = None

        if full_reset:
            self._is_initialized = False

    def _get_session_manager(self) -> SessionManager:
        """Get session manager via dependency injection container"""
        from core.di_container import inject
        from core.protocols.manager_protocols import SessionManagerProtocol
        return inject(SessionManagerProtocol)  # type: ignore[return-value]  # Protocol returns concrete class

    def start_injection(self, params: dict[str, Any]) -> bool:
        """
        Start injection process with unified interface

        Args:
            params: Injection parameters containing:
                - mode: "vram" or "rom"
                - sprite_path: Path to sprite PNG file
                - For VRAM: input_vram, output_vram, offset
                - For ROM: input_rom, output_rom, offset, fast_compression
                - : metadata_path

        Returns:
            True if injection started successfully, False otherwise

        Raises:
            InjectionError: If injection cannot be started
            ValidationError: If parameters are invalid
        """
        operation = "injection"

        if not self._start_operation(operation):
            return False

        def _validate_injection_mode(mode: str) -> None:
            """Validate injection mode and raise error if invalid"""
            if mode not in ("vram", "rom"):
                raise ValidationError(f"Invalid injection mode: {mode}")

        try:
            # Local imports to avoid circular dependency
            from core.services.worker_lifecycle import WorkerManager
            from ui.workers.injection_worker import InjectionWorker
            from ui.workers.rom_injection_worker import ROMInjectionWorker

            # Validate parameters
            self.validate_injection_params(params)

            # Stop any existing worker
            WorkerManager.cleanup_worker(self._current_worker, timeout=1000)
            self._current_worker = None

            # Create appropriate worker based on mode
            if params["mode"] == "vram":
                worker = InjectionWorker(
                    params["sprite_path"],
                    params["input_vram"],
                    params["output_vram"],
                    params["offset"],
                    params.get("metadata_path")
                )
            elif params["mode"] == "rom":
                worker = ROMInjectionWorker(
                    params["sprite_path"],
                    params["input_rom"],
                    params["output_rom"],
                    params["offset"],
                    params.get("fast_compression", False),
                    params.get("metadata_path")
                )
            else:
                _validate_injection_mode(params["mode"])
                return False  # Unreachable but satisfies type checker

            # Connect worker signals before starting
            self._current_worker = worker
            self._connect_worker_signals()

            # Start the worker - only assign permanently after successful start
            worker.start()

            mode_text = "VRAM" if params["mode"] == "vram" else "ROM"
            self._logger.info(f"Started {mode_text} injection: {params['sprite_path']}")
            self.injection_progress.emit(f"Starting {mode_text} injection...")
            return True

        except (OSError, PermissionError) as e:
            self._handle_file_io_error(e, operation, "injection startup")
            raise  # Unreachable but satisfies type checker
        except (ValueError, TypeError) as e:
            self._handle_data_format_error(e, operation, "injection startup")
            raise  # Unreachable but satisfies type checker
        except Exception as e:
            self._handle_error(e, operation)
            return False

    def validate_injection_params(self, params: dict[str, Any]) -> None:
        """
        Validate injection parameters

        Args:
            params: Parameters to validate

        Raises:
            ValidationError: If parameters are invalid
        """
        # Check required common parameters
        required = ["mode", "sprite_path", "offset"]
        self._validate_required(params, required)

        self._validate_type(params["mode"], "mode", str)
        self._validate_type(params["sprite_path"], "sprite_path", str)
        self._validate_type(params["offset"], "offset", int)

        # Use FileValidator for sprite file validation
        sprite_result = FileValidator.validate_image_file(params["sprite_path"])
        if not sprite_result.is_valid:
            raise ValidationError(f"Sprite file validation failed: {sprite_result.error_message}")

        self._validate_range(params["offset"], "offset", min_val=0)

        # Check mode-specific parameters
        if params["mode"] == "vram":
            vram_required = ["input_vram", "output_vram"]
            self._validate_required(params, vram_required)

            # Use FileValidator for VRAM file validation
            vram_result = FileValidator.validate_vram_file(params["input_vram"])
            if not vram_result.is_valid:
                raise ValidationError(f"Input VRAM file validation failed: {vram_result.error_message}")

        elif params["mode"] == "rom":
            rom_required = ["input_rom", "output_rom"]
            self._validate_required(params, rom_required)

            # Use FileValidator for ROM file validation
            rom_result = FileValidator.validate_rom_file(params["input_rom"])
            if not rom_result.is_valid:
                raise ValidationError(f"Input ROM file validation failed: {rom_result.error_message}")

            # Validate optional fast_compression parameter
            if "fast_compression" in params:
                self._validate_type(params["fast_compression"], "fast_compression", bool)
        else:
            raise ValidationError(f"Invalid injection mode: {params['mode']}")

        # Validate optional metadata_path
        if params.get("metadata_path"):
            # Use FileValidator for JSON metadata file validation
            metadata_result = FileValidator.validate_json_file(params["metadata_path"])
            if not metadata_result.is_valid:
                raise ValidationError(f"Metadata file validation failed: {metadata_result.error_message}")

    def get_smart_vram_suggestion(self, sprite_path: str, metadata_path: str = "") -> str:
        """
        Get smart suggestion for input VRAM path using multiple strategies

        Args:
            sprite_path: Path to sprite file
            metadata_path: metadata file path

        Returns:
            Suggested VRAM path or empty string if none found
        """
        strategies = [
            lambda: self._try_extraction_panel_vram(),
            lambda: self._try_metadata_vram(metadata_path, sprite_path),
            lambda: self._try_basename_vram_patterns(sprite_path),
            lambda: self._try_session_vram(),
            lambda: self._try_last_injection_vram(),
        ]

        for strategy in strategies:
            try:
                vram_path = strategy()
                if vram_path:
                    self._logger.debug(f"Smart VRAM suggestion found: {vram_path}")
                    return vram_path
            except (OSError, ValueError) as e:
                self._logger.debug(f"VRAM suggestion strategy failed: {e}")
                continue
            except Exception as e:
                self._logger.debug(f"Unexpected error in VRAM suggestion strategy: {e}")
                continue

        self._logger.debug("No VRAM suggestion found")
        return ""

    def is_injection_active(self) -> bool:
        """Check if injection is currently active"""
        return bool(self._current_worker and self._current_worker.isRunning())

    def _connect_worker_signals(self) -> None:
        """Connect worker signals to manager signals"""
        if not self._current_worker:
            return

        # Common signals for both worker types
        worker = self._current_worker  # Type narrowing for safety
        if hasattr(worker, "progress"):
            worker.progress.connect(self._on_worker_progress)  # type: ignore[attr-defined]
        if hasattr(worker, "injection_finished"):
            worker.injection_finished.connect(self._on_worker_finished)  # type: ignore[attr-defined]
        else:
            # Fallback to QThread's finished signal
            worker.finished.connect(lambda: self._on_worker_finished(True, "Completed"))

        # ROM-specific signals
        if hasattr(worker, "progress_percent"):
            worker.progress_percent.connect(self.progress_percent.emit)  # type: ignore[attr-defined]
        if hasattr(worker, "compression_info"):
            worker.compression_info.connect(self.compression_info.emit)  # type: ignore[attr-defined]

    def _on_worker_progress(self, message: str) -> None:
        """Handle worker progress updates"""
        self.injection_progress.emit(message)

    def _on_worker_finished(self, success: bool, message: str) -> None:
        """Handle worker completion"""
        self._finish_operation("injection")
        self.injection_finished.emit(success, message)

        if success:
            self._logger.info(f"Injection completed successfully: {message}")
        else:
            self._logger.error(f"Injection failed: {message}")

    def _try_extraction_panel_vram(self) -> str:
        """Try to get VRAM path from extraction panel's current session"""
        try:
            session_manager = self._get_session_manager()
            vram_path = session_manager.get("session", "vram_path", "")
            if vram_path and Path(vram_path).exists():
                return vram_path
        except (OSError, ValueError):
            pass  # Expected: file not found, invalid data
        return ""

    def _try_metadata_vram(self, metadata_path: str, sprite_path: str) -> str:
        """Try to get VRAM path from metadata file"""
        if not metadata_path or not Path(metadata_path).exists():
            return ""

        try:
            with Path(metadata_path).open() as f:
                metadata = json.load(f)
            vram_path = metadata.get("source_vram", "")
            if vram_path and Path(vram_path).exists():
                return vram_path
        except (OSError, ValueError, json.JSONDecodeError):
            pass  # Expected: file not found, invalid format, malformed JSON
        return ""

    def _try_basename_vram_patterns(self, sprite_path: str) -> str:
        """Try to find VRAM file using basename patterns"""
        sprite_path_obj = Path(sprite_path)
        sprite_dir = sprite_path_obj.parent
        base_name = sprite_path_obj.stem

        # Common VRAM file patterns
        patterns = [
            f"{base_name}.dmp",
            f"{base_name}_VRAM.dmp",
            f"{base_name}.vram",
            "VRAM.dmp",
            "vram.dmp",
        ]

        for pattern in patterns:
            vram_path = sprite_dir / pattern
            if vram_path.exists():
                return str(vram_path)
        return ""

    def _try_session_vram(self) -> str:
        """Try to get VRAM path from session data"""
        try:
            session_manager = self._get_session_manager()
            recent_vram = session_manager.get_recent_files("vram")
            if recent_vram and Path(recent_vram[0]).exists():
                return recent_vram[0]
        except (OSError, ValueError, IndexError, TypeError):
            pass  # Expected: file not found, invalid data, empty list, wrong type
        return ""

    def _try_last_injection_vram(self) -> str:
        """Try to get VRAM path from last injection settings"""
        try:
            session_manager = self._get_session_manager()
            last_injection_vram = session_manager.get(
                SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_VRAM, ""
            )
            if last_injection_vram and Path(last_injection_vram).exists():
                return last_injection_vram
        except (OSError, ValueError, TypeError):
            pass  # Expected: file not found, invalid data, wrong type
        return ""

    def load_metadata(self, metadata_path: str) -> dict[str, Any] | None:
        """
        Load and parse metadata file

        Args:
            metadata_path: Path to metadata JSON file

        Returns:
            Parsed metadata dict with extraction info, or None if loading fails
        """
        if not metadata_path or not Path(metadata_path).exists():
            return None

        # Initialize variables to avoid unbound variable errors
        parsed_info = None
        metadata = None

        try:
            with Path(metadata_path).open() as f:
                metadata = json.load(f)

            # Parse extraction info if available
            if "extraction" in metadata:
                extraction = metadata["extraction"]
                source_type = extraction.get("source_type", "vram")

                parsed_info = {
                    "metadata": metadata,
                    "source_type": source_type,
                    "extraction": extraction
                }

                if source_type == "rom":
                    # ROM extraction metadata
                    parsed_info["rom_extraction_info"] = {
                        "rom_source": extraction.get("rom_source", ""),
                        "rom_offset": extraction.get("rom_offset", "0x0"),
                        "sprite_name": extraction.get("sprite_name", ""),
                        "tile_count": extraction.get("tile_count", "Unknown")
                    }
                    parsed_info["extraction_vram_offset"] = None
                    parsed_info["default_vram_offset"] = "0xC000"
                else:
                    # VRAM extraction metadata
                    vram_offset = extraction.get("vram_offset", "0xC000")
                    parsed_info["extraction_vram_offset"] = vram_offset
                    parsed_info["rom_extraction_info"] = None

        except (OSError, PermissionError) as e:
            self._logger.warning(f"File I/O error loading metadata from {metadata_path}: {e}")
            return None
        except (json.JSONDecodeError, ValueError) as e:
            self._logger.warning(f"Invalid metadata format in {metadata_path}: {e}")
            return None
        except Exception as e:
            self._logger.warning(f"Failed to load metadata from {metadata_path}: {e}")
            return None
        else:
            if metadata and "extraction" in metadata and parsed_info:
                return parsed_info
            return {
                "metadata": metadata,
                "source_type": "vram",
                "extraction": None,
                "extraction_vram_offset": None,
                "rom_extraction_info": None,
                "default_vram_offset": "0xC000"
            }

    def load_rom_info(self, rom_path: str) -> dict[str, Any] | None:
        """
        Load ROM information and sprite locations with caching

        Args:
            rom_path: Path to ROM file

        Returns:
            Dict containing:
                - header: ROM header info
                - sprite_locations: Dict of sprite name -> offset
                - cached: True if loaded from cache
                - error: Error message if failed
            Or None if loading completely fails
        """
        def _create_error_result(message: str, error_type: str) -> dict[str, Any]:
            """Helper to create consistent error result dictionaries"""
            return {"error": message, "error_type": error_type}

        try:
            # Validate ROM file
            error_result = self._validate_rom_file(rom_path)
            if error_result:
                return error_result

            # Try to load from cache first
            rom_cache = get_rom_cache()
            cached_info = rom_cache.get_rom_info(rom_path)

            if cached_info:
                self._logger.debug(f"Loaded ROM info from cache: {rom_path}")
                cached_info["cached"] = True
                return cached_info

            # Cache miss - load from ROM file
            self._logger.debug(f"Cache miss, loading ROM info from file: {rom_path}")

            # Get extraction manager via dependency injection container
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            extraction_manager = inject(ExtractionManagerProtocol)
            header = extraction_manager.read_rom_header(rom_path)

            result: dict[str, Any] = {
                "header": {
                    "title": header["title"],
                    "rom_type": header["rom_type"],
                    "checksum": header["checksum"]
                },
                "sprite_locations": {},
                "cached": False
            }

            # Get sprite locations if this is Kirby Super Star
            if "KIRBY" in header["title"].upper():
                try:
                    self._logger.info(f"Scanning ROM for sprite locations: {header['title']}")
                    locations = extraction_manager.get_known_sprite_locations(rom_path)

                    # Convert to simple dict of name -> offset
                    sprite_dict = {}
                    for name, pointer in locations.items():
                        display_name = name.replace("_", " ").title()
                        sprite_dict[display_name] = pointer.offset
                    result["sprite_locations"] = sprite_dict

                    self._logger.info(f"Found {len(sprite_dict)} sprite locations")

                    # Cache the results for future use
                    cache_success = rom_cache.save_rom_info(rom_path, result)
                    if cache_success:
                        self._logger.debug(f"Cached ROM info for future use: {rom_path}")
                        self.cache_saved.emit("rom_info", 1)

                except Exception as sprite_error:
                    self._logger.warning(f"Failed to load sprite locations: {sprite_error}")
                    result["sprite_locations_error"] = str(sprite_error)
            # Cache the header info even for non-Kirby ROMs
            elif rom_cache.save_rom_info(rom_path, result):
                self.cache_saved.emit("rom_info", 1)

        except Exception as e:
            self._logger.exception("Failed to load ROM info")
            return _create_error_result(str(e), type(e).__name__)
        else:
            return result

    def _validate_rom_file(self, rom_path: str) -> dict[str, Any] | None:
        """Validate ROM file exists, is readable, and has reasonable size.

        Returns:
            Error dict if validation fails, None if valid
        """
        # Check file exists and is readable
        if not Path(rom_path).exists():
            return {"error": f"ROM file not found: {rom_path}", "error_type": "FileNotFoundError"}

        if not os.access(rom_path, os.R_OK):
            return {"error": f"Cannot read ROM file: {rom_path}", "error_type": "PermissionError"}

        # Check file size is reasonable for a SNES ROM
        file_size = Path(rom_path).stat().st_size
        if file_size < 0x8000:  # Minimum reasonable SNES ROM size (32KB)
            return {"error": f"File too small to be a valid SNES ROM: {file_size} bytes", "error_type": "ValueError"}

        if file_size > 0x600000:  # Maximum reasonable size (6MB)
            return {"error": f"File too large to be a valid SNES ROM: {file_size} bytes", "error_type": "ValueError"}

        return None

    def find_suggested_input_vram(self, sprite_path: str, metadata: dict[str, Any] | None = None,
                                  suggested_vram: str = "") -> str:
        """
        Find the best suggestion for input VRAM path

        Args:
            sprite_path: Path to sprite file
            metadata: Loaded metadata dict (from load_metadata)
            suggested_vram: Pre-suggested VRAM path

        Returns:
            Suggested VRAM path or empty string if none found
        """
        # If we already have a suggestion, use it
        if suggested_vram and Path(suggested_vram).exists():
            return suggested_vram

        # Try metadata first
        if metadata and metadata.get("extraction"):
            vram_source = metadata["extraction"].get("vram_source", "")
            if vram_source and sprite_path:
                # Look for the file in the sprite's directory
                sprite_dir = Path(sprite_path).parent
                possible_path = Path(sprite_dir) / vram_source
                if possible_path.exists():
                    return str(possible_path)

        # Try to find VRAM file with same base name as sprite
        if sprite_path:
            sprite_dir = Path(sprite_path).parent
            sprite_base = Path(sprite_path).stem

            # Remove common sprite suffixes to find original base
            for suffix in ["_sprites_editor", "_sprites", "_editor", "Edited"]:
                if sprite_base.endswith(suffix):
                    sprite_base = sprite_base[: -len(suffix)]
                    break

            # Try common VRAM file patterns
            vram_patterns = [
                f"{sprite_base}.dmp",
                f"{sprite_base}.SnesVideoRam.dmp",
                f"{sprite_base}_VRAM.dmp",
                f"{sprite_base}.VideoRam.dmp",
                f"{sprite_base}.VRAM.dmp",
            ]

            for pattern in vram_patterns:
                possible_path = Path(sprite_dir) / pattern
                if possible_path.exists():
                    return str(possible_path)

        # Check session data from settings manager
        session_manager = self._get_session_manager()
        session_data = session_manager.get_session_data()
        if SETTINGS_KEY_VRAM_PATH in session_data:
            vram_path = session_data[SETTINGS_KEY_VRAM_PATH]
            if vram_path and Path(vram_path).exists():
                return vram_path

        # Check last used injection VRAM
        last_injection_vram = session_manager.get(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_VRAM, ""
        )
        if last_injection_vram and Path(last_injection_vram).exists():
            return last_injection_vram

        return ""

    def suggest_output_vram_path(self, input_vram_path: str) -> str:
        """
        Suggest output VRAM path based on input path with smart numbering

        Args:
            input_vram_path: Input VRAM file path

        Returns:
            Suggested output path
        """
        base = Path(input_vram_path).stem

        # Check if base already ends with "_injected" to avoid duplication
        base = base.removesuffix("_injected")  # Remove "_injected"

        # Try _injected first
        suggested_path = f"{base}_injected.dmp"
        if not Path(suggested_path).exists():
            return suggested_path

        # If _injected exists, try _injected2, _injected3, etc.
        counter = 2
        while counter <= 10:  # Reasonable limit
            suggested_path = f"{base}_injected{counter}.dmp"
            if not Path(suggested_path).exists():
                return suggested_path
            counter += 1

        # If all numbered versions exist, just use the base with timestamp
        timestamp = int(time.time())
        return f"{base}_injected_{timestamp}.dmp"

    def suggest_output_rom_path(self, input_rom_path: str) -> str:
        """
        Suggest output ROM path based on input path with smart numbering

        Args:
            input_rom_path: Input ROM file path

        Returns:
            Suggested output path (in same directory as input)
        """
        input_path = Path(input_rom_path)
        parent = input_path.parent
        base = input_path.stem
        ext = input_path.suffix

        # Check if base already ends with "_modified" to avoid duplication
        base = base.removesuffix("_modified")  # Remove "_modified"

        # Try _modified first
        suggested_path = parent / f"{base}_modified{ext}"
        if not suggested_path.exists():
            return str(suggested_path)

        # If _modified exists, try _modified2, _modified3, etc.
        counter = 2
        while counter <= 10:  # Reasonable limit
            suggested_path = parent / f"{base}_modified{counter}{ext}"
            if not suggested_path.exists():
                return str(suggested_path)
            counter += 1

        # If all numbered versions exist, just use the base with timestamp
        timestamp = int(time.time())
        return str(parent / f"{base}_modified_{timestamp}{ext}")

    def convert_vram_to_rom_offset(self, vram_offset_str: str | int) -> int | None:
        """
        Convert VRAM offset to ROM offset based on known mappings

        Args:
            vram_offset_str: VRAM offset as string (e.g., "0xC000") or int

        Returns:
            ROM offset as integer, or None if no mapping found
        """
        try:
            # Parse VRAM offset
            if isinstance(vram_offset_str, str):
                vram_offset = int(vram_offset_str, 16)
            else:
                vram_offset = vram_offset_str

            # Known VRAM to ROM mappings for Kirby Super Star
            # VRAM 0xC000 (sprite area) typically maps to ROM locations for sprite data
            if vram_offset == 0xC000:
                # Default to Kirby Normal sprite location
                return 0x0C8000

            # For other offsets, no direct mapping available
            # Could be extended with more mappings in the future

        except (ValueError, TypeError):
            return None
        else:
            return None

    def save_rom_injection_settings(self, input_rom: str, sprite_location_text: str,
                                    custom_offset: str, fast_compression: bool) -> None:
        """
        Save ROM injection parameters to settings for future use

        Args:
            input_rom: Input ROM path
            sprite_location_text: Selected sprite location text from combo box
            custom_offset: Custom offset text if used
            fast_compression: Fast compression checkbox state
        """
        session_manager = self._get_session_manager()

        # Save input ROM path
        if input_rom:
            session_manager.set(
                SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, input_rom
            )

        # Save sprite location (from combo box)
        if sprite_location_text and sprite_location_text != "Select sprite location...":
            session_manager.set(
                SETTINGS_NS_ROM_INJECTION,
                SETTINGS_KEY_LAST_SPRITE_LOCATION,
                sprite_location_text
            )

        # Save custom offset if used
        if custom_offset:
            session_manager.set(
                SETTINGS_NS_ROM_INJECTION,
                SETTINGS_KEY_LAST_CUSTOM_OFFSET,
                custom_offset
            )

        # Save fast compression setting
        session_manager.set(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION, fast_compression
        )

        # Save settings to file
        try:
            session_manager.save_session()
        except Exception:
            self._logger.exception("Failed to save ROM injection parameters")

    def load_rom_injection_defaults(self, sprite_path: str, metadata: dict[str, Any] | None = None
                                   ) -> dict[str, Any]:
        """
        Load ROM injection defaults from metadata or saved settings

        Args:
            sprite_path: Path to sprite file
            metadata: Loaded metadata dict (from load_metadata)

        Returns:
            Dict containing:
                - input_rom: Suggested input ROM path
                - output_rom: Suggested output ROM path
                - rom_offset: Suggested ROM offset (int)
                - sprite_location_index: Index to select in combo box
                - custom_offset: Custom offset text
                - fast_compression: Fast compression setting
        """
        session_manager = self._get_session_manager()
        result: dict[str, Any] = {
            "input_rom": "",
            "output_rom": "",
            "rom_offset": None,
            "sprite_location_index": None,
            "custom_offset": "",
            "fast_compression": False
        }

        # Check if we have ROM extraction metadata
        if metadata and metadata.get("rom_extraction_info"):
            rom_info = metadata["rom_extraction_info"]
            rom_source = rom_info.get("rom_source", "")
            rom_offset_str = rom_info.get("rom_offset", "0x0")

            # Look for the ROM file in the sprite's directory
            if rom_source and sprite_path:
                sprite_dir = Path(sprite_path).parent
                possible_rom_path = Path(sprite_dir) / rom_source
                if possible_rom_path.exists():
                    result["input_rom"] = str(possible_rom_path)
                    result["output_rom"] = self.suggest_output_rom_path(possible_rom_path)

                    # Parse the ROM offset
                    try:
                        if rom_offset_str.startswith(("0x", "0X")):
                            result["rom_offset"] = int(rom_offset_str, 16)
                        else:
                            result["rom_offset"] = int(rom_offset_str, 16)
                        result["custom_offset"] = rom_offset_str
                    except (ValueError, TypeError):
                        pass

                    return result

        # Fall back to saved settings
        last_input_rom = session_manager.get(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_INPUT_ROM, ""
        )
        if last_input_rom and Path(last_input_rom).exists():
            result["input_rom"] = last_input_rom
            result["output_rom"] = self.suggest_output_rom_path(last_input_rom)

        # Load last used custom offset
        result["custom_offset"] = session_manager.get(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_CUSTOM_OFFSET, ""
        )

        # Load fast compression setting
        result["fast_compression"] = session_manager.get(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_FAST_COMPRESSION, False
        )

        return result

    def restore_saved_sprite_location(self, extraction_vram_offset: str | None,
                                     sprite_locations: dict[str, int]) -> dict[str, Any]:
        """
        Restore saved sprite location selection

        Args:
            extraction_vram_offset: VRAM offset from extraction metadata
            sprite_locations: Dict of sprite name -> offset from loaded ROM

        Returns:
            Dict containing:
                - sprite_location_name: Name to select in combo box
                - sprite_location_index: Index to select (1-based)
                - custom_offset: Custom offset text if no match
        """
        session_manager = self._get_session_manager()
        result: dict[str, str | int | None] = {
            "sprite_location_name": None,
            "sprite_location_index": None,
            "custom_offset": ""
        }

        # First, try to use extraction offset if available
        if extraction_vram_offset:
            # Convert VRAM offset to ROM offset and find matching sprite location
            rom_offset = self.convert_vram_to_rom_offset(extraction_vram_offset)
            if rom_offset is not None:
                # Find sprite location that matches this offset
                for i, (name, offset) in enumerate(sprite_locations.items(), 1):
                    if offset == rom_offset:
                        result["sprite_location_name"] = name
                        result["sprite_location_index"] = i
                        return result
                # If no exact match, set custom offset
                result["custom_offset"] = f"0x{rom_offset:X}"
                return result

        # Fall back to saved sprite location
        last_sprite_location = session_manager.get(
            SETTINGS_NS_ROM_INJECTION, SETTINGS_KEY_LAST_SPRITE_LOCATION, ""
        )
        if last_sprite_location:
            # Extract display name from saved text (remove offset part if present)
            saved_display_name = last_sprite_location.split(" (0x")[0] if " (0x" in last_sprite_location else last_sprite_location

            # Find matching sprite location in dict
            for i, name in enumerate(sprite_locations.keys(), 1):
                if name == saved_display_name:
                    result["sprite_location_name"] = name
                    result["sprite_location_index"] = i
                    break

        return result

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get ROM cache statistics

        Returns:
            Dictionary with cache information
        """
        rom_cache = get_rom_cache()
        return rom_cache.get_cache_stats()

    def clear_rom_cache(self, older_than_days: int | None = None) -> int:
        """
        Clear ROM scan cache

        Args:
            older_than_days: If specified, only clear files older than this many days

        Returns:
            Number of cache files removed
        """
        rom_cache = get_rom_cache()
        removed_count = rom_cache.clear_cache(older_than_days)
        self._logger.info(f"ROM cache cleared: {removed_count} files removed")
        return removed_count

    def get_scan_progress(self, rom_path: str, scan_params: dict[str, Any]) -> dict[str, Any] | None:
        """
        Get cached scan progress for resumable scanning

        Args:
            rom_path: Path to ROM file
            scan_params: Scan parameters (start_offset, end_offset, step, etc.)

        Returns:
            Dictionary with scan progress or None if not cached
        """
        rom_cache = get_rom_cache()
        return rom_cache.get_partial_scan_results(rom_path, scan_params)

    def save_scan_progress(self, rom_path: str, scan_params: dict[str, Any],
                          found_sprites: list[dict[str, Any]], current_offset: int,
                          completed: bool = False) -> bool:
        """
        Save partial scan results for resumable scanning

        Args:
            rom_path: Path to ROM file
            scan_params: Scan parameters (start_offset, end_offset, step)
            found_sprites: List of sprites found so far
            current_offset: Current scan position
            completed: Whether the scan is complete

        Returns:
            True if saved successfully, False otherwise
        """
        rom_cache = get_rom_cache()
        return rom_cache.save_partial_scan_results(
            rom_path, scan_params, found_sprites, current_offset, completed
        )

    def clear_scan_progress(self, rom_path: str | None = None,
                           scan_params: dict[str, Any] | None = None) -> int:
        """
        Clear scan progress caches

        Args:
            rom_path: If specified, only clear caches for this ROM
            scan_params: If specified, only clear cache for this specific scan

        Returns:
            Number of files removed
        """
        rom_cache = get_rom_cache()
        removed_count = rom_cache.clear_scan_progress_cache(rom_path, scan_params)
        self._logger.info(f"Scan progress cache cleared: {removed_count} files removed")
        return removed_count
