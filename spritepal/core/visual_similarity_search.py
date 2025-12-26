"""
Visual similarity search for sprites using perceptual hashing.

This module enables finding visually similar sprites across ROMs,
useful for finding variations, palette swaps, or related graphics.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from utils.constants import ROM_ALIGNMENT_GAP_THRESHOLD

logger = logging.getLogger(__name__)


@dataclass
class SpriteHash:
    """Container for sprite perceptual hash data."""

    offset: int
    phash: np.ndarray
    dhash: np.ndarray
    histogram: np.ndarray
    metadata: dict[str, Any]  # pyright: ignore[reportExplicitAny] - sprite metadata can contain various types


@dataclass
class SimilarityMatch:
    """Result of similarity search."""

    offset: int
    similarity_score: float
    hash_distance: int
    metadata: dict[str, Any]  # pyright: ignore[reportExplicitAny] - sprite metadata can contain various types


class VisualSimilarityEngine:
    """
    Engine for finding visually similar sprites using multiple techniques.

    Combines perceptual hashing, color histograms, and structural analysis
    for robust similarity matching.
    """

    def __init__(self, hash_size: int = 8):
        """
        Initialize similarity engine.

        Args:
            hash_size: Size of hash (8 produces 64-bit hash)
        """
        self.hash_size = hash_size
        self.sprite_database = {}  # offset -> SpriteHash
        self.index_built = False

        logger.info(f"Initialized VisualSimilarityEngine with hash_size={hash_size}")

    def index_sprite(self, offset: int, image: Image.Image, metadata: dict[str, Any] | None = None) -> SpriteHash:  # pyright: ignore[reportExplicitAny] - sprite metadata can contain various types
        """
        Index a sprite for similarity search.

        Args:
            offset: ROM offset of sprite
            image: PIL Image of the sprite
            metadata: Optional metadata about the sprite

        Returns:
            SpriteHash object
        """
        # Generate multiple hashes for robust matching
        phash = self._calculate_phash(image)
        dhash = self._calculate_dhash(image)
        histogram = self._calculate_color_histogram(image)

        sprite_hash = SpriteHash(offset=offset, phash=phash, dhash=dhash, histogram=histogram, metadata=metadata or {})

        self.sprite_database[offset] = sprite_hash
        logger.debug(f"Indexed sprite at offset 0x{offset:X}")

        return sprite_hash

    def find_similar(
        self, target: Image.Image | int, max_results: int = 10, similarity_threshold: float = 0.8
    ) -> list[SimilarityMatch]:
        """
        Find sprites similar to target.

        Args:
            target: Either a PIL Image or offset of indexed sprite
            max_results: Maximum number of results to return
            similarity_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of similar sprites sorted by similarity
        """
        # Get target hashes
        if isinstance(target, int):
            # Use existing indexed sprite
            if target not in self.sprite_database:
                raise ValueError(f"Sprite at offset 0x{target:X} not indexed")
            target_hash = self.sprite_database[target]
        else:
            # Calculate hashes for new image
            target_hash = SpriteHash(
                offset=-1,
                phash=self._calculate_phash(target),
                dhash=self._calculate_dhash(target),
                histogram=self._calculate_color_histogram(target),
                metadata={},
            )

        # Search database
        matches = []

        for offset, sprite_hash in self.sprite_database.items():
            # Skip self-comparison
            if offset == target_hash.offset:
                continue

            # Calculate similarity
            similarity = self._calculate_similarity(target_hash, sprite_hash)

            if similarity >= similarity_threshold:
                match = SimilarityMatch(
                    offset=offset,
                    similarity_score=similarity,
                    hash_distance=self._hamming_distance(target_hash.phash, sprite_hash.phash),
                    metadata=sprite_hash.metadata,
                )
                matches.append(match)

        # Sort by similarity and limit results
        matches.sort(key=lambda x: x.similarity_score, reverse=True)
        return matches[:max_results]

    def _calculate_phash(self, image: Image.Image) -> np.ndarray:
        """
        Calculate perceptual hash using a simplified approach.

        Resistant to scaling and minor changes.
        Uses average hash instead of DCT for simplicity.
        """
        # Convert to grayscale and resize
        img = image.convert("L").resize((self.hash_size, self.hash_size), Image.Resampling.LANCZOS)

        # Convert to numpy array
        pixels = np.array(img, dtype=np.float32)

        # Calculate average
        avg = np.mean(pixels)

        # Generate hash based on average
        return (pixels > avg).flatten().astype(np.uint8)

    def _calculate_dhash(self, image: Image.Image) -> np.ndarray:
        """
        Calculate difference hash.

        Good for detecting similar structures.
        """
        # Resize to hash_size + 1 width
        img = image.convert("L").resize((self.hash_size + 1, self.hash_size), Image.Resampling.LANCZOS)

        pixels = np.array(img, dtype=np.float32)

        # Calculate horizontal differences
        diff = pixels[:, 1:] > pixels[:, :-1]

        return diff.flatten().astype(np.uint8)

    def _calculate_color_histogram(self, image: Image.Image) -> np.ndarray:
        """
        Calculate normalized color histogram.

        Captures color distribution information.
        """
        # Convert to RGB if needed
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Calculate histogram for each channel
        hist_r = np.histogram(np.array(image)[:, :, 0], bins=16, range=(0, 256))[0]
        hist_g = np.histogram(np.array(image)[:, :, 1], bins=16, range=(0, 256))[0]
        hist_b = np.histogram(np.array(image)[:, :, 2], bins=16, range=(0, 256))[0]

        # Concatenate and normalize
        histogram = np.concatenate([hist_r, hist_g, hist_b])
        histogram = histogram.astype(np.float32)
        histogram /= histogram.sum() + 1e-6  # Avoid division by zero

        return histogram

    def _calculate_similarity(self, hash1: SpriteHash, hash2: SpriteHash) -> float:
        """
        Calculate overall similarity score between two sprites.

        Combines multiple metrics for robust comparison.
        """
        # Perceptual hash similarity (40% weight)
        phash_distance = self._hamming_distance(hash1.phash, hash2.phash)
        phash_similarity = 1.0 - (phash_distance / len(hash1.phash))

        # Difference hash similarity (30% weight)
        dhash_distance = self._hamming_distance(hash1.dhash, hash2.dhash)
        dhash_similarity = 1.0 - (dhash_distance / len(hash1.dhash))

        # Color histogram similarity (30% weight)
        hist_similarity = self._histogram_similarity(hash1.histogram, hash2.histogram)

        # Weighted combination
        return phash_similarity * 0.4 + dhash_similarity * 0.3 + hist_similarity * 0.3

    def _hamming_distance(self, hash1: np.ndarray, hash2: np.ndarray) -> int:
        """Calculate Hamming distance between two hashes."""
        return np.sum(hash1 != hash2)

    def _histogram_similarity(self, hist1: np.ndarray, hist2: np.ndarray) -> float:
        """
        Calculate histogram similarity using intersection method.

        Returns value between 0.0 and 1.0.
        """
        intersection = np.minimum(hist1, hist2).sum()
        return float(intersection)

    def build_similarity_index(self):
        """
        Build optimized index for fast similarity search.

        Uses LSH (Locality Sensitive Hashing) for approximate nearest neighbor.
        """
        if not self.sprite_database:
            logger.warning("No sprites indexed, cannot build similarity index")
            return

        # TODO: Implement LSH index for very large databases
        # For now, brute force search is sufficient for typical ROM sizes

        self.index_built = True
        logger.info(f"Built similarity index for {len(self.sprite_database)} sprites")

    def export_index(self, path: Path):
        """Export similarity index to file for persistence."""

        export_data = {"hash_size": self.hash_size, "database": self.sprite_database, "index_built": self.index_built}

        with Path(path).open("wb") as f:
            pickle.dump(export_data, f)

        logger.info(f"Exported similarity index to {path}")

    def import_index(self, path: Path):
        """Import previously saved similarity index."""

        with Path(path).open("rb") as f:
            data = pickle.load(f)

        self.hash_size = data["hash_size"]
        self.sprite_database = data["database"]
        self.index_built = data["index_built"]

        logger.info(f"Imported similarity index with {len(self.sprite_database)} sprites")


class SpriteGroupFinder:
    """
    Find groups of related sprites (animations, variations).

    Uses similarity search to identify sprite families.
    """

    def __init__(self, similarity_engine: VisualSimilarityEngine):
        self.engine = similarity_engine
        self.groups: list[list[int]] = []  # List of sprite groups

    def find_sprite_groups(self, similarity_threshold: float = 0.85, min_group_size: int = 2) -> list[list[int]]:
        """
        Find groups of similar sprites.

        Returns:
            List of groups, each group is a list of sprite offsets
        """
        processed = set()
        groups = []

        for offset in self.engine.sprite_database:
            if offset in processed:
                continue

            # Find all sprites similar to this one
            similar = self.engine.find_similar(offset, max_results=50, similarity_threshold=similarity_threshold)

            if len(similar) >= min_group_size - 1:
                group = [offset] + [match.offset for match in similar]
                groups.append(group)
                processed.update(group)

        # Sort groups by size
        groups.sort(key=len, reverse=True)

        logger.info(f"Found {len(groups)} sprite groups")
        return groups

    def find_animations(
        self, offset_proximity: int = ROM_ALIGNMENT_GAP_THRESHOLD, similarity_threshold: float = 0.9
    ) -> list[list[int]]:
        """
        Find animation sequences based on proximity and similarity.

        Args:
            offset_proximity: Maximum distance between animation frames
            similarity_threshold: Minimum similarity for animation frames

        Returns:
            List of animation sequences
        """
        animations = []
        processed = set()

        # Sort sprites by offset
        sorted_offsets = sorted(self.engine.sprite_database.keys())

        for i, offset in enumerate(sorted_offsets):
            if offset in processed:
                continue

            animation = [offset]
            current_offset = offset

            # Look for subsequent similar sprites
            for j in range(i + 1, len(sorted_offsets)):
                next_offset = sorted_offsets[j]

                # Check proximity
                if next_offset - current_offset > offset_proximity:
                    break

                # Check similarity
                similar = self.engine.find_similar(
                    current_offset, max_results=10, similarity_threshold=similarity_threshold
                )

                if any(match.offset == next_offset for match in similar):
                    animation.append(next_offset)
                    current_offset = next_offset
                    processed.add(next_offset)

            if len(animation) >= 2:
                animations.append(animation)

        logger.info(f"Found {len(animations)} animation sequences")
        return animations
