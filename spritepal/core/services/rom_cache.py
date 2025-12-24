from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

try:
    from utils.logging_config import get_logger
except ImportError:
    # Fallback logger
    import logging
    def get_logger(module_name: str) -> logging.Logger:
        return logging.getLogger(module_name)

if TYPE_CHECKING:
    from core.managers.application_state_manager import ApplicationStateManager

logger = get_logger(__name__)

class ROMCache:
    """Manages caching of ROM scan results for performance optimization."""

    CACHE_VERSION = "1.0"
    CACHE_DIR_NAME = ".spritepal_rom_cache"

    def __init__(self, state_manager: ApplicationStateManager, cache_dir: str | None = None) -> None:
        """Initialize ROM cache with robust error handling.

        Args:
            state_manager: Required ApplicationStateManager instance for cache settings.
            cache_dir: Optional custom cache directory. If None, uses settings or default.
        """
        self._hash_cache: dict[str, str] = {}
        self._hash_cache_lock = threading.Lock()

        self.settings_manager = state_manager  # Keep attribute name for minimal changes

        # Check if caching is enabled in settings
        self._cache_enabled = self.settings_manager.get_cache_enabled()
        if not self._cache_enabled:
            logger.info("ROM caching is disabled in settings")
            self.cache_dir = self._resolve_cache_dir()  # Still set for compatibility
            return

        # Determine cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Check for custom cache location in settings
            custom_location = self.settings_manager.get_cache_location()
            if custom_location:
                self.cache_dir = Path(custom_location)
            else:
                self.cache_dir = self._resolve_cache_dir()

        # Create cache directory if it doesn't exist, with error handling
        if self._cache_enabled:
            self._cache_enabled = self._setup_cache_directory()
            if self._cache_enabled and not self._ensure_writable_cache_dir():
                fallback_dir = Path(tempfile.gettempdir()) / self.CACHE_DIR_NAME
                try:
                    fallback_dir.mkdir(parents=True, exist_ok=True)
                    self.cache_dir = fallback_dir
                    if self._ensure_writable_cache_dir():
                        logger.info(f"Using fallback cache directory: {self.cache_dir}")
                    else:
                        logger.warning(
                            f"Fallback cache directory {fallback_dir} is not writable. "
                            "ROM caching disabled."
                        )
                        self._cache_enabled = False
                except (OSError, PermissionError):
                    logger.exception("Failed to prepare fallback cache directory")
                    self._cache_enabled = False

    def _resolve_cache_dir(self) -> Path:
        """Resolve cache directory, checking env var for test isolation."""
        env_cache_dir = os.environ.get("SPRITEPAL_CACHE_DIR")
        if env_cache_dir:
            return Path(env_cache_dir)
        return Path.home() / self.CACHE_DIR_NAME

    @property
    def cache_enabled(self) -> bool:
        """Get whether caching is enabled."""
        return self._cache_enabled

    def _setup_cache_directory(self) -> bool:
        """Set up cache directory with fallbacks."""

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"ROM cache directory: {self.cache_dir}")
        except (OSError, PermissionError) as e:
            logger.warning(f"Failed to create cache directory {self.cache_dir}: {e}")
            # Fallback to temp directory
            fallback_dir = Path(tempfile.gettempdir()) / self.CACHE_DIR_NAME
            try:
                fallback_dir.mkdir(parents=True, exist_ok=True)
                self.cache_dir = fallback_dir
                logger.info(f"Using fallback cache directory: {self.cache_dir}")
            except (OSError, PermissionError):
                logger.exception("Failed to create fallback cache directory")
                return False

            return True

        return True

    def _ensure_writable_cache_dir(self) -> bool:
        """Verify cache directory is writable; return False if not."""
        try:
            with tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=True) as tmp:
                tmp.write(b"0")
                tmp.flush()
                os.fsync(tmp.fileno())
            return True
        except Exception as e:
            logger.warning(f"Cache directory not writable {self.cache_dir}: {e}")
            return False

    def _get_rom_hash(self, rom_path: str) -> str:
        """Generate SHA-256 hash of ROM file for cache key with caching optimization.

        Uses file metadata (path + mtime + size) as cache key to avoid expensive
        SHA-256 recalculation for unchanged files. This provides significant
        performance improvement for large ROM files (8-32MB).

        Args:
            rom_path: Path to ROM file

        Returns:
            Hex digest of ROM file hash, or path-based hash for non-existent files

        """
        return self._get_rom_hash_cached(rom_path)

    def _get_rom_hash_cached(self, rom_path: str) -> str:
        """Get ROM hash with metadata-based caching for performance.

        Cache key uses file path + mtime + size to detect changes without
        recalculating full SHA-256 hash every time.

        Args:
            rom_path: Path to ROM file

        Returns:
            Cached or computed SHA-256 hash of ROM file
        """
        rom_path_obj = Path(rom_path)

        # Handle non-existent files (test scenarios)
        if not rom_path_obj.exists():
            path_data = f"nonexistent_{rom_path_obj.resolve()}"
            return hashlib.sha256(path_data.encode()).hexdigest()

        try:
            # Get file metadata for cache key
            stat = rom_path_obj.stat()
            metadata_key = f"{rom_path}_{stat.st_mtime}_{stat.st_size}"

            # Thread-safe cache access
            with self._hash_cache_lock:
                if metadata_key in self._hash_cache:
                    logger.debug(f"ROM hash cache hit for {rom_path_obj.name}")
                    return self._hash_cache[metadata_key]

                # Cache miss - compute full hash
                logger.debug(f"ROM hash cache miss for {rom_path_obj.name}, computing SHA-256...")
                computed_hash = self._compute_full_hash(rom_path)

                # Store in cache (limit cache size to prevent memory growth)
                if len(self._hash_cache) >= 100:  # Reasonable limit for ROM hashes
                    # Remove oldest entry (simple LRU-like behavior)
                    oldest_key = next(iter(self._hash_cache))
                    del self._hash_cache[oldest_key]

                self._hash_cache[metadata_key] = computed_hash
                return computed_hash

        except (OSError, PermissionError) as e:
            # Fallback for permission/access errors
            logger.debug(f"Could not read ROM file metadata for hashing, using path-based hash: {e}")
            return hashlib.sha256(str(rom_path).encode()).hexdigest()

    def _compute_full_hash(self, rom_path: str) -> str:
        """Compute full SHA-256 hash of ROM file.

        Separated from caching logic for clarity and testability.

        Args:
            rom_path: Path to ROM file

        Returns:
            SHA-256 hex digest of file contents
        """
        try:
            sha256_hash = hashlib.sha256()
            with Path(rom_path).open("rb") as f:
                # Read in 64KB chunks for better I/O performance on large files
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except (OSError, PermissionError) as e:
            # Ultimate fallback: just use the path itself
            logger.debug(f"Could not read ROM file for hashing, using path-based hash: {e}")
            return hashlib.sha256(str(rom_path).encode()).hexdigest()

    def _get_cache_file_path(self, rom_hash: str, cache_type: str) -> Path:
        """Get cache file path for a ROM hash and cache type."""
        filename = f"{rom_hash}_{cache_type}.json"
        return self.cache_dir / filename

    def _is_cache_valid(self, cache_file: Path, rom_path: str) -> bool:
        """Check if cache file is valid and not stale with robust error handling."""
        if not cache_file.exists():
            return False

        try:
            # Get expiration days from settings
            expiration_days = self.settings_manager.get_cache_expiration_days()

            max_age = expiration_days * 24 * 3600  # Convert days to seconds

            # For non-existent ROM files (test scenarios), only check cache age
            if not Path(rom_path).exists():
                # Check cache age
                cache_age = time.time() - cache_file.stat().st_mtime
                return cache_age <= max_age

            # For real ROM files, check modification time too
            cache_age = time.time() - cache_file.stat().st_mtime
            if cache_age > max_age:
                return False

            # Check if ROM file has been modified since cache creation
            rom_mtime = Path(rom_path).stat().st_mtime
            cache_mtime = cache_file.stat().st_mtime

        except OSError as e:
            logger.debug(f"Error checking cache validity for {cache_file}: {e}")
            return False

        return rom_mtime <= cache_mtime

    def _save_cache_data(
        self, cache_file: Path, cache_data: Mapping[str, object]
    ) -> bool:
        """Safely save cache data with error handling and unique temp files."""
        if not self._cache_enabled:
            return False

        # Initialize temp_file at function scope to ensure cleanup works even if
        # exception occurs before assignment (fixes fragile locals().get() pattern)
        temp_file: Path | None = None

        try:
            # Ensure cache directory exists before saving (thread-safe)
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Create unique temp file name to prevent collisions
            temp_suffix = f".tmp.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}"
            temp_file = cache_file.with_suffix(temp_suffix)

            # Write to temp file then move to avoid corruption
            with temp_file.open("w") as f:
                json.dump(cache_data, f, indent=2)
                # Ensure data reaches disk before rename (prevents data loss on power failure)
                f.flush()
                os.fsync(f.fileno())
            temp_file.replace(cache_file)
        except Exception as e:
            # Clean up temp file if it exists (temp_file initialized before try block)
            self._cleanup_temp_file(temp_file)
            logger.warning(f"Failed to save cache file {cache_file}: {e}")
            return False

        return True

    def _cleanup_temp_file(self, temp_file: Path | None) -> None:
        """Clean up temporary file safely (TRY301: abstract exception handling)."""
        if temp_file is None:
            return
        try:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
        except (OSError, FileNotFoundError):
            pass  # Ignore cleanup errors

    def _load_cache_data(
        self, cache_file: Path, max_retries: int = 3
    ) -> dict[str, object] | None:
        """Safely load cache data with error handling and retry logic."""
        for attempt in range(max_retries):
            try:
                with cache_file.open() as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                if attempt == max_retries - 1:
                    logger.warning(f"Failed to load cache file {cache_file} after {max_retries} attempts: {e}")
                    return None
                # Exponential backoff for retry
                time.sleep(0.01 * (2 ** attempt))
            except Exception as e:
                # For other errors, don't retry
                logger.warning(f"Failed to load cache file {cache_file}: {e}")
                return None
        return None

    def save_partial_scan_results(
        self,
        rom_path: str,
        scan_params: dict[str, int],
        found_sprites: Sequence[Mapping[str, Any]],  # pyright: ignore[reportExplicitAny] - sprite dicts have mixed types
        current_offset: int,
        completed: bool = False,
    ) -> bool:
        """Save partial scan results for incremental progress."""
        if not self._cache_enabled:
            return False

        progress_data = {
            "found_sprites": found_sprites,
            "current_offset": current_offset,
            "last_updated": time.time(),
            "completed": completed,
            "total_found": len(found_sprites),
            "scan_range": {
                "start": scan_params.get("start_offset", 0),
                "end": scan_params.get("end_offset", 0),
                "step": scan_params.get("alignment", scan_params.get("step", 0x100)),  # Support both alignment and step
            },
        }

        try:
            rom_hash = self._get_rom_hash(rom_path)
            scan_id = self._get_scan_id(scan_params)
            cache_file = self._get_cache_file_path(rom_hash, f"scan_progress_{scan_id}")

            cache_data = {
                "version": self.CACHE_VERSION,
                "rom_path": str(Path(rom_path).resolve()),
                "rom_hash": rom_hash,
                "scan_params": scan_params,
                "cached_at": time.time(),
                "scan_progress": progress_data,
            }

            return self._save_cache_data(cache_file, cache_data)

        except Exception as e:
            logger.warning(f"Failed to save scan progress: {e}")
            return False

    def get_partial_scan_results(
        self, rom_path: str, scan_params: dict[str, int]
    ) -> dict[str, object] | None:
        """Get partial scan results for resuming."""
        if not self._cache_enabled:
            return None

        try:
            rom_hash = self._get_rom_hash(rom_path)
            scan_id = self._get_scan_id(scan_params)
            cache_file = self._get_cache_file_path(rom_hash, f"scan_progress_{scan_id}")

            if not self._is_cache_valid(cache_file, rom_path):
                return None

            cache_data = self._load_cache_data(cache_file)
            if not cache_data:
                return None

            # Validate cache format
            if (cache_data.get("version") != self.CACHE_VERSION or
                "scan_progress" not in cache_data):
                return None

            scan_progress = cache_data["scan_progress"]
            # Runtime guarantees this is dict[str, object] from JSON
            return scan_progress if isinstance(scan_progress, dict) else None

        except Exception as e:
            logger.warning(f"Failed to load scan progress: {e}")
            return None

    def _get_scan_id(self, scan_params: dict[str, int]) -> str:
        """Generate unique scan ID from parameters."""
        # Create consistent hash from scan parameters
        param_str = json.dumps(scan_params, sort_keys=True)
        scan_id = hashlib.sha256(param_str.encode()).hexdigest()[:16]
        logger.debug(f"Scan ID for params {scan_params}: {scan_id}")
        return scan_id

    def get_cache_stats(self) -> dict[str, object]:
        """Get cache statistics with error handling."""
        try:
            if not self._cache_enabled or not self.cache_dir.exists():
                return {
                    "cache_dir": str(self.cache_dir),
                    "cache_enabled": False,
                    "total_files": 0,
                    "total_size_bytes": 0,
                    "scan_progress_caches": 0,
                    "cache_dir_exists": False,
                }

            cache_files = list(self.cache_dir.glob("*.json"))
            total_size = sum(f.stat().st_size for f in cache_files if f.exists())

            sprite_location_files = [f for f in cache_files if "_sprite_locations.json" in f.name]
            rom_info_files = [f for f in cache_files if "_rom_info.json" in f.name]
            scan_progress_files = [f for f in cache_files if "_scan_progress_" in f.name]
            preview_files = [f for f in cache_files if "_preview_" in f.name]
            preview_batch_files = [f for f in cache_files if "_preview_batch.json" in f.name]

            return {
                "cache_dir": str(self.cache_dir),
                "cache_enabled": self._cache_enabled,
                "total_files": len(cache_files),
                "total_size_bytes": total_size,
                "sprite_location_caches": len(sprite_location_files),
                "rom_info_caches": len(rom_info_files),
                "scan_progress_caches": len(scan_progress_files),
                "preview_caches": len(preview_files),
                "preview_batch_caches": len(preview_batch_files),
                "cache_dir_exists": self.cache_dir.exists(),
            }

        except Exception as e:
            return {"error": str(e), "cache_enabled": False}

    def clear_cache(self, older_than_days: int | None = None) -> int:
        """Clear cache files and hash cache with error handling."""
        if not self._cache_enabled:
            return 0

        removed_count = 0
        try:
            cutoff_time = None
            if older_than_days is not None:
                cutoff_time = time.time() - (older_than_days * 24 * 3600)

            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    if cutoff_time is None or cache_file.stat().st_mtime < cutoff_time:
                        cache_file.unlink()
                        removed_count += 1
                except (OSError, PermissionError) as e:
                    logger.debug(f"Could not delete cache file {cache_file}: {e}")

            # Clear hash cache when clearing file cache
            with self._hash_cache_lock:
                if older_than_days is None:
                    # Clear all hash cache entries
                    self._hash_cache.clear()
                    logger.debug("Cleared ROM hash cache")
                # Note: For time-based clearing, we can't easily determine which
                # hash cache entries correspond to old files, so we keep them
                # for performance. They'll be evicted naturally by LRU behavior.

        except Exception as e:
            logger.warning(f"Failed to clear cache: {e}")

        return removed_count

    def get_sprite_locations(
        self, rom_path: str
    ) -> dict[str, object] | None:
        """Get cached sprite locations for ROM.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of sprite locations or None if not cached

        """
        if not self._cache_enabled:
            return None

        try:
            rom_hash = self._get_rom_hash(rom_path)
            cache_file = self._get_cache_file_path(rom_hash, "sprite_locations")

            if not self._is_cache_valid(cache_file, rom_path):
                return None

            cache_data = self._load_cache_data(cache_file)
            if not cache_data:
                return None

            # Validate cache format
            if (cache_data.get("version") != self.CACHE_VERSION or
                "sprite_locations" not in cache_data):
                return None

            # Restore SpritePointer objects from cached dictionaries
            sprite_locations = cache_data["sprite_locations"]
            restored_locations = {}

            # Validate type (asserts are disabled with -O, use explicit check)
            if not isinstance(sprite_locations, dict):
                logger.warning(f"Invalid sprite_locations type in cache: {type(sprite_locations).__name__}")
                return None
            for name, location_data in sprite_locations.items():
                if isinstance(location_data, dict) and "offset" in location_data:
                    # Import SpritePointer only when needed to avoid circular imports.
                    # REQUIRED DELAYED IMPORT: Prevents circular dependency:
                    # rom_cache -> rom_injector -> managers -> rom_cache
                    try:
                        from core.rom_injector import (
                            SpritePointer,
                        )
                        # Restore SpritePointer object from cached data
                        restored_locations[name] = SpritePointer(
                            offset=location_data["offset"],
                            bank=location_data.get("bank", 0),
                            address=location_data.get("address", 0),
                            compressed_size=location_data.get("compressed_size"),
                            offset_variants=location_data.get("offset_variants"),
                        )
                    except ImportError:
                        # Fallback: return dict if SpritePointer can't be imported
                        restored_locations[name] = location_data
                else:
                    # Keep as-is for non-SpritePointer data
                    restored_locations[name] = location_data

        except Exception as e:
            logger.warning(f"Failed to load sprite locations from cache: {e}")
            return None

        return restored_locations

    def save_sprite_locations(
        self,
        rom_path: str,
        sprite_locations: Mapping[str, object],
        rom_header: Mapping[str, object] | None = None,
    ) -> bool:
        """Save sprite locations to cache.

        Args:
            rom_path: Path to ROM file
            sprite_locations: Dictionary of sprite locations to cache
            rom_header: Optional ROM header information

        Returns:
            True if saved successfully, False otherwise

        """
        if not self._cache_enabled:
            return False

        try:
            rom_hash = self._get_rom_hash(rom_path)
            cache_file = self._get_cache_file_path(rom_hash, "sprite_locations")

            cache_data = {
                "version": self.CACHE_VERSION,
                "rom_path": str(Path(rom_path).resolve()),
                "rom_hash": rom_hash,
                "cached_at": time.time(),
                "sprite_locations": sprite_locations,
            }

            # Include ROM header if provided
            if rom_header:
                cache_data["rom_header"] = rom_header

            # Convert SpritePointer objects to serializable format if needed
            serializable_locations = {}
            for name, location in sprite_locations.items():
                if hasattr(location, "offset"):
                    # This is a SpritePointer object - capture all fields
                    # Safe to access attributes after hasattr check
                    serializable_locations[name] = {
                        "offset": cast(object, location).offset,  # type: ignore[attr-defined] - SpritePointer has offset attr
                        "bank": getattr(location, "bank", 0),
                        "address": getattr(location, "address", 0),
                        "compressed_size": getattr(location, "compressed_size", None),
                        "offset_variants": getattr(location, "offset_variants", None),
                    }
                else:
                    # Already serializable
                    serializable_locations[name] = location

            cache_data["sprite_locations"] = serializable_locations

            return self._save_cache_data(cache_file, cache_data)

        except Exception as e:
            logger.warning(f"Failed to save sprite locations to cache: {e}")
            return False

    def get_rom_info(
        self, rom_path: str
    ) -> dict[str, object] | None:
        """Get cached ROM information (header, etc.).

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary of ROM info or None if not cached

        """
        if not self._cache_enabled:
            return None

        try:
            rom_hash = self._get_rom_hash(rom_path)
            cache_file = self._get_cache_file_path(rom_hash, "rom_info")

            if not self._is_cache_valid(cache_file, rom_path):
                return None

            cache_data = self._load_cache_data(cache_file)
            if not cache_data:
                return None

            # Validate cache format
            if (cache_data.get("version") != self.CACHE_VERSION or
                "rom_info" not in cache_data):
                return None

            rom_info = cache_data["rom_info"]
            return cast(dict[str, object], rom_info) if isinstance(rom_info, dict) else None

        except Exception as e:
            logger.warning(f"Failed to load ROM info from cache: {e}")
            return None

    def save_rom_info(
        self, rom_path: str, rom_info: Mapping[str, object]
    ) -> bool:
        """Save ROM information to cache.

        Args:
            rom_path: Path to ROM file
            rom_info: Dictionary of ROM information to cache

        Returns:
            True if saved successfully, False otherwise

        """
        if not self._cache_enabled:
            return False

        try:
            rom_hash = self._get_rom_hash(rom_path)
            cache_file = self._get_cache_file_path(rom_hash, "rom_info")

            cache_data = {
                "version": self.CACHE_VERSION,
                "rom_path": str(Path(rom_path).resolve()),
                "rom_hash": rom_hash,
                "cached_at": time.time(),
                "rom_info": rom_info,
            }

            return self._save_cache_data(cache_file, cache_data)

        except Exception as e:
            logger.warning(f"Failed to save ROM info to cache: {e}")
            return False

    def clear_scan_progress_cache(self, rom_path: str | None = None,
                                 scan_params: dict[str, int] | None = None) -> int:
        """Clear scan progress caches."""
        if not self._cache_enabled:
            return 0

        removed_count = 0
        try:
            if rom_path and scan_params:
                # Clear specific scan cache
                rom_hash = self._get_rom_hash(rom_path)
                scan_id = self._get_scan_id(scan_params)
                cache_file = self._get_cache_file_path(rom_hash, f"scan_progress_{scan_id}")
                if cache_file.exists():
                    cache_file.unlink()
                    removed_count = 1
            else:
                # Clear all scan progress caches
                for cache_file in self.cache_dir.glob("*_scan_progress_*.json"):
                    try:
                        cache_file.unlink()
                        removed_count += 1
                    except (OSError, PermissionError) as e:
                        logger.debug(f"Could not delete scan cache {cache_file}: {e}")
        except (OSError, PermissionError) as e:
            logger.debug(f"Error during scan cache cleanup: {e}")

        return removed_count

    def clear_preview_cache(self, rom_path: str | None = None) -> int:
        """Clear preview data caches.

        Args:
            rom_path: Optional ROM path to clear caches for specific ROM only

        Returns:
            Number of cache files removed
        """
        if not self._cache_enabled:
            return 0

        removed_count = 0
        try:
            if rom_path:
                # Clear preview caches for specific ROM
                rom_hash = self._get_rom_hash(rom_path)

                # Clear individual preview caches
                for cache_file in self.cache_dir.glob(f"{rom_hash}_preview_*.json"):
                    try:
                        cache_file.unlink()
                        removed_count += 1
                    except (OSError, PermissionError) as e:
                        logger.debug(f"Could not delete preview cache {cache_file}: {e}")

                # Clear batch preview cache
                batch_cache = self._get_cache_file_path(rom_hash, "preview_batch")
                if batch_cache.exists():
                    try:
                        batch_cache.unlink()
                        removed_count += 1
                    except (OSError, PermissionError) as e:
                        logger.debug(f"Could not delete batch cache {batch_cache}: {e}")
            else:
                # Clear all preview caches
                for cache_file in self.cache_dir.glob("*_preview_*.json"):
                    try:
                        cache_file.unlink()
                        removed_count += 1
                    except (OSError, PermissionError) as e:
                        logger.debug(f"Could not delete preview cache {cache_file}: {e}")

                for cache_file in self.cache_dir.glob("*_preview_batch.json"):
                    try:
                        cache_file.unlink()
                        removed_count += 1
                    except (OSError, PermissionError) as e:
                        logger.debug(f"Could not delete batch cache {cache_file}: {e}")

        except (OSError, PermissionError) as e:
            logger.debug(f"Error during preview cache cleanup: {e}")

        return removed_count

    def _get_cache_key(
        self, rom_hash: str, offset: int, params: Mapping[str, object] | None = None
    ) -> str:
        """Generate consistent cache key for preview data.

        Args:
            rom_hash: Hash of ROM file
            offset: Offset within ROM
            params: Optional parameters affecting preview generation

        Returns:
            Cache key string
        """
        key_components = [rom_hash, str(offset)]

        if params:
            # Sort parameters for consistent key generation
            sorted_params = json.dumps(params, sort_keys=True)
            param_hash = hashlib.md5(sorted_params.encode()).hexdigest()[:8]
            key_components.append(param_hash)

        return "_".join(key_components)

    def save_preview_data(
        self,
        rom_path: str,
        offset: int,
        tile_data: bytes,
        width: int,
        height: int,
        params: Mapping[str, object] | None = None,
    ) -> bool:
        """Save preview tile data to cache with compression.

        Args:
            rom_path: Path to ROM file
            offset: Offset within ROM where sprite data was found
            tile_data: Raw tile data bytes
            width: Width of sprite in pixels
            height: Height of sprite in pixels
            params: Optional parameters used for preview generation

        Returns:
            True if saved successfully, False otherwise
        """
        if not self._cache_enabled:
            return False

        try:
            rom_hash = self._get_rom_hash(rom_path)
            cache_key = self._get_cache_key(rom_hash, offset, params)
            cache_file = self._get_cache_file_path(rom_hash, f"preview_{cache_key}")

            # Compress tile data using zlib (level 6 for balance of speed/compression)
            compressed_data = zlib.compress(tile_data, level=6)

            cache_data = {
                "version": self.CACHE_VERSION,
                "rom_path": str(Path(rom_path).resolve()),
                "rom_hash": rom_hash,
                "cached_at": time.time(),
                "preview_data": {
                    "offset": offset,
                    "tile_data": compressed_data.hex(),  # Store as hex string for JSON
                    "width": width,
                    "height": height,
                    "params": params,
                    "timestamp": time.time(),
                    "compression_ratio": len(compressed_data) / len(tile_data) if tile_data else 0.0,
                }
            }

            success = self._save_cache_data(cache_file, cache_data)
            if success:
                logger.debug(f"Saved preview data for offset {offset:08X} "
                           f"(compressed {len(tile_data)} -> {len(compressed_data)} bytes)")
            return success

        except Exception as e:
            logger.warning(f"Failed to save preview data: {e}")
            return False

    def get_preview_data(
        self, rom_path: str, offset: int, params: Mapping[str, object] | None = None
    ) -> dict[str, object] | None:
        """Get cached preview data for ROM and offset.

        Args:
            rom_path: Path to ROM file
            offset: Offset within ROM
            params: Optional parameters used for preview generation

        Returns:
            Dictionary containing decompressed tile data and metadata, or None if not cached
        """
        if not self._cache_enabled:
            return None

        try:
            rom_hash = self._get_rom_hash(rom_path)
            cache_key = self._get_cache_key(rom_hash, offset, params)
            cache_file = self._get_cache_file_path(rom_hash, f"preview_{cache_key}")

            if not self._is_cache_valid(cache_file, rom_path):
                return None

            cache_data = self._load_cache_data(cache_file)
            if not cache_data:
                return None

            # Validate cache format
            if (cache_data.get("version") != self.CACHE_VERSION or
                "preview_data" not in cache_data):
                return None

            preview_data = cache_data["preview_data"]
            # Validate type (asserts are disabled with -O, use explicit check)
            if not isinstance(preview_data, dict):
                logger.warning(f"Invalid preview_data type in cache: {type(preview_data).__name__}")
                return None

            # Decompress tile data
            try:
                compressed_hex = preview_data["tile_data"]
                compressed_data = bytes.fromhex(compressed_hex)
                tile_data = zlib.decompress(compressed_data)

                # Return decompressed data with metadata
                return {
                    "offset": preview_data["offset"],
                    "tile_data": tile_data,
                    "width": preview_data["width"],
                    "height": preview_data["height"],
                    "params": preview_data.get("params"),
                    "timestamp": preview_data["timestamp"],
                    "compression_ratio": preview_data.get("compression_ratio", 0.0),
                }

            except (ValueError, zlib.error) as e:
                logger.warning(f"Failed to decompress preview data: {e}")
                return None

        except Exception as e:
            logger.warning(f"Failed to load preview data: {e}")
            return None

    def save_preview_batch(
        self, rom_path: str, preview_data_dict: Mapping[int, Mapping[str, object]]
    ) -> bool:
        """Save multiple preview data entries in batch for efficiency.

        Args:
            rom_path: Path to ROM file
            preview_data_dict: Dictionary mapping offsets to preview data
                              Each entry should contain: tile_data, width, height, params

        Returns:
            True if all entries saved successfully, False otherwise
        """
        if not self._cache_enabled:
            return False

        if not preview_data_dict:
            return True

        try:
            rom_hash = self._get_rom_hash(rom_path)
            cache_file = self._get_cache_file_path(rom_hash, "preview_batch")

            # Process each entry and compress tile data
            batch_data = {}
            total_original_size = 0
            total_compressed_size = 0

            for offset, data in preview_data_dict.items():
                tile_data = data["tile_data"]
                if not isinstance(tile_data, bytes):
                    logger.warning(f"Invalid tile data type for offset {offset:08X}")
                    continue

                # Compress tile data
                compressed_data = zlib.compress(tile_data, level=6)
                total_original_size += len(tile_data)
                total_compressed_size += len(compressed_data)

                batch_data[str(offset)] = {
                    "tile_data": compressed_data.hex(),
                    "width": data["width"],
                    "height": data["height"],
                    "params": data.get("params"),
                    "timestamp": time.time(),
                    "compression_ratio": len(compressed_data) / len(tile_data),
                }

            cache_data = {
                "version": self.CACHE_VERSION,
                "rom_path": str(Path(rom_path).resolve()),
                "rom_hash": rom_hash,
                "cached_at": time.time(),
                "batch_preview_data": batch_data,
                "batch_stats": {
                    "entry_count": len(batch_data),
                    "total_original_size": total_original_size,
                    "total_compressed_size": total_compressed_size,
                    "overall_compression_ratio": total_compressed_size / total_original_size if total_original_size > 0 else 0.0,
                }
            }

            success = self._save_cache_data(cache_file, cache_data)
            if success:
                logger.debug(f"Saved batch preview data: {len(batch_data)} entries, "
                           f"compressed {total_original_size} -> {total_compressed_size} bytes")
            return success

        except Exception as e:
            logger.warning(f"Failed to save preview batch: {e}")
            return False

    def refresh_settings(self) -> None:
        """Refresh cache settings from settings manager."""
        # Update cache enabled state
        old_enabled = self._cache_enabled
        self._cache_enabled = self.settings_manager.get_cache_enabled()

        if old_enabled and not self._cache_enabled:
            logger.info("ROM caching has been disabled")
        elif not old_enabled and self._cache_enabled:
            logger.info("ROM caching has been enabled")

        # Update cache location if enabled
        if self._cache_enabled:
            custom_location = self.settings_manager.get_cache_location()
            if custom_location:
                new_dir = Path(custom_location)
                if new_dir != self.cache_dir:
                    logger.info(f"Cache directory changed from {self.cache_dir} to {new_dir}")
                    self.cache_dir = new_dir
                    self._cache_enabled = self._setup_cache_directory()

