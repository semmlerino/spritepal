"""
Advanced search worker for background sprite searching.

Provides parallel search, visual similarity search, and pattern-based search
capabilities in a background thread.
"""

from __future__ import annotations

import mmap
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, override

from PIL import Image
from PySide6.QtCore import Signal

from core.parallel_sprite_finder import ParallelSpriteFinder, SearchResult
from core.visual_similarity_search import VisualSimilarityEngine
from core.workers.base import BaseWorker, handle_worker_errors
from utils.constants import MAX_SPRITE_SIZE, MIN_SPRITE_SIZE
from utils.logging_config import get_logger

if TYPE_CHECKING:
    from ui.components.filters.search_filters_widget import SearchFilter

logger = get_logger(__name__)


class AdvancedSearchWorker(BaseWorker):
    """Worker thread for background searching.

    Inherits from BaseWorker for standard worker lifecycle management.
    Supports parallel sprite search, visual similarity search, and pattern search.
    """

    # Custom signals specific to search
    result_found = Signal(SearchResult)
    """Emitted when a result is found."""

    search_complete = Signal(list)  # all results
    """Emitted when search completes. Args: all results list."""

    error = Signal(str)
    """Emitted on error. Args: error_message."""

    def __init__(
        self,
        search_type: str,
        params: dict[str, Any],  # pyright: ignore[reportExplicitAny] - varied param types
    ) -> None:
        super().__init__()
        self.search_type = search_type
        self.params = params
        self.finder: ParallelSpriteFinder | None = None
        self._operation_name = f"AdvancedSearchWorker-{search_type}"  # Override BaseWorker's default
        # Note: BaseWorker handles WorkerManager registration automatically

    @handle_worker_errors("search operation")
    @override
    def run(self) -> None:
        """Execute search based on type."""
        try:
            if self.search_type == "parallel":
                self._run_parallel_search()
            elif self.search_type == "visual":
                self._run_visual_search()
            elif self.search_type == "pattern":
                self._run_pattern_search()
            else:
                self.error.emit(f"Unknown search type: {self.search_type}")
        except Exception as e:
            logger.exception("Search worker error")
            self.error.emit(str(e))
        finally:
            # Always cleanup finder resources
            self._cleanup_finder()

    def _run_parallel_search(self) -> None:
        """Run parallel sprite search."""
        from ui.components.filters.search_filters_widget import SearchFilter

        rom_path = str(self.params["rom_path"])
        start = int(self.params.get("start_offset", 0))
        end_val = self.params.get("end_offset", None)
        end = int(end_val) if end_val is not None else None
        filters_val = self.params.get(
            "filters",
            SearchFilter(
                min_size=MIN_SPRITE_SIZE,
                max_size=MAX_SPRITE_SIZE,
                min_tiles=1,
                max_tiles=1024,
                alignment=1,
                include_compressed=True,
                include_uncompressed=False,
                confidence_threshold=0.5,
            ),
        )
        filters = (
            filters_val
            if isinstance(filters_val, SearchFilter)
            else SearchFilter(
                min_size=MIN_SPRITE_SIZE,
                max_size=MAX_SPRITE_SIZE,
                min_tiles=1,
                max_tiles=1024,
                alignment=1,
                include_compressed=True,
                include_uncompressed=False,
                confidence_threshold=0.5,
            )
        )

        # Create parallel finder
        self.finder = ParallelSpriteFinder(
            num_workers=int(self.params.get("num_workers", 4)), step_size=int(self.params.get("step_size", 0x100))
        )

        # Search without progress callback (removed dead signal)
        results = self.finder.search_parallel(
            rom_path,
            start,
            end,
            cancellation_token=self,
        )

        # Apply filters
        filtered_results = []
        for result in results:
            if self._apply_filters(result, filters):
                filtered_results.append(result)
                self.result_found.emit(result)

        self.search_complete.emit(filtered_results)

    def _run_visual_search(self) -> None:
        """Run visual similarity search."""
        try:
            rom_path = str(self.params["rom_path"])
            similarity_threshold = float(self.params["similarity_threshold"])
            self.params["search_scope"]

            # Determine search mode: offset or image file
            ref_offset = self.params.get("reference_offset")
            image_path = self.params.get("image_path")

            # Initialize similarity engine
            similarity_engine = VisualSimilarityEngine()

            # Check if similarity index exists
            index_path = Path(rom_path).with_suffix(".similarity_index")
            if not index_path.exists():
                self.error.emit("No similarity index found for ROM. Please build index first.")
                return

            # Load similarity index
            try:
                similarity_engine.import_index(index_path)
                logger.info(f"Loaded similarity index with {len(similarity_engine.sprite_database)} sprites")
            except Exception as e:
                self.error.emit(f"Failed to load similarity index: {e}")
                return

            # Search for similar sprites
            max_results = int(self.params.get("max_results", 50))

            # Determine the search target (offset or image)
            target: Image.Image | int
            if image_path is not None:
                # Load the uploaded image
                try:
                    target = Image.open(image_path)
                    # Convert to RGBA for consistent processing
                    if target.mode != "RGBA":
                        target = target.convert("RGBA")
                    logger.info(f"Using uploaded image as reference: {image_path}")
                except Exception as e:
                    self.error.emit(f"Failed to load image: {e}")
                    return
            else:
                # Use offset-based search
                ref_offset = int(ref_offset)  # type: ignore[arg-type]
                if ref_offset not in similarity_engine.sprite_database:
                    self.error.emit(f"Reference sprite at 0x{ref_offset:X} not found in index")
                    return
                target = ref_offset

            # Perform similarity search
            self.progress.emit(0, 1)  # Indeterminate progress

            matches = similarity_engine.find_similar(
                target,
                max_results=max_results,
                similarity_threshold=similarity_threshold / 100.0,  # Convert percentage to decimal
            )

            self.progress.emit(1, 1)

            # Convert matches to SearchResult format for compatibility
            results = []
            for match in matches:
                # Create a simplified SearchResult from SimilarityMatch
                result = SearchResult(
                    offset=match.offset,
                    size=0,  # Not available from similarity search
                    tile_count=0,  # Not available from similarity search
                    compressed_size=0,  # Not available from similarity search
                    confidence=match.similarity_score,
                    metadata={"similarity_score": match.similarity_score, "hash_distance": match.hash_distance},
                )
                results.append(result)
                self.result_found.emit(result)

            self.search_complete.emit(results)

        except Exception as e:
            logger.exception("Visual search error")
            self.error.emit(str(e))

    def _run_pattern_search(self) -> None:
        """Run pattern-based search with hex patterns and regex support."""
        try:
            rom_path = str(self.params["rom_path"])
            patterns_val = self.params.get("patterns", [])
            patterns = list(patterns_val) if isinstance(patterns_val, list) else []
            pattern_type = str(self.params.get("pattern_type", "hex"))
            case_sensitive = bool(self.params.get("case_sensitive", False))
            alignment = int(self.params.get("alignment", 1))
            context_bytes = int(self.params.get("context_bytes", 16))
            max_results = int(self.params.get("max_results", 1000))
            operation = str(self.params.get("operation", "Single Pattern"))

            if not patterns:
                self.error.emit("No patterns specified")
                return

            # Use memory-mapped file for large ROMs
            with Path(rom_path).open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as rom_data:
                rom_size = len(rom_data)

                if operation == "Single Pattern" or len(patterns) == 1:
                    # Single pattern search
                    pattern = patterns[0]
                    if pattern_type == "hex":
                        self._search_hex_pattern(rom_data, pattern, alignment, context_bytes, max_results, rom_size)
                    elif pattern_type == "regex":
                        self._search_regex_pattern(
                            rom_data, pattern, case_sensitive, alignment, context_bytes, max_results, rom_size
                        )
                    else:
                        self.error.emit(f"Unknown pattern type: {pattern_type}")
                        return
                # Multiple pattern search
                elif pattern_type == "hex":
                    self._search_multiple_hex_patterns(
                        rom_data, patterns, operation, alignment, context_bytes, max_results, rom_size
                    )
                elif pattern_type == "regex":
                    self._search_multiple_regex_patterns(
                        rom_data, patterns, operation, case_sensitive, alignment, context_bytes, max_results, rom_size
                    )
                else:
                    self.error.emit(f"Unknown pattern type: {pattern_type}")
                    return

            self.search_complete.emit([])  # Results are emitted individually via result_found

        except Exception as e:
            logger.exception("Pattern search error")
            self.error.emit(str(e))

    def _search_hex_pattern(
        self, rom_data: mmap.mmap, pattern_str: str, alignment: int, context_bytes: int, max_results: int, rom_size: int
    ) -> None:
        """Search for hex pattern with wildcard support."""
        try:
            # Parse hex pattern (e.g., "00 01 02 ?? FF")
            pattern_bytes, mask = self._parse_hex_pattern(pattern_str)
            if not pattern_bytes:
                self.error.emit("Invalid hex pattern format")
                return

            pattern_len = len(pattern_bytes)
            results_count = 0
            chunk_size = 0x10000  # 64KB chunks for progress updates

            # Search through ROM data
            for start_offset in range(0, rom_size - pattern_len + 1, chunk_size):
                # Check cancellation
                if self.is_cancelled:
                    break

                # Update progress
                progress = int((start_offset / rom_size) * 100)
                self.progress.emit(progress, 100)

                # Search within this chunk (with overlap for pattern boundary)
                chunk_end = min(start_offset + chunk_size + pattern_len - 1, rom_size)

                offset = start_offset
                while offset <= chunk_end - pattern_len:
                    # Check alignment
                    if alignment > 1 and offset % alignment != 0:
                        offset += 1
                        continue

                    # Check pattern match
                    if self._match_hex_pattern_at_offset(rom_data, offset, pattern_bytes, mask):
                        # Create search result
                        context_start = max(0, offset - context_bytes)
                        context_end = min(rom_size, offset + pattern_len + context_bytes)
                        context_data = bytes(rom_data[context_start:context_end])

                        result = SearchResult(
                            offset=offset,
                            size=pattern_len,
                            tile_count=1,  # Pattern matches are single entities
                            compressed_size=pattern_len,
                            confidence=1.0,  # Exact match
                            metadata={
                                "pattern": pattern_str,
                                "pattern_type": "hex",
                                "context_start": context_start,
                                "context_data": context_data.hex(),
                                "match_data": bytes(rom_data[offset : offset + pattern_len]).hex(),
                            },
                        )

                        self.result_found.emit(result)
                        results_count += 1

                        # Check if we've reached the maximum results
                        if results_count >= max_results:
                            logger.info(f"Reached maximum results limit: {max_results}")
                            return

                        # Skip past this match
                        offset += pattern_len
                    else:
                        offset += 1

                # Early termination check
                if self.is_cancelled:
                    break

            self.progress.emit(100, 100)

        except Exception as e:
            logger.exception("Hex pattern search error")
            self.error.emit(f"Hex pattern search failed: {e}")

    def _search_regex_pattern(
        self,
        rom_data: mmap.mmap,
        pattern_str: str,
        case_sensitive: bool,
        alignment: int,
        context_bytes: int,
        max_results: int,
        rom_size: int,
    ) -> None:
        """Search for regex pattern in ROM data."""
        try:
            # Compile regex pattern
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                pattern = re.compile(pattern_str.encode(), flags)
            except re.error as e:
                self.error.emit(f"Invalid regex pattern: {e}")
                return

            results_count = 0
            chunk_size = 0x10000  # 64KB chunks
            overlap_size = 1024  # Overlap to catch patterns spanning chunks

            # Search through ROM data in chunks
            for start_offset in range(0, rom_size, chunk_size - overlap_size):
                # Check cancellation
                if self.is_cancelled:
                    break

                # Update progress
                progress = int((start_offset / rom_size) * 100)
                self.progress.emit(progress, 100)

                # Get chunk data
                chunk_end = min(start_offset + chunk_size, rom_size)
                chunk_data = bytes(rom_data[start_offset:chunk_end])

                # Find all matches in this chunk
                for match in pattern.finditer(chunk_data):
                    match_offset = start_offset + match.start()
                    match_len = match.end() - match.start()

                    # Check alignment
                    if alignment > 1 and match_offset % alignment != 0:
                        continue

                    # Avoid duplicate matches in overlap region
                    if start_offset > 0 and match.start() < overlap_size:
                        continue

                    # Create context data
                    context_start = max(0, match_offset - context_bytes)
                    context_end = min(rom_size, match_offset + match_len + context_bytes)
                    context_data = bytes(rom_data[context_start:context_end])

                    result = SearchResult(
                        offset=match_offset,
                        size=match_len,
                        tile_count=1,
                        compressed_size=match_len,
                        confidence=1.0,  # Exact match
                        metadata={
                            "pattern": pattern_str,
                            "pattern_type": "regex",
                            "context_start": context_start,
                            "context_data": context_data.hex(),
                            "match_data": match.group().hex(),
                            "match_text": self._safe_decode(match.group()),
                        },
                    )

                    self.result_found.emit(result)
                    results_count += 1

                    # Check if we've reached the maximum results
                    if results_count >= max_results:
                        logger.info(f"Reached maximum results limit: {max_results}")
                        return

                # Early termination check
                if self.is_cancelled:
                    break

            self.progress.emit(100, 100)

        except Exception as e:
            logger.exception("Regex pattern search error")
            self.error.emit(f"Regex pattern search failed: {e}")

    def _parse_hex_pattern(self, pattern_str: str) -> tuple[bytes, bytes]:
        """
        Parse hex pattern string with wildcards into bytes and mask.

        Args:
            pattern_str: Pattern like "00 01 02 ?? ?? FF"

        Returns:
            Tuple of (pattern_bytes, mask_bytes) where mask has 0xFF for exact match, 0x00 for wildcard
        """
        try:
            # Clean and split pattern
            pattern_str = pattern_str.strip().upper()
            hex_tokens = re.split(r"[\s,]+", pattern_str)

            pattern_bytes = bytearray()
            mask_bytes = bytearray()

            for token in hex_tokens:
                if not token:
                    continue

                if token in {"??", "?"}:
                    # Wildcard - any byte matches
                    pattern_bytes.append(0x00)
                    mask_bytes.append(0x00)
                else:
                    # Hex byte
                    if len(token) != 2 or not all(c in "0123456789ABCDEF" for c in token):
                        raise ValueError(f"Invalid hex token: {token}")

                    byte_value = int(token, 16)
                    pattern_bytes.append(byte_value)
                    mask_bytes.append(0xFF)

            return bytes(pattern_bytes), bytes(mask_bytes)

        except (ValueError, IndexError) as e:
            logger.exception(f"Failed to parse hex pattern '{pattern_str}': {e}")
            return b"", b""

    def _match_hex_pattern_at_offset(
        self, rom_data: mmap.mmap, offset: int, pattern_bytes: bytes, mask_bytes: bytes
    ) -> bool:
        """Check if hex pattern matches at specific offset."""
        if offset + len(pattern_bytes) > len(rom_data):
            return False

        for i, (pattern_byte, mask_byte) in enumerate(zip(pattern_bytes, mask_bytes, strict=False)):
            rom_byte = rom_data[offset + i]
            if mask_byte == 0xFF and rom_byte != pattern_byte:
                return False

        return True

    def _safe_decode(self, data: bytes) -> str:
        """Safely decode bytes to string for display."""
        try:
            # Try common encodings
            for encoding in ["ascii", "utf-8", "latin-1"]:
                try:
                    return data.decode(encoding)
                except UnicodeDecodeError:
                    continue

            # Fallback: replace non-printable chars
            return "".join(chr(b) if 32 <= b <= 126 else f"\\x{b:02x}" for b in data)
        except Exception:
            return "<decode error>"

    def _search_multiple_hex_patterns(
        self,
        rom_data: mmap.mmap,
        patterns: list[str],
        operation: str,
        alignment: int,
        context_bytes: int,
        max_results: int,
        rom_size: int,
    ) -> None:
        """Search for multiple hex patterns with OR/AND operations."""
        try:
            # Parse all patterns
            parsed_patterns = []
            for pattern_str in patterns:
                pattern_bytes, mask = self._parse_hex_pattern(pattern_str)
                if pattern_bytes:
                    parsed_patterns.append((pattern_str, pattern_bytes, mask))
                else:
                    logger.warning(f"Skipping invalid hex pattern: {pattern_str}")

            if not parsed_patterns:
                self.error.emit("No valid hex patterns found")
                return

            results_count = 0
            chunk_size = 0x10000  # 64KB chunks
            and_window_size = 256  # For AND operations, look within this window

            if operation.startswith("OR"):
                # OR operation - find matches for any pattern
                for start_offset in range(0, rom_size, chunk_size):
                    if self.is_cancelled or results_count >= max_results:
                        break

                    progress = int((start_offset / rom_size) * 100)
                    self.progress.emit(progress, 100)

                    chunk_end = min(start_offset + chunk_size, rom_size)

                    # Check each pattern in this chunk
                    for pattern_str, pattern_bytes, mask in parsed_patterns:
                        pattern_len = len(pattern_bytes)

                        offset = start_offset
                        while offset <= chunk_end - pattern_len and results_count < max_results:
                            if alignment > 1 and offset % alignment != 0:
                                offset += 1
                                continue

                            if self._match_hex_pattern_at_offset(rom_data, offset, pattern_bytes, mask):
                                result = self._create_pattern_result(
                                    rom_data, offset, pattern_len, pattern_str, "hex", context_bytes, rom_size
                                )
                                self.result_found.emit(result)
                                results_count += 1
                                offset += pattern_len
                            else:
                                offset += 1

            elif operation.startswith("AND"):
                # AND operation - find locations where all patterns exist nearby
                for start_offset in range(0, rom_size - and_window_size, chunk_size):
                    if self.is_cancelled or results_count >= max_results:
                        break

                    progress = int((start_offset / rom_size) * 100)
                    self.progress.emit(progress, 100)

                    chunk_end = min(start_offset + chunk_size, rom_size)

                    offset = start_offset
                    while offset <= chunk_end - and_window_size and results_count < max_results:
                        if alignment > 1 and offset % alignment != 0:
                            offset += 1
                            continue

                        # Check if all patterns exist within the window
                        window_end = min(offset + and_window_size, rom_size)
                        pattern_matches = []

                        for pattern_str, pattern_bytes, mask in parsed_patterns:
                            pattern_len = len(pattern_bytes)
                            found = False

                            for window_offset in range(offset, window_end - pattern_len + 1):
                                if self._match_hex_pattern_at_offset(rom_data, window_offset, pattern_bytes, mask):
                                    pattern_matches.append((pattern_str, window_offset, pattern_len))
                                    found = True
                                    break

                            if not found:
                                break

                        # If all patterns found, create result
                        if len(pattern_matches) == len(parsed_patterns):
                            # Use the first match as the main result
                            main_pattern, main_offset, main_len = pattern_matches[0]
                            result = self._create_pattern_result(
                                rom_data,
                                main_offset,
                                main_len,
                                f"AND: {main_pattern} (+{len(pattern_matches) - 1} more)",
                                "hex",
                                context_bytes,
                                rom_size,
                            )
                            result.metadata["and_matches"] = pattern_matches
                            self.result_found.emit(result)
                            results_count += 1
                            offset += and_window_size // 2  # Skip ahead to avoid overlaps
                        else:
                            offset += 1

            self.progress.emit(100, 100)

        except Exception as e:
            logger.exception("Multiple hex pattern search error")
            self.error.emit(f"Multiple hex pattern search failed: {e}")

    def _search_multiple_regex_patterns(
        self,
        rom_data: mmap.mmap,
        patterns: list[str],
        operation: str,
        case_sensitive: bool,
        alignment: int,
        context_bytes: int,
        max_results: int,
        rom_size: int,
    ) -> None:
        """Search for multiple regex patterns with OR/AND operations."""
        try:
            # Compile all patterns
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled_patterns = []

            for pattern_str in patterns:
                try:
                    compiled_pattern = re.compile(pattern_str.encode(), flags)
                    compiled_patterns.append((pattern_str, compiled_pattern))
                except re.error as e:
                    logger.warning(f"Skipping invalid regex pattern '{pattern_str}': {e}")

            if not compiled_patterns:
                self.error.emit("No valid regex patterns found")
                return

            results_count = 0
            chunk_size = 0x10000  # 64KB chunks
            overlap_size = 1024  # Overlap to catch patterns spanning chunks
            and_window_size = 256  # For AND operations

            if operation.startswith("OR"):
                # OR operation - find matches for any pattern
                for start_offset in range(0, rom_size, chunk_size - overlap_size):
                    if self.is_cancelled or results_count >= max_results:
                        break

                    progress = int((start_offset / rom_size) * 100)
                    self.progress.emit(progress, 100)

                    chunk_end = min(start_offset + chunk_size, rom_size)
                    chunk_data = bytes(rom_data[start_offset:chunk_end])

                    # Check each pattern in this chunk
                    for pattern_str, pattern in compiled_patterns:
                        for match in pattern.finditer(chunk_data):
                            if results_count >= max_results:
                                break

                            match_offset = start_offset + match.start()
                            match_len = match.end() - match.start()

                            if alignment > 1 and match_offset % alignment != 0:
                                continue

                            # Avoid duplicates in overlap region
                            if start_offset > 0 and match.start() < overlap_size:
                                continue

                            result = self._create_pattern_result(
                                rom_data, match_offset, match_len, pattern_str, "regex", context_bytes, rom_size
                            )
                            result.metadata["match_text"] = self._safe_decode(match.group())
                            self.result_found.emit(result)
                            results_count += 1

            elif operation.startswith("AND"):
                # AND operation - find locations where all patterns exist nearby
                for start_offset in range(0, rom_size - and_window_size, chunk_size):
                    if self.is_cancelled or results_count >= max_results:
                        break

                    progress = int((start_offset / rom_size) * 100)
                    self.progress.emit(progress, 100)

                    chunk_end = min(start_offset + chunk_size, rom_size)

                    offset = start_offset
                    while offset <= chunk_end - and_window_size and results_count < max_results:
                        if alignment > 1 and offset % alignment != 0:
                            offset += 1
                            continue

                        # Check if all patterns exist within the window
                        window_end = min(offset + and_window_size, rom_size)
                        window_data = bytes(rom_data[offset:window_end])
                        pattern_matches = []

                        for pattern_str, pattern in compiled_patterns:
                            match = pattern.search(window_data)
                            if match:
                                match_offset = offset + match.start()
                                match_len = match.end() - match.start()
                                pattern_matches.append(
                                    (pattern_str, match_offset, match_len, self._safe_decode(match.group()))
                                )
                            else:
                                break

                        # If all patterns found, create result
                        if len(pattern_matches) == len(compiled_patterns):
                            # Use the first match as the main result
                            main_pattern, main_offset, main_len, main_text = pattern_matches[0]
                            result = self._create_pattern_result(
                                rom_data,
                                main_offset,
                                main_len,
                                f"AND: {main_pattern} (+{len(pattern_matches) - 1} more)",
                                "regex",
                                context_bytes,
                                rom_size,
                            )
                            result.metadata["match_text"] = main_text
                            result.metadata["and_matches"] = pattern_matches
                            self.result_found.emit(result)
                            results_count += 1
                            offset += and_window_size // 2
                        else:
                            offset += 1

            self.progress.emit(100, 100)

        except Exception as e:
            logger.exception("Multiple regex pattern search error")
            self.error.emit(f"Multiple regex pattern search failed: {e}")

    def _create_pattern_result(
        self,
        rom_data: mmap.mmap,
        offset: int,
        size: int,
        pattern: str,
        pattern_type: str,
        context_bytes: int,
        rom_size: int,
    ) -> SearchResult:
        """Create a SearchResult for a pattern match."""
        context_start = max(0, offset - context_bytes)
        context_end = min(rom_size, offset + size + context_bytes)
        context_data = bytes(rom_data[context_start:context_end])

        return SearchResult(
            offset=offset,
            size=size,
            tile_count=1,
            compressed_size=size,
            confidence=1.0,
            metadata={
                "pattern": pattern,
                "pattern_type": pattern_type,
                "context_start": context_start,
                "context_data": context_data.hex(),
                "match_data": bytes(rom_data[offset : offset + size]).hex(),
            },
        )

    def _apply_filters(self, result: SearchResult, filters: SearchFilter) -> bool:
        """Apply filters to search result."""
        # Size filter
        if not (filters.min_size <= result.size <= filters.max_size):
            return False

        # Tile count filter
        if not (filters.min_tiles <= result.tile_count <= filters.max_tiles):
            return False

        # Alignment filter
        if filters.alignment > 1 and result.offset % filters.alignment != 0:
            return False

        # Compression filter
        is_compressed = result.compressed_size < result.size
        if not filters.include_compressed and is_compressed:
            return False
        if not filters.include_uncompressed and not is_compressed:
            return False

        # Confidence filter
        return not result.confidence < filters.confidence_threshold

    @override
    def cancel(self) -> None:
        """Cancel the search."""
        super().cancel()  # Sets _cancellation_requested and calls requestInterruption()
        self._cleanup_finder()

    def _cleanup_finder(self) -> None:
        """Cleanup finder resources."""
        if self.finder and hasattr(self.finder, "shutdown"):
            try:
                self.finder.shutdown()
                logger.debug("Successfully shut down finder")
            except Exception as e:
                logger.warning(f"Error shutting down finder: {e}")
            finally:
                self.finder = None

    @override
    def emit_error(self, message: str, exception: Exception | None = None) -> None:
        """Emit error signal - compatibility method for decorator."""
        self.error.emit(message)


# Alias for backwards compatibility during transition
SearchWorker = AdvancedSearchWorker
