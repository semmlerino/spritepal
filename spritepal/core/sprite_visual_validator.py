"""
Visual sprite validation to distinguish real character sprites from garbage data
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from utils.logging_config import get_logger

if TYPE_CHECKING:
    import cv2  # type: ignore[import-not-found]
else:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        cv2 = None

logger = get_logger(__name__)

class SpriteVisualValidator:
    """Validates if image data contains actual character sprites vs garbage pixels"""

    def __init__(self) -> None:
        self.tile_size: int = 8  # 8x8 pixel tiles

    def validate_sprite_image(self, image_path: str) -> tuple[bool, float, dict[str, float]]:
        """
        Validate if an image contains real sprite data.

        Returns:
            Tuple of (is_valid, confidence_score, metrics_dict)
        """
        try:
            # Load image with context manager to prevent resource leak
            with Image.open(image_path) as img:
                img_gray = img.convert("L")  # Convert to grayscale
                img_array = np.array(img_gray)

            # Calculate various metrics
            metrics = {}

            # 1. Coherence score - do pixels form coherent shapes?
            metrics["coherence"] = self._calculate_coherence_score(img_array)

            # 2. Tile diversity - are tiles different from each other?
            metrics["tile_diversity"] = self._calculate_tile_diversity(img_array)

            # 3. Edge detection - do we have clear edges/outlines?
            metrics["edge_score"] = self._calculate_edge_score(img_array)

            # 4. Symmetry detection - character sprites often have symmetry
            metrics["symmetry"] = self._calculate_symmetry_score(img_array)

            # 5. Empty space ratio - sprites have organized empty space
            metrics["empty_space"] = self._calculate_empty_space_ratio(img_array)

            # 6. Pattern regularity - sprites have regular patterns, not noise
            metrics["pattern_regularity"] = self._calculate_pattern_regularity(img_array)

            # Calculate overall score
            confidence = self._calculate_overall_confidence(metrics)
            is_valid = confidence > 0.5

            logger.info(f"Sprite validation: valid={is_valid}, confidence={confidence:.3f}")
            logger.debug(f"Metrics: {metrics}")

        except Exception:
            logger.exception("Failed to validate sprite image")
            return False, 0.0, {}
        else:
            return is_valid, confidence, metrics

    def _calculate_coherence_score(self, img_array: np.ndarray) -> float:
        """
        Calculate how coherent the shapes in the image are.
        Uses connected component analysis.
        """
        if cv2 is None:
            # Fallback: simple coherence based on non-zero pixels
            non_zero = np.count_nonzero(img_array > 0)
            total = img_array.size
            ratio = non_zero / total
            # Good sprites have 20-80% non-zero pixels
            if 0.2 <= ratio <= 0.8:
                return float(0.5 + (0.5 - abs(ratio - 0.5)))
            return 0.2

        # Threshold to binary
        _, binary = cv2.threshold(img_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Find connected components
        num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

        # Filter out very small components (noise)
        min_area = 16  # At least 4x4 pixels
        valid_components = 0
        total_area = 0

        for i in range(1, num_labels):  # Skip background (0)
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= min_area:
                valid_components += 1
                total_area += area

        # Score based on having reasonable number of coherent components
        if valid_components == 0:
            return 0.0

        # Ideal range: 10-100 components for a sprite sheet
        component_score = min(valid_components / 50.0, 1.0)

        # Components should cover reasonable portion of image
        coverage = total_area / (img_array.shape[0] * img_array.shape[1])
        coverage_score = min(coverage * 2, 1.0)  # 50% coverage is ideal

        return (component_score + coverage_score) / 2

    def _calculate_tile_diversity(self, img_array: np.ndarray) -> float:
        """
        Calculate diversity of tiles - real sprites have varied but not random tiles.
        """
        height, width = img_array.shape
        tile_size = self.tile_size

        tiles = []
        for y in range(0, height - tile_size + 1, tile_size):
            for x in range(0, width - tile_size + 1, tile_size):
                tile = img_array[y:y+tile_size, x:x+tile_size]
                tiles.append(tile.flatten())

        if not tiles:
            return 0.0

        tiles = np.array(tiles)

        # Calculate unique tiles (with some tolerance for minor differences)
        unique_tiles = []
        for tile in tiles:
            is_unique = True
            for unique_tile in unique_tiles:
                if np.sum(np.abs(tile - unique_tile)) < 50:  # Tolerance
                    is_unique = False
                    break
            if is_unique:
                unique_tiles.append(tile)

        # Score based on diversity ratio
        diversity_ratio = len(unique_tiles) / len(tiles)

        # Too low = repetitive, too high = random noise
        if diversity_ratio < 0.1:
            return diversity_ratio * 5  # Penalize very repetitive
        if diversity_ratio > 0.9:
            return 1.0 - diversity_ratio  # Penalize too random
        return 0.5 + (0.5 - abs(diversity_ratio - 0.5))  # Peak at 0.5

    def _calculate_edge_score(self, img_array: np.ndarray) -> float:
        """
        Calculate edge score - sprites have clear outlines.
        """
        if cv2 is None:
            # Fallback: use simple gradient
            dy, dx = np.gradient(img_array.astype(float))
            edge_strength = np.sqrt(dx**2 + dy**2)
            edge_pixels = np.sum(edge_strength > 20)
            total_pixels = img_array.size
            edge_ratio = edge_pixels / total_pixels
            # Good edge ratio is between 5-30%
            if 0.05 <= edge_ratio <= 0.3:
                return 0.5 + (0.25 - abs(edge_ratio - 0.175)) * 2
            return 0.3

        # Apply edge detection
        edges = cv2.Canny(img_array, 50, 150)

        # Calculate edge density
        edge_pixels = np.sum(edges > 0)
        total_pixels = edges.shape[0] * edges.shape[1]
        edge_density = edge_pixels / total_pixels

        # Ideal edge density for sprites: 5-20%
        if edge_density < 0.05:
            return edge_density * 10
        if edge_density > 0.3:
            return 1.0 - edge_density
        return 0.5 + (0.5 - abs(edge_density - 0.125) * 4)

    def _calculate_symmetry_score(self, img_array: np.ndarray) -> float:
        """
        Calculate symmetry - many character sprites have vertical symmetry.
        """
        _height, width = img_array.shape

        # Check vertical symmetry
        left_half = img_array[:, :width//2]
        right_half = img_array[:, width//2:]
        right_half_flipped = np.fliplr(right_half)

        # Resize to same size if needed
        min_width = min(left_half.shape[1], right_half_flipped.shape[1])
        left_half = left_half[:, :min_width]
        right_half_flipped = right_half_flipped[:, :min_width]

        # Calculate similarity
        diff = np.abs(left_half.astype(float) - right_half_flipped.astype(float))
        symmetry_score = 1.0 - (float(np.mean(diff)) / 255.0)

        # Don't require perfect symmetry - partial is good
        return float(min(symmetry_score * 1.5, 1.0))

    def _calculate_empty_space_ratio(self, img_array: np.ndarray) -> float:
        """
        Calculate empty space ratio - sprites have organized empty space.
        """
        # Count zero/near-zero pixels
        empty_pixels = np.sum(img_array < 10)
        total_pixels = img_array.shape[0] * img_array.shape[1]
        empty_ratio = empty_pixels / total_pixels

        # Ideal empty space: 30-70%
        if empty_ratio < 0.3:
            return empty_ratio / 0.3
        if empty_ratio > 0.7:
            return (1.0 - empty_ratio) / 0.3
        return 1.0

    def _calculate_pattern_regularity(self, img_array: np.ndarray) -> float:
        """
        Calculate pattern regularity using autocorrelation.
        """
        if cv2 is None:
            # Fallback: simple tile-based analysis
            h, w = img_array.shape
            tile_scores = []
            for y in range(0, h-8, 8):
                for x in range(0, w-8, 8):
                    tile = img_array[y:y+8, x:x+8]
                    # Check if tile has structure
                    if np.std(tile) > 10:
                        tile_scores.append(1)
                    else:
                        tile_scores.append(0)
            if tile_scores:
                return float(np.mean(tile_scores))
            return 0.3

        # Downsample for performance
        small = cv2.resize(img_array, (64, 64))

        # Calculate 2D autocorrelation
        f = np.fft.fft2(small)
        power = np.abs(f) ** 2
        autocorr = np.fft.ifft2(power).real
        autocorr = np.fft.fftshift(autocorr)

        # Normalize
        autocorr = autocorr / np.max(autocorr)

        # Look for regular peaks (excluding center)
        center = autocorr.shape[0] // 2
        autocorr[center-2:center+2, center-2:center+2] = 0

        # Find peaks
        peaks = autocorr > 0.3
        num_peaks = np.sum(peaks)

        # Score based on having some but not too many peaks
        if num_peaks < 5 or num_peaks > 50:
            return 0.2
        return float(0.5 + 0.5 * (1.0 - abs(num_peaks - 20) / 20))

    def _calculate_overall_confidence(self, metrics: dict[str, float]) -> float:
        """
        Calculate overall confidence score from individual metrics.
        """
        # Weighted average of metrics
        weights = {
            "coherence": 0.25,
            "tile_diversity": 0.20,
            "edge_score": 0.20,
            "symmetry": 0.10,
            "empty_space": 0.15,
            "pattern_regularity": 0.10
        }

        total_score = 0.0
        total_weight = 0.0

        for metric, value in metrics.items():
            if metric in weights:
                total_score += value * weights[metric]
                total_weight += weights[metric]

        if total_weight > 0:
            return total_score / total_weight
        return 0.0

    def validate_tile_data(self, tile_data: bytes, tile_count: int) -> tuple[bool, float]:
        """
        Validate raw tile data before conversion to image.
        """
        # Quick validation based on data patterns
        if len(tile_data) != tile_count * 32:  # 32 bytes per 4bpp tile
            return False, 0.0

        # Check for all zeros or all ones (common in garbage data)
        unique_bytes = len(set(tile_data))
        if unique_bytes < 10:  # Too uniform
            return False, 0.1

        # Check for reasonable byte distribution
        byte_counts = np.bincount(np.frombuffer(tile_data, dtype=np.uint8), minlength=256)
        entropy = -np.sum((byte_counts/len(tile_data)) * np.log2(byte_counts/len(tile_data) + 1e-10))

        # Sprite data typically has entropy in range 4-7
        if entropy < 3 or entropy > 7.5:
            return False, 0.2

        return True, 0.8
