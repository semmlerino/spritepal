"""
Background indexing worker for visual similarity search.

Automatically indexes sprites as they're found during ROM scanning,
building a searchable index for visual similarity queries.
Now accepts `ApplicationStateManager` via dependency injection.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image
from PySide6.QtCore import QObject, Signal, Slot

from core.visual_similarity_search import VisualSimilarityEngine
from core.workers.base import BaseWorker, handle_worker_errors
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager
    from core.protocols.manager_protocols import ExtractionManagerProtocol

logger = get_logger(__name__)

class SimilarityIndexingWorker(BaseWorker):
    """
    Background worker that indexes sprites for visual similarity search.

    Listens for sprite_found signals and automatically builds an index
    of visual signatures for each sprite found during ROM scanning.
    """

    # Additional signals specific to similarity indexing
    sprite_indexed = Signal(int)
    """Emitted when a sprite is indexed. Args: offset (int)."""

    index_saved = Signal(str)
    """Emitted when index is saved to disk. Args: save_path."""

    index_loaded = Signal(int)
    """Emitted when index is loaded from cache. Args: sprite_count (int)."""

    def __init__(
        self,
        rom_path: str,
        parent: QObject | None = None,
        *,
        settings_manager: ApplicationStateManager,
    ):
        """
        Initialize similarity indexing worker.

        Args:
            rom_path: Path to the ROM file being scanned
            parent: Parent QObject
            settings_manager: ApplicationStateManager instance (required).
        """
        super().__init__(parent)
        self.rom_path = rom_path
        self.rom_hash = self._calculate_rom_hash(rom_path)
        self.settings_manager = settings_manager

        # Initialize similarity engine
        self.similarity_engine = VisualSimilarityEngine()

        # Cache directory for similarity indices
        self.cache_dir = self._get_cache_directory()
        self.index_file = self.cache_dir / f"{self.rom_hash}.json"

        # Indexing state
        self._indexed_count = 0
        self._total_to_index = 0
        self._pending_sprites: dict[int, dict[str, Any]] = {}  # pyright: ignore[reportExplicitAny] - Dynamic sprite data
        self._index_lock = threading.Lock()

        # Load existing index if available
        self._load_existing_index()

        logger.info(f"Initialized similarity indexing worker for ROM: {Path(rom_path).name}")
        logger.debug(f"ROM hash: {self.rom_hash}")
        logger.debug(f"Index file: {self.index_file}")

    def _calculate_rom_hash(self, rom_path: str) -> str:
        """Calculate a hash of the ROM file for cache identification."""
        try:
            with Path(rom_path).open("rb") as f:
                # Hash first 64KB for performance while maintaining uniqueness
                chunk = f.read(65536)
                return hashlib.sha256(chunk).hexdigest()[:16]
        except Exception as e:
            logger.warning(f"Could not calculate ROM hash: {e}")
            # Fallback to path-based hash
            return hashlib.sha256(rom_path.encode()).hexdigest()[:16]

    def _get_cache_directory(self) -> Path:
        """Get the cache directory for similarity indices."""
        try:
            settings_manager = self.settings_manager
            # Try to get custom cache directory from settings
            # TODO: Implement get_cache_directory method on SettingsManager
            cache_root_str = settings_manager.get_cache_location() # Call the correct method
            if not cache_root_str:
                cache_root = Path.home() / ".spritepal"
            else:
                cache_root = Path(cache_root_str)
        except Exception:
            # Fallback to default location
            cache_root = Path.home() / ".spritepal"

        cache_dir = cache_root / "similarity_indices"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _load_existing_index(self) -> None:
        """Load existing similarity index if available."""
        # Use Any since json.load returns Any - isinstance narrows it
        index_data: Any = None  # pyright: ignore[reportExplicitAny] - json.load returns Any

        if self.index_file.exists():
            try:
                with self.index_file.open("r", encoding="utf-8") as f:
                    index_data = json.load(f)
                logger.debug("Loaded index from JSON format")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Could not load JSON index: {e}")
                index_data = None

        if index_data is None:
            logger.debug("No existing similarity index found")
            return

        # Validate index format
        if not isinstance(index_data, dict) or "version" not in index_data:
            logger.warning("Invalid index file format, will rebuild")
            return

        # Check version compatibility
        if index_data.get("version") != "1.0":
            logger.info(f"Index version mismatch (found {index_data.get('version')}, expected 1.0), will rebuild")
            return

        # Load sprite database
        sprite_hashes = index_data.get("sprite_hashes", {})
        for offset_str, hash_data in sprite_hashes.items():
            try:
                offset = int(offset_str)
                # Reconstruct SpriteHash objects in the engine
                self.similarity_engine.sprite_database[offset] = hash_data
            except (ValueError, KeyError) as e:
                logger.warning(f"Skipping invalid hash data for offset {offset_str}: {e}")

        loaded_count = len(self.similarity_engine.sprite_database)
        logger.info(f"Loaded {loaded_count} sprites from existing similarity index")
        self.index_loaded.emit(loaded_count)

    def _save_index(self) -> None:
        """Save current similarity index to disk as JSON."""
        if not self.similarity_engine.sprite_database:
            logger.debug("No sprites to save in similarity index")
            return

        try:
            # Prepare index data
            sprite_hashes: dict[str, Any] = {}  # pyright: ignore[reportExplicitAny] - Dynamic sprite hash data
            # Convert sprite database to serializable format
            for offset, sprite_hash in self.similarity_engine.sprite_database.items():
                sprite_hashes[str(offset)] = sprite_hash

            index_data: dict[str, Any] = {  # pyright: ignore[reportExplicitAny] - Index metadata and hashes
                "version": "1.0",
                "rom_hash": self.rom_hash,
                "rom_path": str(self.rom_path),
                "created_at": str(Path(self.rom_path).stat().st_mtime),
                "sprite_count": len(self.similarity_engine.sprite_database),
                "sprite_hashes": sprite_hashes
            }

            self._save_index_json(index_data)

            logger.info(f"Saved similarity index with {len(self.similarity_engine.sprite_database)} sprites to {self.index_file}")
            self.index_saved.emit(str(self.index_file))

        except Exception as e:
            logger.exception(f"Could not save similarity index: {e}")
            # Clean up temporary file if it exists
            temp_file = self.index_file.with_suffix(".tmp")
            if temp_file.exists():
                with contextlib.suppress(Exception):
                    temp_file.unlink()

    def _save_index_json(self, index_data: dict[str, Any]) -> None:  # pyright: ignore[reportExplicitAny] - Index data dict
        """Save index data as JSON with atomic write.

        Args:
            index_data: Dictionary containing the index data to save
        """
        # Write to temporary file first for atomic operation
        temp_file = self.index_file.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2)

        # Atomic rename
        temp_file.replace(self.index_file)

    @Slot(dict)
    def on_sprite_found(self, sprite_info: dict[str, Any]) -> None:  # pyright: ignore[reportExplicitAny] - Signal payload
        """
        Handle sprite_found signal by indexing the sprite.

        Args:
            sprite_info: Dictionary containing sprite information including offset
        """
        try:
            offset = sprite_info.get("offset")
            if offset is None:
                logger.warning("Sprite info missing offset, cannot index")
                return

            # Check if already indexed
            if offset in self.similarity_engine.sprite_database:
                logger.debug(f"Sprite at 0x{offset:X} already indexed, skipping")
                return

            # Store sprite info for processing
            with self._index_lock:
                self._pending_sprites[offset] = sprite_info
                self._total_to_index += 1

            logger.debug(f"Queued sprite at 0x{offset:X} for indexing")

        except Exception as e:
            logger.exception(f"Error handling sprite_found signal: {e}")

    @Slot()
    def on_scan_finished(self) -> None:
        """Handle scan completion by starting background indexing."""
        if not self._pending_sprites:
            logger.info("No sprites to index")
            self.operation_finished.emit(True, "No sprites to index")
            return

        logger.info(f"Starting background indexing of {len(self._pending_sprites)} sprites")
        self.start()

    @handle_worker_errors("similarity indexing")
    def run(self) -> None:
        """Background indexing of pending sprites."""
        try:
            from core.di_container import inject
            from core.protocols.manager_protocols import ExtractionManagerProtocol
            extraction_manager = inject(ExtractionManagerProtocol)
            indexed_count = 0

            # Process pending sprites
            sprites_to_process = list(self._pending_sprites.items())
            total_sprites = len(sprites_to_process)

            # Handle case where no sprites to index
            if total_sprites == 0:
                logger.info("No sprites to index")
                self.emit_progress(100, "No sprites to index")
                return

            self.emit_progress(0, f"Starting indexing of {total_sprites} sprites")

            for i, (offset, sprite_info) in enumerate(sprites_to_process):
                # Check for cancellation
                self.check_cancellation()
                self.wait_if_paused()

                try:
                    # Extract sprite image for indexing
                    sprite_image = self._extract_sprite_image(offset, extraction_manager)
                    if sprite_image is None:
                        logger.warning(f"Could not extract image for sprite at 0x{offset:X}")
                        continue

                    # Index the sprite
                    self.similarity_engine.index_sprite(
                        offset=offset,
                        image=sprite_image,
                        metadata=sprite_info
                    )

                    indexed_count += 1
                    self.sprite_indexed.emit(offset)

                    # Update progress
                    progress = int((i + 1) / total_sprites * 100)
                    self.emit_progress(progress, f"Indexed {indexed_count}/{total_sprites} sprites")

                    logger.debug(f"Indexed sprite at 0x{offset:X} ({indexed_count}/{total_sprites})")

                except Exception as e:
                    logger.exception(f"Failed to index sprite at 0x{offset:X}: {e}")
                    continue

            # Clear pending sprites
            with self._index_lock:
                if self._pending_sprites:
                    self._pending_sprites.clear()

            # Save index to disk
            if indexed_count > 0:
                self.emit_progress(100, "Saving similarity index...")
                self._save_index()

            logger.info(f"Similarity indexing complete: {indexed_count} sprites indexed")
            self.operation_finished.emit(True, f"Indexed {indexed_count} sprites")

        except InterruptedError:
            logger.info("Similarity indexing cancelled")
            self.operation_finished.emit(False, "Indexing cancelled")
        except Exception as e:
            logger.exception("Similarity indexing failed")
            self.operation_finished.emit(False, f"Indexing failed: {e}")

    def _extract_sprite_image(self, offset: int, extraction_manager: ExtractionManagerProtocol) -> Image.Image | None:
        """
        Extract sprite image for indexing.

        Args:
            offset: ROM offset of the sprite
            extraction_manager: Manager to handle sprite extraction

        Returns:
            PIL Image of the sprite, or None if extraction failed
        """
        try:
            # Use extraction manager to get sprite data
            # TODO: Implement extract_sprite_at_offset method on ExtractionManager
            sprite_data = extraction_manager.extract_sprite_at_offset(  # type: ignore[attr-defined]
                rom_path=self.rom_path,
                offset=offset,
                output_format="RGBA"  # Get as PIL Image
            )

            if sprite_data and hasattr(sprite_data, "image"):
                return sprite_data.image

            logger.warning(f"No image data returned for sprite at 0x{offset:X}")
            return None

        except Exception as e:
            logger.exception(f"Failed to extract sprite image at 0x{offset:X}: {e}")
            return None

    def get_similarity_engine(self) -> VisualSimilarityEngine:
        """Get the similarity engine for external use."""
        return self.similarity_engine

    def get_indexed_count(self) -> int:
        """Get the number of currently indexed sprites."""
        return len(self.similarity_engine.sprite_database)

    def is_sprite_indexed(self, offset: int) -> bool:
        """Check if a sprite at the given offset is already indexed."""
        return offset in self.similarity_engine.sprite_database
