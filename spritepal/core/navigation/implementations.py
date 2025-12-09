"""
Concrete implementations of navigation strategies.

Provides working implementations of different navigation algorithms
including linear, pattern-based, similarity, and hybrid approaches.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Any

from typing_extensions import override

from utils.logging_config import get_logger

from .data_structures import (
    NavigationContext,
    NavigationHint,
    NavigationStrategy,
    RegionType,
    SpriteLocation,
)
from .intelligence import OffsetPredictor, PatternAnalyzer, SimilarityEngine
from .strategies import (
    AbstractNavigationStrategy,
    AbstractPatternStrategy,
    AbstractSimilarityStrategy,
)

if TYPE_CHECKING:
    from .region_map import SpriteRegionMap

logger = get_logger(__name__)

class LinearNavigationStrategy(AbstractNavigationStrategy):
    """
    Linear navigation strategy that mimics traditional sequential scanning.

    Provides compatibility with existing linear search patterns while
    offering intelligent step size optimization.
    """

    def __init__(self) -> None:
        super().__init__("Linear")
        self.default_step = 0x40  # Default step size
        self.adaptive_stepping = True

    @override
    def find_next_sprites(
        self,
        context: NavigationContext,
        region_map: SpriteRegionMap,
        rom_data: bytes | None = None
    ) -> list[NavigationHint]:
        """Find next sprites using linear scanning approach."""
        hints = []

        # Determine step size based on region characteristics
        step_size = self._calculate_optimal_step_size(context, region_map)

        # Generate linear predictions
        for i in range(1, min(context.max_hints + 1, 20)):  # Generate up to 20 candidates
            predicted_offset = context.current_offset + (step_size * i)

            # Skip if we've been here recently
            if predicted_offset in context.recently_visited:
                continue

            # Check if this offset makes sense based on known sprites
            confidence = self._calculate_linear_confidence(predicted_offset, region_map, context)

            if confidence >= 0.3:  # Minimum threshold for linear strategy
                hint = NavigationHint(
                    target_offset=predicted_offset,
                    confidence=confidence,
                    reasoning=f"Linear scan: step size {step_size}",
                    strategy_used=NavigationStrategy.LINEAR,
                    expected_region_type=self._predict_region_type(predicted_offset, region_map),
                    priority=0.4  # Medium priority for linear approach
                )
                hints.append(hint)

        return hints[:context.max_hints]

    @override
    def learn_from_discovery(self, hint: NavigationHint, actual_location: SpriteLocation | None) -> None:
        """Learn from discovery results to optimize step sizes."""
        success = actual_location is not None
        self._update_statistics(success)

        if success and self.adaptive_stepping:
            # Adjust step size based on success patterns
            logger.debug(f"Linear strategy success at offset {hint.target_offset:08X}")

    @override
    def get_confidence_estimate(self, context: NavigationContext) -> float:
        """Linear strategy has consistent moderate confidence."""
        return 0.5  # Always moderate confidence

    def _calculate_optimal_step_size(self, context: NavigationContext, region_map: SpriteRegionMap) -> int:
        """Calculate optimal step size based on local sprite density."""
        if not self.adaptive_stepping:
            return self.default_step

        # Find nearby sprites to estimate density
        nearby_sprites = region_map.find_nearest_sprites(context.current_offset, count=5, max_distance=0x1000)

        if len(nearby_sprites) < 2:
            return self.default_step

        # Calculate average spacing between nearby sprites
        distances = [distance for _, distance in nearby_sprites]
        avg_distance = statistics.mean(distances)

        # Adaptive step size based on local density
        if avg_distance < 0x20:
            return 0x10  # Dense area, small steps
        if avg_distance < 0x100:
            return 0x40  # Medium density
        return 0x80  # Sparse area, larger steps

    def _calculate_linear_confidence(
        self,
        offset: int,
        region_map: SpriteRegionMap,
        context: NavigationContext
    ) -> float:
        """Calculate confidence for a linear prediction."""
        base_confidence = 0.5

        # Reduce confidence if we're in a known gap
        gaps = region_map.get_gaps(min_size=100)
        in_gap = any(start <= offset <= end for start, end in gaps)

        if in_gap:
            base_confidence += 0.2  # Gaps are more likely to have sprites

        # Reduce confidence if too close to current position
        distance = abs(offset - context.current_offset)
        if distance < 0x20:
            base_confidence -= 0.3

        # Check if in favorite region
        if context.is_in_favorite_region(offset):
            base_confidence += 0.1

        return max(0.0, min(1.0, base_confidence))

    def _predict_region_type(self, offset: int, region_map: SpriteRegionMap) -> RegionType:
        """Predict region type based on nearby sprites."""
        nearby_sprites = region_map.find_nearest_sprites(offset, count=3, max_distance=0x1000)

        if not nearby_sprites:
            return RegionType.UNKNOWN

        # Use most common region type among nearby sprites
        region_types = [sprite.region_type for sprite, _ in nearby_sprites]
        return Counter(region_types).most_common(1)[0][0]

class PatternBasedStrategy(AbstractPatternStrategy):
    """
    Pattern-based navigation using learned sprite organization patterns.

    Analyzes sprite placement patterns and uses them to predict
    likely locations for undiscovered sprites.
    """

    def __init__(self) -> None:
        super().__init__("PatternBased")
        self.pattern_analyzer = PatternAnalyzer()
        self.offset_predictor = OffsetPredictor()
        self.min_sprites_for_analysis = 5

    @override
    def find_next_sprites(
        self,
        context: NavigationContext,
        region_map: SpriteRegionMap,
        rom_data: bytes | None = None
    ) -> list[NavigationHint]:
        """Find sprites based on learned patterns."""
        if len(region_map) < self.min_sprites_for_analysis:
            return []  # Not enough data for pattern analysis

        # Extract current patterns
        current_patterns = self._extract_patterns(region_map)

        # Update stored patterns
        self._patterns.update(current_patterns)

        # Generate predictions based on patterns
        hints = self._apply_patterns(current_patterns, context)

        # Use offset predictor for additional predictions
        comprehensive_analysis = self.pattern_analyzer.get_comprehensive_analysis(region_map)
        predicted_hints = self.offset_predictor.predict_next_locations(
            context.current_offset,
            region_map,
            comprehensive_analysis,
            max_predictions=context.max_hints
        )

        # Combine and deduplicate hints
        all_hints = hints + predicted_hints
        unique_hints = self._deduplicate_hints(all_hints)

        # Sort by confidence and return top results
        sorted_hints = sorted(unique_hints, key=lambda h: h.confidence, reverse=True)
        return sorted_hints[:context.max_hints]

    @override
    def learn_from_discovery(self, hint: NavigationHint, actual_location: SpriteLocation | None) -> None:
        """Learn from discovery results to improve patterns."""
        success = actual_location is not None
        self._update_statistics(success)

        if success and self._learning_enabled:
            # Update pattern weights based on successful predictions
            strategy_used = hint.strategy_used
            if strategy_used == NavigationStrategy.PATTERN_BASED:
                logger.debug(f"Pattern-based success: {hint.reasoning}")

    @override
    def get_confidence_estimate(self, context: NavigationContext) -> float:
        """Estimate confidence based on pattern strength."""
        if not self._patterns:
            return 0.2  # Low confidence without patterns

        # Calculate confidence based on pattern consistency
        overall_confidence = 0.5

        if "spacing" in self._patterns:
            spacing_confidence = self._patterns["spacing"].get("confidence", 0.0)
            overall_confidence = max(overall_confidence, spacing_confidence)

        if "sizes" in self._patterns:
            size_confidence = self._patterns["sizes"].get("confidence", 0.0)
            overall_confidence = max(overall_confidence, size_confidence)

        return min(overall_confidence, 0.9)  # Cap at 90% confidence

    @override
    def _extract_patterns(self, region_map: SpriteRegionMap) -> dict[str, Any]:
        """Extract comprehensive patterns from region map."""
        return self.pattern_analyzer.get_comprehensive_analysis(region_map)

    @override
    def _apply_patterns(self, patterns: dict[str, Any], context: NavigationContext) -> list[NavigationHint]:
        """Apply learned patterns to generate navigation hints."""
        hints = []

        # Spacing pattern hints
        if "spacing" in patterns:
            spacing_hints = self._apply_spacing_patterns(patterns["spacing"], context)
            hints.extend(spacing_hints)

        # Size pattern hints
        if "sizes" in patterns:
            size_hints = self._apply_size_patterns(patterns["sizes"], context)
            hints.extend(size_hints)

        # Region pattern hints
        if "regions" in patterns:
            region_hints = self._apply_region_patterns(patterns["regions"], context)
            hints.extend(region_hints)

        return hints

    def _apply_spacing_patterns(self, spacing_data: dict[str, Any], context: NavigationContext) -> list[NavigationHint]:
        """Generate hints based on spacing patterns."""
        hints = []

        common_distances = spacing_data.get("common_distances", [])
        confidence_base = spacing_data.get("confidence", 0.5)

        for distance, frequency in common_distances[:3]:  # Top 3 spacing patterns
            predicted_offset = context.current_offset + distance

            # Calculate confidence based on pattern strength
            total_frequency = sum(freq for _, freq in common_distances)
            pattern_strength = frequency / total_frequency if total_frequency > 0 else 0
            confidence = confidence_base * pattern_strength * 0.8  # Scale for spacing patterns

            hint = NavigationHint(
                target_offset=predicted_offset,
                confidence=confidence,
                reasoning=f"Spacing pattern: {distance} bytes (occurs {frequency} times)",
                strategy_used=NavigationStrategy.PATTERN_BASED,
                expected_region_type=RegionType.UNKNOWN,
                pattern_strength=pattern_strength,
                priority=0.7
            )
            hints.append(hint)

        return hints

    def _apply_size_patterns(self, size_data: dict[str, Any], context: NavigationContext) -> list[NavigationHint]:
        """Generate hints based on size patterns."""
        return []

        # This would analyze gaps that could fit common sprite sizes
        # Implementation would be similar to spacing patterns

    def _apply_region_patterns(self, region_data: dict[str, Any], context: NavigationContext) -> list[NavigationHint]:
        """Generate hints based on region organization patterns."""
        hints = []

        high_density_regions = region_data.get("high_density_regions", [])
        region_analysis = region_data.get("region_analysis", {})

        # Generate hints for high-density regions
        for region_id in high_density_regions:
            region_info = region_analysis.get(region_id, {})
            if not region_info:
                continue

            region_start = region_info["start_offset"]
            region_end = region_info["end_offset"]

            # Skip current region
            current_region = context.current_offset // 0x10000
            if region_id == current_region:
                continue

            # Predict in middle of high-density region
            predicted_offset = region_start + (region_end - region_start) // 2

            confidence = region_data.get("confidence", 0.5) * region_info.get("density", 0.1)

            hint = NavigationHint(
                target_offset=predicted_offset,
                confidence=confidence,
                reasoning=f"High-density region {region_id} (density: {region_info.get('density', 0):.3f})",
                strategy_used=NavigationStrategy.PATTERN_BASED,
                expected_region_type=RegionType.HIGH_DENSITY,
                priority=0.8
            )
            hints.append(hint)

        return hints

    def _deduplicate_hints(self, hints: list[NavigationHint]) -> list[NavigationHint]:
        """Remove duplicate hints, keeping highest confidence."""
        offset_map = {}

        for hint in hints:
            offset = hint.target_offset
            if offset not in offset_map or hint.confidence > offset_map[offset].confidence:
                offset_map[offset] = hint

        return list(offset_map.values())

class SimilarityStrategy(AbstractSimilarityStrategy):
    """
    Similarity-based navigation using content analysis.

    Finds sprites similar to recently discovered ones and predicts
    locations of related sprites based on content similarity.
    """

    def __init__(self) -> None:
        super().__init__("Similarity")
        self.similarity_engine = SimilarityEngine()
        self.reference_sprites: list[SpriteLocation] = []
        self.max_reference_sprites = 10

    @override
    def find_next_sprites(
        self,
        context: NavigationContext,
        region_map: SpriteRegionMap,
        rom_data: bytes | None = None
    ) -> list[NavigationHint]:
        """Find sprites based on similarity to known sprites."""
        if len(region_map) < 2:
            return []  # Need at least 2 sprites for similarity comparison

        hints = []

        # Get recent sprites as references
        recent_sprites = self._get_reference_sprites(context, region_map)

        for reference_sprite in recent_sprites:
            # Find similar sprites
            similar_sprites = self.similarity_engine.find_similar_sprites(
                reference_sprite,
                region_map,
                min_similarity=self._similarity_threshold
            )

            # Generate hints based on similar sprite patterns
            similarity_hints = self._generate_similarity_hints(
                reference_sprite,
                similar_sprites,
                context
            )
            hints.extend(similarity_hints)

        # Remove duplicates and sort by confidence
        unique_hints = self._deduplicate_hints(hints)
        sorted_hints = sorted(unique_hints, key=lambda h: h.confidence, reverse=True)

        return sorted_hints[:context.max_hints]

    @override
    def learn_from_discovery(self, hint: NavigationHint, actual_location: SpriteLocation | None) -> None:
        """Learn from discovery results to improve similarity matching."""
        success = actual_location is not None
        self._update_statistics(success)

        if success and actual_location:
            # Add to reference sprites for future similarity comparisons
            self.reference_sprites.append(actual_location)

            # Keep only recent reference sprites
            if len(self.reference_sprites) > self.max_reference_sprites:
                self.reference_sprites = self.reference_sprites[-self.max_reference_sprites:]

            logger.debug(f"Added reference sprite for similarity: 0x{actual_location.offset:06X}")

    @override
    def get_confidence_estimate(self, context: NavigationContext) -> float:
        """Estimate confidence based on similarity data quality."""
        if not self.reference_sprites:
            return 0.3  # Low confidence without reference sprites

        # Higher confidence with more reference data
        ref_count_factor = min(1.0, len(self.reference_sprites) / self.max_reference_sprites)
        return 0.4 + (ref_count_factor * 0.4)

    @override
    def _calculate_similarity(self, sprite1: SpriteLocation, sprite2: SpriteLocation) -> float:
        """Calculate similarity between two sprites."""
        return self.similarity_engine.calculate_similarity(sprite1, sprite2)

    @override
    def _find_similar_sprites(
        self,
        target_sprite: SpriteLocation,
        region_map: SpriteRegionMap
    ) -> list[tuple[SpriteLocation, float]]:
        """Find sprites similar to target sprite."""
        return self.similarity_engine.find_similar_sprites(
            target_sprite,
            region_map,
            min_similarity=self._similarity_threshold
        )

    def _get_reference_sprites(self, context: NavigationContext, region_map: SpriteRegionMap) -> list[SpriteLocation]:
        """Get reference sprites for similarity comparison."""
        references = []

        # Use stored reference sprites
        references.extend(self.reference_sprites)

        # Add recently visited sprites
        for offset in context.recently_visited[:5]:
            sprite = region_map.get_sprite(offset)
            if sprite and sprite not in references:
                references.append(sprite)

        return references[:self.max_reference_sprites]

    def _generate_similarity_hints(
        self,
        reference_sprite: SpriteLocation,
        similar_sprites: list[tuple[SpriteLocation, float]],
        context: NavigationContext
    ) -> list[NavigationHint]:
        """Generate navigation hints based on sprite similarities."""
        hints = []

        if not similar_sprites:
            return hints

        # Analyze patterns in similar sprite locations
        similar_offsets = [sprite.offset for sprite, _ in similar_sprites]

        # Look for patterns in similar sprite spacing
        if len(similar_offsets) >= 2:
            # Calculate potential next locations based on similar sprite patterns
            avg_spacing = self._calculate_average_spacing(similar_offsets)

            if avg_spacing > 0:
                # Predict next location based on pattern
                predicted_offset = context.current_offset + avg_spacing

                # Calculate confidence based on similarity strength
                avg_similarity = statistics.mean([sim for _, sim in similar_sprites])
                confidence = avg_similarity * 0.7  # Scale for similarity-based prediction

                hint = NavigationHint(
                    target_offset=predicted_offset,
                    confidence=confidence,
                    reasoning=f"Similar to sprite at 0x{reference_sprite.offset:06X} (avg similarity: {avg_similarity:.3f})",
                    strategy_used=NavigationStrategy.SIMILARITY,
                    expected_region_type=reference_sprite.region_type,
                    similarity_score=avg_similarity,
                    priority=0.6
                )
                hints.append(hint)

        return hints

    def _calculate_average_spacing(self, offsets: list[int]) -> int:
        """Calculate average spacing between offsets."""
        if len(offsets) < 2:
            return 0

        sorted_offsets = sorted(offsets)
        spacings = []

        for i in range(len(sorted_offsets) - 1):
            spacing = sorted_offsets[i + 1] - sorted_offsets[i]
            spacings.append(spacing)

        return int(statistics.mean(spacings)) if spacings else 0

    def _deduplicate_hints(self, hints: list[NavigationHint]) -> list[NavigationHint]:
        """Remove duplicate hints, keeping highest confidence."""
        offset_map = {}

        for hint in hints:
            offset = hint.target_offset
            if offset not in offset_map or hint.confidence > offset_map[offset].confidence:
                offset_map[offset] = hint

        return list(offset_map.values())

class HybridNavigationStrategy(AbstractNavigationStrategy):
    """
    Hybrid strategy combining multiple navigation approaches.

    Intelligently combines linear, pattern-based, and similarity
    strategies based on context and data availability.
    """

    def __init__(self) -> None:
        super().__init__("Hybrid")

        # Component strategies
        self.linear_strategy = LinearNavigationStrategy()
        self.pattern_strategy = PatternBasedStrategy()
        self.similarity_strategy = SimilarityStrategy()

        # Strategy weights (can be learned/adapted)
        self.strategy_weights = {
            "linear": 0.3,
            "pattern": 0.4,
            "similarity": 0.3
        }
    @override

    def find_next_sprites(
        self,
        context: NavigationContext,
        region_map: SpriteRegionMap,
        rom_data: bytes | None = None
    ) -> list[NavigationHint]:
        """Find sprites using hybrid approach."""

        # Get hints from each strategy
        linear_hints = self.linear_strategy.find_next_sprites(context, region_map, rom_data)
        pattern_hints = self.pattern_strategy.find_next_sprites(context, region_map, rom_data)
        similarity_hints = self.similarity_strategy.find_next_sprites(context, region_map, rom_data)

        # Weight and combine hints
        weighted_hints = []

        # Apply weights to each strategy's hints
        for hint in linear_hints:
            weighted_hint = self._create_weighted_hint(hint, self.strategy_weights["linear"], "linear")
            weighted_hints.append(weighted_hint)

        for hint in pattern_hints:
            weighted_hint = self._create_weighted_hint(hint, self.strategy_weights["pattern"], "pattern")
            weighted_hints.append(weighted_hint)

        for hint in similarity_hints:
            weighted_hint = self._create_weighted_hint(hint, self.strategy_weights["similarity"], "similarity")
            weighted_hints.append(weighted_hint)

        # Combine overlapping hints
        combined_hints = self._combine_overlapping_hints(weighted_hints)

        # Sort by final confidence
        sorted_hints = sorted(combined_hints, key=lambda h: h.confidence, reverse=True)

        return sorted_hints[:context.max_hints]
    @override

    def learn_from_discovery(self, hint: NavigationHint, actual_location: SpriteLocation | None) -> None:
        """Learn from discovery results and update strategy weights."""
        success = actual_location is not None
        self._update_statistics(success)

        # Forward learning to component strategies
        self.linear_strategy.learn_from_discovery(hint, actual_location)
        self.pattern_strategy.learn_from_discovery(hint, actual_location)
        self.similarity_strategy.learn_from_discovery(hint, actual_location)

        # Adapt strategy weights based on success
        if success:
            strategy_used = hint.reasoning.split(":")[0].lower()  # Extract strategy from reasoning
            if strategy_used in self.strategy_weights:
                # Slightly increase weight for successful strategy
                self.strategy_weights[strategy_used] = min(0.8, self.strategy_weights[strategy_used] + 0.05)
                # Normalize weights
                self._normalize_weights()
    @override

    def get_confidence_estimate(self, context: NavigationContext) -> float:
        """Estimate confidence based on component strategies."""
        linear_conf = self.linear_strategy.get_confidence_estimate(context)
        pattern_conf = self.pattern_strategy.get_confidence_estimate(context)
        similarity_conf = self.similarity_strategy.get_confidence_estimate(context)

        # Weighted average of component confidences
        return (
            linear_conf * self.strategy_weights["linear"] +
            pattern_conf * self.strategy_weights["pattern"] +
            similarity_conf * self.strategy_weights["similarity"]
        )

    def _create_weighted_hint(self, hint: NavigationHint, weight: float, strategy_name: str) -> NavigationHint:
        """Create a weighted version of a hint."""
        weighted_confidence = hint.confidence * weight

        return NavigationHint(
            target_offset=hint.target_offset,
            confidence=weighted_confidence,
            reasoning=f"{strategy_name}: {hint.reasoning}",
            strategy_used=NavigationStrategy.HYBRID,
            expected_region_type=hint.expected_region_type,
            estimated_size=hint.estimated_size,
            similarity_score=hint.similarity_score,
            pattern_strength=hint.pattern_strength,
            priority=hint.priority
        )

    def _combine_overlapping_hints(self, hints: list[NavigationHint]) -> list[NavigationHint]:
        """Combine hints that target the same or nearby offsets."""
        # Group hints by target offset (with some tolerance)
        offset_groups = defaultdict(list)
        tolerance = 0x20  # 32 bytes tolerance for "same" location

        for hint in hints:
            # Find existing group within tolerance
            grouped = False
            for group_offset in offset_groups:
                if abs(hint.target_offset - group_offset) <= tolerance:
                    offset_groups[group_offset].append(hint)
                    grouped = True
                    break

            if not grouped:
                offset_groups[hint.target_offset].append(hint)

        # Combine hints in each group
        combined_hints = []
        for group_hints in offset_groups.values():
            if len(group_hints) == 1:
                combined_hints.append(group_hints[0])
            else:
                combined_hint = self._merge_hints(group_hints)
                combined_hints.append(combined_hint)

        return combined_hints

    def _merge_hints(self, hints: list[NavigationHint]) -> NavigationHint:
        """Merge multiple hints into a single combined hint."""
        if len(hints) == 1:
            return hints[0]

        # Use average offset
        avg_offset = int(statistics.mean([h.target_offset for h in hints]))

        # Combined confidence (not simple average - mutual reinforcement)
        confidences = [h.confidence for h in hints]
        combined_confidence = min(0.95, statistics.mean(confidences) + 0.1 * len(hints))

        # Combine reasoning
        strategies = [h.reasoning.split(":")[0] for h in hints]
        combined_reasoning = f"Combined strategies: {', '.join(set(strategies))}"

        # Use highest priority region type
        best_region_type = max(hints, key=lambda h: h.confidence).expected_region_type

        return NavigationHint(
            target_offset=avg_offset,
            confidence=combined_confidence,
            reasoning=combined_reasoning,
            strategy_used=NavigationStrategy.HYBRID,
            expected_region_type=best_region_type,
            priority=0.8  # High priority for combined hints
        )

    def _normalize_weights(self) -> None:
        """Normalize strategy weights to sum to 1.0."""
        total_weight = sum(self.strategy_weights.values())
        if total_weight > 0:
            for strategy in self.strategy_weights:
                self.strategy_weights[strategy] /= total_weight
