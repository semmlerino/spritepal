"""
Advanced search dialog for sophisticated sprite searching.

Provides multiple search modes, filters, history, and visual search capabilities.
"""
from __future__ import annotations

import json
import logging
import mmap
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, override

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.parallel_sprite_finder import ParallelSpriteFinder, SearchResult
from core.services.preview_generator import PreviewGenerator, PreviewRequest
from core.visual_similarity_search import SimilarityMatch, VisualSimilarityEngine
from core.workers.base import BaseWorker, handle_worker_errors
from ui.common import WorkerManager
from ui.common.collapsible_group_box import CollapsibleGroupBox
from ui.common.spacing_constants import ADVANCED_SEARCH_MIN_SIZE, INDENT_UNDER_CONTROL
from ui.components.filters import SearchFiltersWidget
from ui.components.filters.search_filters_widget import SearchFilter
from ui.constants.help_text import TOOLTIPS
from ui.dialogs.similarity_results_dialog import show_similarity_results
from ui.styles.theme import COLORS
from utils.constants import MAX_SPRITE_SIZE, MIN_SPRITE_SIZE

logger = logging.getLogger(__name__)

# SearchFilter is imported from ui.components.filters.search_filters_widget


@dataclass
class SearchHistoryEntry:
    """Entry in search history."""
    timestamp: datetime
    search_type: str
    query: str
    filters: SearchFilter
    results_count: int

    def to_display_string(self) -> str:
        """Format for display in history list."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] {self.search_type}: {self.query} ({self.results_count} results)"

class SearchWorker(BaseWorker):
    """Worker thread for background searching.

    Inherits from BaseWorker for standard worker lifecycle management.
    """

    # Custom signals specific to search
    result_found = Signal(SearchResult)
    """Emitted when a result is found."""

    search_complete = Signal(list)  # all results
    """Emitted when search completes. Args: all results list."""

    error = Signal(str)
    """Emitted on error. Args: error_message."""

    def __init__(self, search_type: str, params: dict[str, Any]):  # pyright: ignore[reportExplicitAny] - search parameters can be varied types
        super().__init__()
        self.search_type = search_type
        self.params = params
        self.finder = None
        self._operation_name = f"SearchWorker-{search_type}"  # Override BaseWorker's default
        # Note: BaseWorker handles WorkerManager registration automatically

    @handle_worker_errors("search operation")
    @override
    def run(self):
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

    def _run_parallel_search(self):
        """Run parallel sprite search."""
        rom_path = str(self.params["rom_path"])
        start = int(self.params.get("start_offset", 0))
        end_val = self.params.get("end_offset", None)
        end = int(end_val) if end_val is not None else None
        filters_val = self.params.get("filters", SearchFilter(
            min_size=MIN_SPRITE_SIZE,
            max_size=MAX_SPRITE_SIZE,
            min_tiles=1,
            max_tiles=1024,
            alignment=1,
            include_compressed=True,
            include_uncompressed=False,
            confidence_threshold=0.5
        ))
        filters = filters_val if isinstance(filters_val, SearchFilter) else SearchFilter(
            min_size=MIN_SPRITE_SIZE,
            max_size=MAX_SPRITE_SIZE,
            min_tiles=1,
            max_tiles=1024,
            alignment=1,
            include_compressed=True,
            include_uncompressed=False,
            confidence_threshold=0.5
        )

        # Create parallel finder
        self.finder = ParallelSpriteFinder(
            num_workers=int(self.params.get("num_workers", 4)),
            step_size=int(self.params.get("step_size", 0x100))
        )

        # Search without progress callback (removed dead signal)
        results = self.finder.search_parallel(
            rom_path,
            start,
            end,
            cancellation_token=self  # type: ignore[arg-type]  # Worker has is_cancelled() method
        )

        # Apply filters
        filtered_results = []
        for result in results:
            if self._apply_filters(result, filters):
                filtered_results.append(result)
                self.result_found.emit(result)

        self.search_complete.emit(filtered_results)

    def _run_visual_search(self):
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
                similarity_threshold=similarity_threshold / 100.0  # Convert percentage to decimal
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
                    metadata={"similarity_score": match.similarity_score,
                             "hash_distance": match.hash_distance}
                )
                results.append(result)
                self.result_found.emit(result)

            self.search_complete.emit(results)

        except Exception as e:
            logger.exception("Visual search error")
            self.error.emit(str(e))

    def _run_pattern_search(self):
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
                            self._search_regex_pattern(rom_data, pattern, case_sensitive, alignment, context_bytes, max_results, rom_size)
                        else:
                            self.error.emit(f"Unknown pattern type: {pattern_type}")
                            return
                    # Multiple pattern search
                    elif pattern_type == "hex":
                        self._search_multiple_hex_patterns(rom_data, patterns, operation, alignment, context_bytes, max_results, rom_size)
                    elif pattern_type == "regex":
                        self._search_multiple_regex_patterns(rom_data, patterns, operation, case_sensitive, alignment, context_bytes, max_results, rom_size)
                    else:
                        self.error.emit(f"Unknown pattern type: {pattern_type}")
                        return

            self.search_complete.emit([])  # Results are emitted individually via result_found

        except Exception as e:
            logger.exception("Pattern search error")
            self.error.emit(str(e))

    def _search_hex_pattern(self, rom_data: mmap.mmap, pattern_str: str, alignment: int, context_bytes: int, max_results: int, rom_size: int):
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
                                "match_data": bytes(rom_data[offset:offset + pattern_len]).hex()
                            }
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

    def _search_regex_pattern(self, rom_data: mmap.mmap, pattern_str: str, case_sensitive: bool, alignment: int, context_bytes: int, max_results: int, rom_size: int):
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
            overlap_size = 1024   # Overlap to catch patterns spanning chunks

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
                            "match_text": self._safe_decode(match.group())
                        }
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

    def _match_hex_pattern_at_offset(self, rom_data: mmap.mmap, offset: int, pattern_bytes: bytes, mask_bytes: bytes) -> bool:
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

    def _search_multiple_hex_patterns(self, rom_data: mmap.mmap, patterns: list[str], operation: str, alignment: int, context_bytes: int, max_results: int, rom_size: int):
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
                                result = self._create_pattern_result(rom_data, offset, pattern_len, pattern_str, "hex", context_bytes, rom_size)
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
                            result = self._create_pattern_result(rom_data, main_offset, main_len, f"AND: {main_pattern} (+{len(pattern_matches)-1} more)", "hex", context_bytes, rom_size)
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

    def _search_multiple_regex_patterns(self, rom_data: mmap.mmap, patterns: list[str], operation: str, case_sensitive: bool, alignment: int, context_bytes: int, max_results: int, rom_size: int):
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
            overlap_size = 1024   # Overlap to catch patterns spanning chunks
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

                            result = self._create_pattern_result(rom_data, match_offset, match_len, pattern_str, "regex", context_bytes, rom_size)
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
                                pattern_matches.append((pattern_str, match_offset, match_len, self._safe_decode(match.group())))
                            else:
                                break

                        # If all patterns found, create result
                        if len(pattern_matches) == len(compiled_patterns):
                            # Use the first match as the main result
                            main_pattern, main_offset, main_len, main_text = pattern_matches[0]
                            result = self._create_pattern_result(rom_data, main_offset, main_len, f"AND: {main_pattern} (+{len(pattern_matches)-1} more)", "regex", context_bytes, rom_size)
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

    def _create_pattern_result(self, rom_data: mmap.mmap, offset: int, size: int, pattern: str, pattern_type: str, context_bytes: int, rom_size: int) -> SearchResult:
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
                "match_data": bytes(rom_data[offset:offset + size]).hex()
            }
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

    def is_set(self) -> bool:
        """Check if cancelled (for cancellation token interface)."""
        return self.is_cancelled  # Use BaseWorker's property

    def _cleanup_finder(self):
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

class AdvancedSearchDialog(QDialog):
    """
    Advanced search dialog with multiple search modes and filters.

    Features:
    - Parallel search with progress
    - Visual similarity search
    - Pattern-based search
    - Search history
    - Advanced filters
    - Keyboard shortcuts
    """

    # Signals
    sprite_selected = Signal(int)  # Offset of selected sprite
    search_started = Signal()
    search_completed = Signal(int)  # Number of results

    def __init__(self, rom_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rom_path = rom_path
        self.search_history = []
        self.current_results = []
        self.search_worker = None

        self._setup_ui()
        self._setup_shortcuts()
        self._load_history()

    def _setup_ui(self) -> None:
        """Setup the user interface."""
        self.setWindowTitle("Advanced Sprite Search")
        self.setMinimumSize(*ADVANCED_SEARCH_MIN_SIZE)

        layout = QVBoxLayout(self)

        # Create tab widget
        self.tabs = QTabWidget()

        # Add search tabs
        self.tabs.addTab(self._create_parallel_search_tab(), "Parallel Search")
        self.tabs.addTab(self._create_visual_search_tab(), "Visual Search")
        self.tabs.addTab(self._create_pattern_search_tab(), "Pattern Search")
        self.tabs.addTab(self._create_history_tab(), "History")

        layout.addWidget(self.tabs)

        # Results section
        results_group = QGroupBox("Search Results")
        results_layout = QVBoxLayout()

        # Results info
        self.results_label = QLabel("No search performed")
        results_layout.addWidget(self.results_label)

        # Results list
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._on_result_selected)
        results_layout.addWidget(self.results_list)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        results_layout.addWidget(self.progress_bar)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close
        )
        buttons.rejected.connect(self.reject)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._start_search)
        buttons.addButton(self.search_button, QDialogButtonBox.ButtonRole.ActionRole)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop_search)
        if self.stop_button:
            self.stop_button.setEnabled(False)
        buttons.addButton(self.stop_button, QDialogButtonBox.ButtonRole.ActionRole)

        layout.addWidget(buttons)

    def _create_parallel_search_tab(self) -> QWidget:
        """Create parallel search tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Search range
        range_group = QGroupBox("Search Range")
        range_layout = QGridLayout()

        # Start offset
        self.start_offset_edit = QLineEdit("0x0")
        self.start_offset_edit.setToolTip(TOOLTIPS["start_offset"])
        range_layout.addWidget(QLabel("Start Offset:"), 0, 0)
        range_layout.addWidget(self.start_offset_edit, 0, 1)

        # End offset
        self.end_offset_edit = QLineEdit("")
        self.end_offset_edit.setPlaceholderText("End of ROM")
        self.end_offset_edit.setToolTip(TOOLTIPS["end_offset"])
        range_layout.addWidget(QLabel("End Offset:"), 1, 0)
        range_layout.addWidget(self.end_offset_edit, 1, 1)

        # Step size
        self.step_size_spin = QSpinBox()
        self.step_size_spin.setRange(0x10, 0x1000)
        self.step_size_spin.setValue(0x100)
        self.step_size_spin.setSingleStep(0x10)
        self.step_size_spin.setPrefix("0x")
        self.step_size_spin.setDisplayIntegerBase(16)
        self.step_size_spin.setToolTip(TOOLTIPS["step_size"])
        range_layout.addWidget(QLabel("Step Size:"), 2, 0)
        range_layout.addWidget(self.step_size_spin, 2, 1)

        range_group.setLayout(range_layout)
        layout.addWidget(range_group)

        # Performance settings - collapsible, collapsed by default
        perf_group = CollapsibleGroupBox("Performance", collapsed=True)
        perf_layout = QGridLayout()

        # Worker threads
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 16)
        self.workers_spin.setValue(4)
        self.workers_spin.setToolTip(TOOLTIPS["worker_threads"])
        perf_layout.addWidget(QLabel("Worker Threads:"), 0, 0)
        perf_layout.addWidget(self.workers_spin, 0, 1)

        # Adaptive stepping
        self.adaptive_check = QCheckBox("Adaptive Step Sizing")
        self.adaptive_check.setChecked(True)
        self.adaptive_check.setToolTip(TOOLTIPS["adaptive_stepping"])
        perf_layout.addWidget(self.adaptive_check, 1, 0, 1, 2)

        perf_group.setContentLayout(perf_layout)
        layout.addWidget(perf_group)

        # Filters - use shared SearchFiltersWidget
        self.filters_widget = SearchFiltersWidget(collapsible=True, expanded=True)
        layout.addWidget(self.filters_widget)

        layout.addStretch()
        return widget

    def _create_visual_search_tab(self) -> QWidget:
        """Create visual search tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Reference source selection
        ref_group = QGroupBox("Reference Selection")
        ref_layout = QVBoxLayout()

        # Mode selection radio buttons
        self.ref_mode_offset_radio = QRadioButton("Use ROM Sprite Offset")
        self.ref_mode_offset_radio.setChecked(True)
        self.ref_mode_offset_radio.toggled.connect(self._on_ref_mode_changed)
        ref_layout.addWidget(self.ref_mode_offset_radio)

        # ROM offset selection row
        offset_layout = QHBoxLayout()
        offset_layout.setContentsMargins(INDENT_UNDER_CONTROL, 0, 0, 0)  # Indent under radio
        self.ref_offset_edit = QLineEdit()
        self.ref_offset_edit.setPlaceholderText("Sprite offset (e.g. 0x12345)")
        self.ref_offset_edit.setToolTip(TOOLTIPS["offset"])
        self.ref_offset_edit.textChanged.connect(self._on_reference_offset_changed)
        offset_layout.addWidget(self.ref_offset_edit)

        self.ref_browse_button = QPushButton("Browse ROM...")
        self.ref_browse_button.clicked.connect(self._browse_reference_sprite)
        offset_layout.addWidget(self.ref_browse_button)
        ref_layout.addLayout(offset_layout)

        # Image file mode
        self.ref_mode_image_radio = QRadioButton("Use Image File")
        self.ref_mode_image_radio.toggled.connect(self._on_ref_mode_changed)
        ref_layout.addWidget(self.ref_mode_image_radio)

        # Image file selection row
        image_layout = QHBoxLayout()
        image_layout.setContentsMargins(INDENT_UNDER_CONTROL, 0, 0, 0)  # Indent under radio
        self.image_path_edit = QLineEdit()
        self.image_path_edit.setPlaceholderText("Image file path (PNG, BMP, GIF)")
        self.image_path_edit.setToolTip(
            "Upload an image to search for similar sprites.\n"
            "Supported formats: PNG, BMP, GIF, JPEG\n"
            "Recommended size: 8x8 to 256x256 pixels"
        )
        self.image_path_edit.setEnabled(False)  # Disabled until image mode selected
        self.image_path_edit.textChanged.connect(self._on_image_path_changed)
        image_layout.addWidget(self.image_path_edit)

        self.image_browse_button = QPushButton("Browse...")
        self.image_browse_button.setEnabled(False)
        self.image_browse_button.clicked.connect(self._browse_image_file)
        image_layout.addWidget(self.image_browse_button)
        ref_layout.addLayout(image_layout)

        # Reference preview
        preview_label = QLabel("Preview:")
        preview_label.setStyleSheet("margin-top: 8px;")
        ref_layout.addWidget(preview_label)

        self.ref_preview_label = QLabel("No reference selected")
        self.ref_preview_label.setMinimumHeight(128)
        self.ref_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ref_preview_label.setStyleSheet(
            f"border: 1px solid {COLORS['border']}; background-color: {COLORS['background']};"
        )
        ref_layout.addWidget(self.ref_preview_label)

        ref_group.setLayout(ref_layout)
        layout.addWidget(ref_group)

        # Similarity settings
        sim_group = QGroupBox("Similarity Settings")
        sim_layout = QGridLayout()

        # Similarity threshold
        self.similarity_slider = QSlider(Qt.Orientation.Horizontal)
        self.similarity_slider.setRange(0, 100)
        self.similarity_slider.setValue(80)
        self.similarity_slider.setToolTip(TOOLTIPS["similarity_threshold"])
        self.similarity_label = QLabel("80%")
        self.similarity_slider.valueChanged.connect(self._update_similarity_label)

        sim_layout.addWidget(QLabel("Similarity Threshold:"), 0, 0)
        sim_layout.addWidget(self.similarity_slider, 0, 1)
        sim_layout.addWidget(self.similarity_label, 0, 2)

        # Search scope
        self.visual_scope_combo = QComboBox()
        self.visual_scope_combo.addItems([
            "Current ROM",
            "All Indexed Sprites",
            "Selected Region"
        ])
        self.visual_scope_combo.setToolTip(TOOLTIPS["search_scope"])
        sim_layout.addWidget(QLabel("Search Scope:"), 1, 0)
        sim_layout.addWidget(self.visual_scope_combo, 1, 1, 1, 2)

        sim_group.setLayout(sim_layout)
        layout.addWidget(sim_group)

        # Store uploaded image
        self._uploaded_image: Image.Image | None = None

        layout.addStretch()
        return widget

    def _create_pattern_search_tab(self) -> QWidget:
        """Create pattern search tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Pattern input
        pattern_group = QGroupBox("Search Pattern")
        pattern_layout = QVBoxLayout()

        # Pattern type
        type_layout = QHBoxLayout()
        self.hex_radio = QRadioButton("Hex Pattern")
        if self.hex_radio:
            self.hex_radio.setChecked(True)
        self.regex_radio = QRadioButton("Regular Expression")
        type_layout.addWidget(self.hex_radio)
        type_layout.addWidget(self.regex_radio)
        type_layout.addStretch()
        pattern_layout.addLayout(type_layout)

        # Pattern input
        self.pattern_edit = QTextEdit()
        self.pattern_edit.setMaximumHeight(100)
        self.pattern_edit.setPlaceholderText(
            "Enter hex pattern (e.g. '00 01 02 ?? ?? FF') or regex"
        )
        pattern_layout.addWidget(self.pattern_edit)

        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)

        # Pattern options
        options_group = QGroupBox("Search Options")
        options_layout = QGridLayout()

        # Pattern-specific options
        self.case_sensitive_check = QCheckBox("Case Sensitive (Regex)")
        self.whole_word_check = QCheckBox("Whole Word Only")
        self.pattern_aligned_check = QCheckBox("Alignment Required (16-byte)")

        options_layout.addWidget(self.case_sensitive_check, 0, 0)
        options_layout.addWidget(self.whole_word_check, 0, 1)
        options_layout.addWidget(self.pattern_aligned_check, 1, 0, 1, 2)

        # Context size
        options_layout.addWidget(QLabel("Context Size:"), 2, 0)
        self.context_size_spin = QSpinBox()
        self.context_size_spin.setRange(0, 256)
        self.context_size_spin.setValue(32)
        self.context_size_spin.setSuffix(" bytes")
        self.context_size_spin.setToolTip("Number of bytes to show around each match")
        options_layout.addWidget(self.context_size_spin, 2, 1)

        # Maximum results
        options_layout.addWidget(QLabel("Max Results:"), 3, 0)
        self.max_results_spin = QSpinBox()
        self.max_results_spin.setRange(1, 10000)
        self.max_results_spin.setValue(1000)
        self.max_results_spin.setToolTip("Maximum number of matches to find")
        options_layout.addWidget(self.max_results_spin, 3, 1)

        # Multiple pattern operation
        options_layout.addWidget(QLabel("Multiple Patterns:"), 4, 0)
        self.pattern_operation_combo = QComboBox()
        self.pattern_operation_combo.addItems(["Single Pattern", "OR (any match)", "AND (all match)"])
        self.pattern_operation_combo.setToolTip("How to handle multiple patterns (one per line)")
        options_layout.addWidget(self.pattern_operation_combo, 4, 1)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Pattern examples (collapsible - hidden by default to reduce clutter)
        examples_group = CollapsibleGroupBox("Pattern Examples", collapsed=True)

        examples_text = (
            "Hex Pattern Examples:\n"
            "• 00 01 02 FF - Exact bytes\n"
            "• 00 ?? ?? FF - Wildcards (any byte)\n"
            "• 10 20 ?? ?? 30 - Mixed exact and wildcards\n\n"
            "Regex Pattern Examples:\n"
            "• SNES - Find ASCII text 'SNES'\n"
            "• [A-Z]{4} - Four uppercase letters\n"
            "• \\x00\\x01.{2}\\xFF - Bytes with any 2-byte gap\n\n"
            "Multiple Patterns (one per line):\n"
            "• OR: Find any matching pattern\n"
            "• AND: Find locations with all patterns nearby"
        )

        examples_label = QLabel(examples_text)
        examples_label.setWordWrap(True)
        examples_label.setStyleSheet(f"QLabel {{ font-size: 9pt; color: {COLORS['text_muted']}; }}")
        examples_group.add_widget(examples_label)

        layout.addWidget(examples_group)

        layout.addStretch()
        return widget

    def _create_history_tab(self) -> QWidget:
        """Create search history tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # History list
        self.history_list = QListWidget()
        layout.addWidget(self.history_list)

        # History actions
        actions_layout = QHBoxLayout()

        self.clear_history_button = QPushButton("Clear History")
        self.clear_history_button.clicked.connect(self._clear_history)
        actions_layout.addWidget(self.clear_history_button)

        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        return widget

    # NOTE: _create_filters_group has been replaced by SearchFiltersWidget

    def _update_similarity_label(self, value: int):
        """Update similarity label text."""
        if self.similarity_label:
            self.similarity_label.setText(f"{value}%")

    def _focus_search(self):
        """Focus the search input field."""
        self.start_offset_edit.setFocus()

    def _show_history_tab(self):
        """Show the history tab."""
        if self.tabs:
            self.tabs.setCurrentIndex(3)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Ctrl+F - Focus search
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_search)

        # Ctrl+Enter - Start search
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(
            self._start_search
        )

        # Escape - Stop search
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            self._stop_search
        )

        # Ctrl+H - Show history
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self._show_history_tab)

    def _start_search(self):
        """Start the search based on current tab."""
        if self.search_worker is not None and self.search_worker.isRunning():
            return

        current_tab = self.tabs.currentIndex()

        if current_tab == 0:  # Parallel search
            self._start_parallel_search()
        elif current_tab == 1:  # Visual search
            self._start_visual_search()
        elif current_tab == 2:  # Pattern search
            self._start_pattern_search()

    def _start_parallel_search(self):
        """Start parallel search."""
        # Get parameters
        try:
            start = int(self.start_offset_edit.text(), 16) if self.start_offset_edit.text() else 0
            end = int(self.end_offset_edit.text(), 16) if self.end_offset_edit.text() else None
        except ValueError:
            if self.results_label:
                self.results_label.setText("Invalid offset format")
            return

        # Get filters from widget
        filters = self.filters_widget.get_filters()

        # Create worker
        params = {
            "rom_path": self.rom_path,
            "start_offset": start,
            "end_offset": end,
            "num_workers": self.workers_spin.value(),
            "step_size": self.step_size_spin.value(),
            "filters": filters
        }

        self.search_worker = SearchWorker("parallel", params)
        self._connect_worker_signals()

        # Update UI
        if self.search_button:
            self.search_button.setEnabled(False)
        if self.stop_button:
            self.stop_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        if self.results_list:
            self.results_list.clear()
        self.current_results = []
        if self.results_label:
            self.results_label.setText("Searching...")

        # Add to history
        entry = SearchHistoryEntry(
            timestamp=datetime.now(UTC),
            search_type="Parallel",
            query=f"0x{start:X} - {f'0x{end:X}' if end else 'EOF'}",
            filters=filters,
            results_count=0
        )
        self.search_history.append(entry)

        # Start search
        self.search_started.emit()
        self.search_worker.start()

    def _start_visual_search(self):
        """Start visual similarity search."""
        # Check if similarity index exists first
        if not self._check_similarity_index_exists():
            self._offer_to_build_similarity_index()
            return

        # Determine mode: offset or image file
        use_offset_mode = self.ref_mode_offset_radio.isChecked()
        ref_offset: int | None = None
        image_path: str | None = None
        query_description: str

        if use_offset_mode:
            # Get reference sprite offset
            ref_text = self.ref_offset_edit.text().strip()
            if not ref_text:
                if self.results_label:
                    self.results_label.setText("Please specify a reference sprite offset")
                return

            try:
                ref_offset = int(ref_text, 16) if ref_text.startswith("0x") else int(ref_text, 16)
            except ValueError:
                if self.results_label:
                    self.results_label.setText("Invalid offset format. Use hex format like 0x12345")
                return

            query_description = f"Similar to 0x{ref_offset:X}"
        else:
            # Get image file
            image_path = self.image_path_edit.text().strip()
            if not image_path or self._uploaded_image is None:
                if self.results_label:
                    self.results_label.setText("Please select an image file")
                return

            query_description = f"Similar to image: {Path(image_path).name}"

        # Get similarity threshold
        similarity_threshold = self.similarity_slider.value()  # Get percentage value

        # Get search scope
        search_scope = self.visual_scope_combo.currentText()

        # Create worker parameters
        params: dict[str, Any] = {  # pyright: ignore[reportExplicitAny] - Dynamic params
            "rom_path": self.rom_path,
            "similarity_threshold": similarity_threshold,
            "search_scope": search_scope,
            "max_results": 50
        }

        if use_offset_mode:
            params["reference_offset"] = ref_offset
        else:
            params["image_path"] = image_path

        self.search_worker = SearchWorker("visual", params)
        self._connect_worker_signals()

        # Update UI
        if self.search_button:
            self.search_button.setEnabled(False)
        if self.stop_button:
            self.stop_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        if self.results_list:
            self.results_list.clear()
        self.current_results = []
        if self.results_label:
            self.results_label.setText("Searching for similar sprites...")

        # Add to history
        entry = SearchHistoryEntry(
            timestamp=datetime.now(UTC),
            search_type="Visual",
            query=f"{query_description} (threshold: {similarity_threshold}%)",
            filters=SearchFilter(
                min_size=0, max_size=MAX_SPRITE_SIZE,
                min_tiles=0, max_tiles=1024,
                alignment=1,
                include_compressed=True,
                include_uncompressed=True,
                confidence_threshold=self.similarity_slider.value() / 100.0
            ),
            results_count=0
        )
        self.search_history.append(entry)

        # Start search
        self.search_started.emit()
        self.search_worker.start()

    def _start_pattern_search(self):
        """Start pattern search with comprehensive options."""
        # Get pattern input
        pattern_text = self.pattern_edit.toPlainText().strip()
        if not pattern_text:
            if self.results_label:
                self.results_label.setText("Please enter a search pattern")
            return

        # Determine pattern type
        pattern_type = "hex" if self.hex_radio.isChecked() else "regex"

        # Parse multiple patterns (one per line)
        patterns = [p.strip() for p in pattern_text.split("\n") if p.strip()]

        # Validate patterns based on type
        if pattern_type == "hex":
            for i, pattern in enumerate(patterns):
                if not self._validate_hex_pattern(pattern):
                    if self.results_label:
                        self.results_label.setText(f"Invalid hex pattern on line {i+1}: Use format like: 00 01 02 ?? FF")
                    return
        else:  # regex
            for i, pattern in enumerate(patterns):
                if not self._validate_regex_pattern(pattern):
                    if self.results_label:
                        self.results_label.setText(f"Invalid regex pattern on line {i+1}")
                    return

        # Get search options
        case_sensitive = self.case_sensitive_check.isChecked()
        alignment = self._get_pattern_alignment()

        # Create search parameters
        params = {
            "rom_path": self.rom_path,
            "patterns": patterns,
            "pattern_type": pattern_type,
            "case_sensitive": case_sensitive,
            "alignment": alignment,
            "context_bytes": self.context_size_spin.value(),
            "max_results": self.max_results_spin.value(),
            "whole_word": self.whole_word_check.isChecked(),
            "operation": self.pattern_operation_combo.currentText()
        }

        # Create worker
        self.search_worker = SearchWorker("pattern", params)
        self._connect_worker_signals()

        # Update UI
        if self.search_button:
            self.search_button.setEnabled(False)
        if self.stop_button:
            self.stop_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        if self.results_list:
            self.results_list.clear()
        self.current_results = []
        if self.results_label:
            self.results_label.setText("Searching for pattern...")

        # Add to history
        entry = SearchHistoryEntry(
            timestamp=datetime.now(UTC),
            search_type=f"Pattern ({'Hex' if pattern_type == 'hex' else 'Regex'})",
            query=pattern_text[:50] + ("..." if len(pattern_text) > 50 else ""),
            filters=SearchFilter(
                min_size=0,
                max_size=0,
                min_tiles=0,
                max_tiles=0,
                alignment=alignment,
                include_compressed=True,
                include_uncompressed=True,
                confidence_threshold=0.0
            ),
            results_count=0
        )
        self.search_history.append(entry)

        # Start search
        self.search_started.emit()
        self.search_worker.start()

    def _validate_hex_pattern(self, pattern: str) -> bool:
        """Validate hex pattern format."""
        try:
            # Clean pattern
            pattern = pattern.strip().upper()
            if not pattern:
                return False

            # Split into tokens
            tokens = re.split(r"[\s,]+", pattern)

            for token in tokens:
                if not token:
                    continue

                # Check for wildcard
                if token in ["??", "?"]:
                    continue

                # Check for valid hex byte
                if len(token) != 2 or not all(c in "0123456789ABCDEF" for c in token):
                    return False

            return len(tokens) > 0

        except Exception:
            return False

    def _validate_regex_pattern(self, pattern: str) -> bool:
        """Validate regex pattern."""
        try:
            re.compile(pattern.encode())
            return True
        except re.error:
            return False

    def _get_pattern_alignment(self) -> int:
        """Get alignment requirement for pattern search."""
        if not self.pattern_aligned_check.isChecked():
            return 1

        # Default to 16-byte alignment for pattern searches
        return 16

    def _connect_worker_signals(self):
        """Connect search worker signals."""
        if self.search_worker:
            self.search_worker.result_found.connect(self._add_result)
            self.search_worker.search_complete.connect(self._search_complete)
            self.search_worker.error.connect(self._search_error)

    def _disconnect_worker_signals(self) -> None:
        """Disconnect search worker signals before cleanup."""
        if self.search_worker:
            from contextlib import suppress
            with suppress(RuntimeError, TypeError):
                self.search_worker.result_found.disconnect(self._add_result)
                self.search_worker.search_complete.disconnect(self._search_complete)
                self.search_worker.error.disconnect(self._search_error)

    def _add_result(self, result: SearchResult):
        """Add result to list with enhanced pattern search support."""
        self.current_results.append(result)

        # Create display text based on result type
        metadata: Any = result.metadata  # pyright: ignore[reportExplicitAny] - SearchResult.metadata is dict[str, Any] at runtime
        if metadata.get("pattern_type") in ["hex", "regex"]:
            # Pattern search result
            pattern_type = str(metadata["pattern_type"]).upper()
            pattern_str = str(metadata.get("pattern", ""))
            pattern = pattern_str[:30] + ("..." if len(pattern_str) > 30 else "")
            match_data_str = str(metadata.get("match_data", ""))
            match_data = match_data_str[:20] + ("..." if len(match_data_str) > 20 else "")

            display_text = (
                f"0x{result.offset:08X} - {pattern_type} Pattern: {pattern} "
                f"(Match: {match_data}, Size: {result.size} bytes)"
            )

            # Add context information for tooltip
            context_data = str(metadata.get("context_data", ""))
            if context_data:
                context_preview = context_data[:32] + ("..." if len(context_data) > 32 else "")
                tooltip_text = (
                    f"Pattern: {metadata.get('pattern', '')}\n"
                    f"Match at: 0x{result.offset:08X}\n"
                    f"Size: {result.size} bytes\n"
                    f"Context: {context_preview}"
                )
                match_text = metadata.get("match_text")
                if match_text:
                    tooltip_text += f"\nText: {str(match_text)[:50]}"
            else:
                tooltip_text = f"Pattern match at 0x{result.offset:08X}"
        else:
            # Regular sprite search result
            display_text = (
                f"0x{result.offset:08X} - "
                f"Size: {result.size:,} bytes, "
                f"Tiles: {result.tile_count}, "
                f"Confidence: {result.confidence:.0%}"
            )
            tooltip_text = f"Sprite at 0x{result.offset:08X}"

        # Create list item
        item = QListWidgetItem(display_text)
        item.setData(Qt.ItemDataRole.UserRole, result)
        item.setToolTip(tooltip_text)
        if self.results_list:
            self.results_list.addItem(item)

        # Update count with appropriate label
        result_type = "patterns" if metadata.get("pattern_type") else "sprites"
        if self.results_label:
            self.results_label.setText(f"Found {len(self.current_results)} {result_type}")

    def _search_complete(self, results: list[Any]):  # pyright: ignore[reportExplicitAny] - SearchResult list from worker
        """Handle search completion."""
        if self.search_button:
            self.search_button.setEnabled(True)
        if self.stop_button:
            self.stop_button.setEnabled(False)
        self.progress_bar.setVisible(False)

        # Update history
        if self.search_history:
            self.search_history[-1].results_count = len(results)
            self._update_history_display()

        # For visual search, show similarity results dialog
        if (self.search_worker is not None and
            self.search_worker.search_type == "visual" and
            results):
            self._show_visual_search_results(results)

        # Update results
        if self.results_label:
            self.results_label.setText(
            f"Search complete: {len(results)} sprites found"
        )
        self.search_completed.emit(len(results))

    def _search_error(self, error_msg: str):
        """Handle search error."""
        if self.search_button:
            self.search_button.setEnabled(True)
        if self.stop_button:
            self.stop_button.setEnabled(False)
        self.progress_bar.setVisible(False)

        if self.results_label:
            self.results_label.setText(f"Search error: {error_msg}")
        logger.error(f"Search error: {error_msg}")

    def _stop_search(self):
        """Stop current search."""
        if self.search_worker is not None and self.search_worker.isRunning():
            self.search_worker.cancel()
            if self.results_label:
                self.results_label.setText("Search cancelled")

    def _on_result_selected(self, item: QListWidgetItem):
        """Handle result selection."""
        result = item.data(Qt.ItemDataRole.UserRole)
        if result:
            self.sprite_selected.emit(result.offset)

    def _browse_reference_sprite(self):
        """Browse for reference sprite (thread-safe)."""
        # For now, use a simple dialog to input an offset
        # In a full implementation, this could open a sprite browser
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QInputDialog

        # Check if we're in the main thread
        if QThread.currentThread() != self.thread():
            logger.warning("_browse_reference_sprite called from worker thread - operation skipped")
            return

        try:
            offset_text, ok = QInputDialog.getText(
                self,
                "Reference Sprite Offset",
                "Enter sprite offset (hex format):",
                text="0x"
            )

            if ok and offset_text.strip():
                try:
                    # Validate the offset format
                    if offset_text.startswith("0x"):
                        offset = int(offset_text, 16)
                    else:
                        offset = int(offset_text, 16)

                    # Set the offset in the edit field
                    if self.ref_offset_edit:
                        self.ref_offset_edit.setText(f"0x{offset:X}")

                    # Try to generate and show a preview
                    self._update_reference_preview(offset)

                except ValueError:
                    if self.results_label:
                        self.results_label.setText("Invalid offset format")
        except Exception as e:
            logger.exception(f"Error in _browse_reference_sprite: {e}")
            if self.results_label:
                self.results_label.setText(f"Error: {e}")

    def _on_ref_mode_changed(self, checked: bool) -> None:
        """Handle reference mode radio button changes."""
        if not checked:
            return  # Only handle when a button is being selected

        use_offset = self.ref_mode_offset_radio.isChecked()

        # Toggle enabled state of inputs
        self.ref_offset_edit.setEnabled(use_offset)
        self.ref_browse_button.setEnabled(use_offset)
        self.image_path_edit.setEnabled(not use_offset)
        self.image_browse_button.setEnabled(not use_offset)

        # Clear preview when switching modes
        if self.ref_preview_label:
            self.ref_preview_label.setText("No reference selected")
            self.ref_preview_label.setPixmap(QPixmap())

        # Clear stored image when switching to offset mode
        if use_offset:
            self._uploaded_image = None

    def _browse_image_file(self) -> None:
        """Browse for an image file to use as reference."""
        from PySide6.QtWidgets import QFileDialog

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Image",
            "",
            "Image Files (*.png *.bmp *.gif *.jpg *.jpeg);;All Files (*.*)"
        )

        if filename:
            self.image_path_edit.setText(filename)

    def _on_image_path_changed(self) -> None:
        """Handle changes to the image path."""
        image_path = self.image_path_edit.text().strip()
        if not image_path:
            if self.ref_preview_label:
                self.ref_preview_label.setText("No image selected")
                self.ref_preview_label.setPixmap(QPixmap())
            self._uploaded_image = None
            return

        self._load_and_validate_image(image_path)

    def _load_and_validate_image(self, path: str) -> bool:
        """Load and validate an image file.

        Args:
            path: Path to the image file

        Returns:
            True if image was loaded successfully
        """
        try:
            # Check if file exists
            image_path = Path(path)
            if not image_path.exists():
                if self.ref_preview_label:
                    self.ref_preview_label.setText("File not found")
                self._uploaded_image = None
                return False

            # Load the image
            image = Image.open(path)

            # Validate dimensions
            width, height = image.size
            if width < 8 or height < 8:
                if self.ref_preview_label:
                    self.ref_preview_label.setText(
                        f"Image too small ({width}x{height}). Minimum: 8x8"
                    )
                self._uploaded_image = None
                return False

            # Resize if too large
            max_size = 256
            if width > max_size or height > max_size:
                # Maintain aspect ratio
                if width > height:
                    new_width = max_size
                    new_height = int(height * max_size / width)
                else:
                    new_height = max_size
                    new_width = int(width * max_size / height)
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")

            # Convert to RGBA for consistent processing
            if image.mode != "RGBA":
                image = image.convert("RGBA")

            # Store the image
            self._uploaded_image = image

            # Show preview
            # Convert PIL image to QPixmap
            from io import BytesIO
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            buffer.seek(0)

            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())

            # Scale for display (max 128 pixels)
            if pixmap.width() > 128 or pixmap.height() > 128:
                pixmap = pixmap.scaled(
                    128, 128,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )

            if self.ref_preview_label:
                self.ref_preview_label.setPixmap(pixmap)
                self.ref_preview_label.setToolTip(
                    f"Image: {image_path.name}\n"
                    f"Size: {image.size[0]}x{image.size[1]}"
                )

            logger.info(f"Loaded reference image: {path} ({image.size[0]}x{image.size[1]})")
            return True

        except Exception as e:
            logger.exception(f"Error loading image: {e}")
            if self.ref_preview_label:
                self.ref_preview_label.setText(f"Error loading image: {e}")
            self._uploaded_image = None
            return False

    def _on_reference_offset_changed(self):
        """Handle changes to reference offset text."""
        offset_text = self.ref_offset_edit.text().strip()
        if not offset_text:
            if self.ref_preview_label:
                self.ref_preview_label.setText("No reference sprite selected")
                self.ref_preview_label.setPixmap(QPixmap())
            return

        try:
            # Parse offset (always base-16, "0x" prefix is optional)
            offset = int(offset_text.removeprefix("0x"), 16)

            # Update preview
            self._update_reference_preview(offset)

        except ValueError:
            if self.ref_preview_label:
                self.ref_preview_label.setText("Invalid offset format")
                self.ref_preview_label.setPixmap(QPixmap())

    def _update_reference_preview(self, offset: int):
        """Update the reference sprite preview."""
        try:
            # Create a preview request
            request = PreviewRequest(
                source_type="rom",
                data_path=self.rom_path,
                offset=offset,
                size=(128, 128)
            )

            # Generate preview using the preview service
            preview_generator = PreviewGenerator()
            result = preview_generator.generate_preview(request)

            if result and result.pixmap and not result.pixmap.isNull():
                # Scale preview to fit the label
                scaled_pixmap = result.pixmap.scaled(
                    128, 128,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                if self.ref_preview_label:
                    self.ref_preview_label.setPixmap(scaled_pixmap)
                    self.ref_preview_label.setText("")
            else:
                if self.ref_preview_label:
                    self.ref_preview_label.setText(f"Could not load sprite at 0x{offset:X}")
                    self.ref_preview_label.setPixmap(QPixmap())

        except Exception as e:
            logger.exception(f"Failed to generate reference preview: {e}")
            if self.ref_preview_label:
                self.ref_preview_label.setText(f"Preview error: {str(e)[:50]}...")
                self.ref_preview_label.setPixmap(QPixmap())

    def _show_visual_search_results(self, results: list[Any]):  # pyright: ignore[reportExplicitAny] - SearchResult list from worker
        """Show visual search results in similarity dialog."""
        try:
            # Convert SearchResult objects back to SimilarityMatch for the dialog
            ref_offset_text = self.ref_offset_edit.text().strip()
            ref_offset = int(ref_offset_text.removeprefix("0x"), 16)

            matches = []
            for result in results:
                # Runtime type is SearchResult, but typed as Any to avoid object issues
                result_typed: Any = result  # pyright: ignore[reportExplicitAny] - worker result list contains SearchResult objects
                metadata = result_typed.metadata if hasattr(result_typed, 'metadata') else {}
                match = SimilarityMatch(
                    offset=result_typed.offset,
                    similarity_score=result_typed.confidence,
                    hash_distance=int(metadata.get("hash_distance", 0)) if metadata else 0,
                    metadata=metadata or {}
                )
                matches.append(match)

            # Show similarity results dialog
            dialog = show_similarity_results(matches, ref_offset, self)
            dialog.sprite_selected.connect(self.sprite_selected.emit)
            dialog.exec()

        except Exception as e:
            logger.exception(f"Failed to show visual search results: {e}")
            if self.results_label:
                self.results_label.setText(f"Error displaying results: {e}")

    def _check_similarity_index_exists(self) -> bool:
        """Check if similarity index exists for the current ROM."""
        index_path = Path(self.rom_path).with_suffix(".similarity_index")
        return index_path.exists()

    def _offer_to_build_similarity_index(self):
        """Offer to build similarity index if it doesn't exist (thread-safe)."""
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QMessageBox

        # Check if we're in the main thread
        if QThread.currentThread() != self.thread():
            logger.warning("_offer_to_build_similarity_index called from worker thread - operation skipped")
            return

        try:
            reply = QMessageBox.question(
                self,
                "Build Similarity Index",
                "No similarity index found for this ROM. Visual search requires an index to be built first.\n\n"
                "Building an index will scan the ROM for sprites and create a searchable database. "
                "This may take several minutes but only needs to be done once per ROM.\n\n"
                "Would you like to build the similarity index now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._build_similarity_index()
        except Exception as e:
            logger.exception(f"Error in _offer_to_build_similarity_index: {e}")
            if self.results_label:
                self.results_label.setText(f"Error: {e}")

    def _build_similarity_index(self):
        """Build similarity index for the current ROM (thread-safe)."""
        # This would be implemented to scan the ROM and build the index
        # For now, show a placeholder message
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QMessageBox

        # Check if we're in the main thread
        if QThread.currentThread() != self.thread():
            logger.warning("_build_similarity_index called from worker thread - operation skipped")
            return

        try:
            QMessageBox.information(
                self,
                "Build Index",
                "Index building is not yet implemented. This feature would:\n\n"
                "1. Scan the entire ROM for sprite data\n"
                "2. Extract visual features from each sprite\n"
                "3. Build a searchable similarity index\n"
                "4. Save the index for future searches\n\n"
                "This functionality will be added in a future update."
            )
        except Exception as e:
            logger.exception(f"Error in _build_similarity_index: {e}")
            if self.results_label:
                self.results_label.setText(f"Error: {e}")

    def _clear_history(self):
        """Clear search history."""
        if self.search_history:
            self.search_history.clear()
        if self.history_list:
            self.history_list.clear()
        self._save_history()

    def _update_history_display(self):
        """Update history list display."""
        if self.history_list:
            self.history_list.clear()
        for entry in reversed(self.search_history[-20:]):  # Show last 20
            item = QListWidgetItem(entry.to_display_string())
            item.setData(Qt.ItemDataRole.UserRole, entry)
            if self.history_list:
                self.history_list.addItem(item)

    def _save_history(self):
        """Save search history to file."""
        history_file = Path.home() / ".spritepal" / "search_history.json"
        history_file.parent.mkdir(exist_ok=True)

        # Convert to serializable format
        data = []
        for entry in self.search_history[-100:]:  # Keep last 100
            data.append({
                "timestamp": entry.timestamp.isoformat(),
                "search_type": entry.search_type,
                "query": entry.query,
                "results_count": entry.results_count,
                "filters": {
                    "min_size": entry.filters.min_size,
                    "max_size": entry.filters.max_size,
                    "min_tiles": entry.filters.min_tiles,
                    "max_tiles": entry.filters.max_tiles,
                    "alignment": entry.filters.alignment,
                    "include_compressed": entry.filters.include_compressed,
                    "include_uncompressed": entry.filters.include_uncompressed,
                    "confidence_threshold": entry.filters.confidence_threshold
                }
            })

        with Path(history_file).open("w") as f:
            json.dump(data, f, indent=2)

    def _load_history(self):
        """Load search history from file."""
        history_file = Path.home() / ".spritepal" / "search_history.json"
        if not history_file.exists():
            return

        try:
            with Path(history_file).open() as f:
                data = json.load(f)

            for item in data:
                filters = SearchFilter(**item["filters"])
                entry = SearchHistoryEntry(
                    timestamp=datetime.fromisoformat(item["timestamp"]),
                    search_type=item["search_type"],
                    query=item["query"],
                    filters=filters,
                    results_count=item["results_count"]
                )
                self.search_history.append(entry)

            self._update_history_display()

        except Exception as e:
            logger.exception(f"Failed to load search history: {e}")

    @override
    def closeEvent(self, event: Any):  # pyright: ignore[reportExplicitAny] - Qt event can be QCloseEvent
        """Handle dialog close event with proper thread cleanup."""
        # Stop any running search worker using safe cleanup (never terminate)
        if self.search_worker and self.search_worker.isRunning():
            logger.debug("Stopping search worker on dialog close")
            # Disconnect signals first to prevent late signal delivery to destroyed dialog
            self._disconnect_worker_signals()
            # Use WorkerManager for safe cleanup - never uses terminate()
            WorkerManager.cleanup_worker_attr(self, "search_worker", timeout=3000)
            logger.debug("Search worker cleanup completed")

        # Save history before closing
        try:
            self._save_history()
        except Exception as e:
            logger.exception(f"Failed to save search history on close: {e}")

        # Accept the close event
        event.accept()
