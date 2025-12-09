"""
Core navigation manager for smart sprite discovery.

Integrates with the existing manager pattern to provide intelligent
sprite navigation capabilities with proper Qt integration.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal
from typing_extensions import override

from core.managers.base_manager import BaseManager
from core.managers.exceptions import NavigationError
from utils.logging_config import get_logger

from .data_structures import NavigationContext, NavigationHint, SpriteLocation
from .region_map import SpriteRegionMap
from .strategies import get_strategy_registry

if TYPE_CHECKING:
    from core.protocols.manager_protocols import SettingsManagerProtocol

logger = get_logger(__name__)

class NavigationManager(BaseManager):
    """
    Manager for intelligent sprite navigation operations.

    Provides high-level interface for smart sprite discovery, integrating
    pattern learning, similarity analysis, and predictive algorithms.
    Now accepts `SettingsManagerProtocol` via dependency injection.
    """

    # Navigation-specific signals
    navigation_hints_ready = Signal(list)  # List of NavigationHint objects
    region_map_updated = Signal(dict)      # Region map statistics
    pattern_learned = Signal(str, dict)   # Strategy name, pattern data
    similarity_found = Signal(int, list)  # Offset, list of similar sprites

    def __init__(self, parent: QObject | None = None,
                 settings_manager: SettingsManagerProtocol | None = None) -> None:
        """Initialize navigation manager."""
        # Initialize all attributes BEFORE calling super().__init__()
        # Core data structures
        self._region_maps: dict[str, SpriteRegionMap] = {}  # ROM path -> region map
        self._navigation_context = NavigationContext()

        # Strategy management
        self._strategy_registry = get_strategy_registry()
        self._active_strategies: list[str] = []

        # Background processing
        self._background_thread: threading.Thread | None = None
        self._background_enabled = True
        self._background_stop_event = threading.Event()

        # Cache management
        self._cache_dir: Path | None = None
        self._auto_save_enabled = True

        # Performance tracking
        self._performance_metrics = {
            "total_hints_generated": 0,
            "successful_navigations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "average_hint_time": 0.0
        }

        # Inject settings manager or use fallback
        if settings_manager is None:
            from core.di_container import inject
            from core.protocols.manager_protocols import SettingsManagerProtocol
            self.settings_manager = inject(SettingsManagerProtocol)
        else:
            self.settings_manager = settings_manager

        # Now call super().__init__() which triggers _initialize()
        super().__init__("NavigationManager", parent)

    @override
    def _initialize(self) -> None:
        """Initialize the navigation manager."""
        try:
            # Set up cache directory
            self._setup_cache_directory()

            # Register default strategies
            self._register_default_strategies()

            # Start background processing
            if self._background_enabled:
                self._start_background_processing()

            self._is_initialized = True
            logger.info("Navigation manager initialized successfully")

        except Exception as e:
            self._handle_error(e, "initialization")
            raise NavigationError(f"Failed to initialize NavigationManager: {e}") from e

    @override
    def cleanup(self) -> None:
        """Clean up navigation manager resources."""
        try:
            # Stop background processing
            if self._background_thread and self._background_thread.is_alive():
                self._background_stop_event.set()
                self._background_thread.join(timeout=5.0)

                if self._background_thread.is_alive():
                    logger.warning("Background thread did not stop gracefully")

            # Save region maps if auto-save is enabled
            if self._auto_save_enabled:
                self._save_all_region_maps()

            # Clear data structures
            self._region_maps.clear()

            logger.info("Navigation manager cleaned up successfully")

        except Exception as e:
            logger.exception(f"Error during navigation manager cleanup: {e}")

    def set_rom_file(self, rom_path: str, rom_size: int) -> None:
        """
        Set the current ROM file for navigation.

        Args:
            rom_path: Path to ROM file
            rom_size: Size of ROM file in bytes
        """
        if not self._start_operation("set_rom_file"):
            return

        try:
            self._validate_required({"rom_path": rom_path}, ["rom_path"])
            self._validate_type(rom_size, "rom_size", int)
            self._validate_range(rom_size, "rom_size", min_val=1)

            # Create or load region map for this ROM
            if rom_path not in self._region_maps:
                self._region_maps[rom_path] = self._load_or_create_region_map(rom_path, rom_size)

            # Update navigation context
            self._navigation_context.current_offset = 0

            logger.info(f"Set ROM file: {rom_path} (size: {rom_size} bytes)")

        except Exception as e:
            self._handle_error(e, "set_rom_file")
            raise
        finally:
            self._finish_operation("set_rom_file")

    def add_discovered_sprite(self, rom_path: str, sprite: SpriteLocation) -> None:
        """
        Add a newly discovered sprite to the region map.

        Args:
            rom_path: Path to ROM file
            sprite: Discovered sprite location
        """
        if not self._start_operation("add_sprite"):
            return

        try:
            self._validate_required({"rom_path": rom_path, "sprite": sprite}, ["rom_path", "sprite"])

            # Get or create region map
            if rom_path not in self._region_maps:
                logger.warning(f"No region map for ROM: {rom_path}")
                return

            region_map = self._region_maps[rom_path]

            # Add sprite to region map
            if region_map.add_sprite(sprite):
                logger.info(f"Added sprite at 0x{sprite.offset:06X} to region map")

                # Emit signal with updated statistics
                stats = region_map.get_region_statistics()
                self.region_map_updated.emit(stats)

                # Trigger pattern learning in background
                self._trigger_background_learning(rom_path)

        except Exception as e:
            self._handle_error(e, "add_sprite")
            raise
        finally:
            self._finish_operation("add_sprite")

    def get_navigation_hints(
        self,
        rom_path: str,
        current_offset: int,
        max_hints: int = 10,
        strategies: list[str] | None = None
    ) -> list[NavigationHint]:
        """
        Get intelligent navigation hints for the next sprite locations.

        Args:
            rom_path: Path to ROM file
            current_offset: Current position in ROM
            max_hints: Maximum number of hints to return
            strategies: Specific strategies to use (None = use all enabled)

        Returns:
            List of navigation hints sorted by relevance
        """
        if not self._start_operation("get_hints"):
            return []

        try:
            start_time = time.time()

            self._validate_required({"rom_path": rom_path}, ["rom_path"])
            self._validate_type(current_offset, "current_offset", int)
            self._validate_range(current_offset, "current_offset", min_val=0)
            self._validate_range(max_hints, "max_hints", min_val=1, max_val=100)

            # Get region map
            region_map = self._region_maps.get(rom_path)
            if not region_map:
                logger.warning(f"No region map for ROM: {rom_path}")
                return []

            # Update navigation context
            self._navigation_context.current_offset = current_offset
            self._navigation_context.max_hints = max_hints

            # Get strategies to use
            if strategies:
                active_strategies = [
                    self._strategy_registry.get_strategy(name)
                    for name in strategies
                    if self._strategy_registry.get_strategy(name)
                ]
            else:
                active_strategies = list(self._strategy_registry.get_enabled_strategies().values())

            if not active_strategies:
                logger.warning("No active navigation strategies available")
                return []

            # Collect hints from all strategies
            all_hints = []

            for strategy in active_strategies:
                if strategy is None:
                    logger.warning("Skipping None strategy in active_strategies")
                    continue

                try:
                    strategy_hints = strategy.find_next_sprites(
                        self._navigation_context,
                        region_map
                    )
                    all_hints.extend(strategy_hints)

                except Exception as e:
                    logger.exception(f"Strategy '{strategy.get_strategy_name()}' failed: {e}")
                    continue

            # Remove duplicates and sort by score
            unique_hints = self._deduplicate_hints(all_hints)
            sorted_hints = sorted(unique_hints, key=lambda h: h.score, reverse=True)

            # Apply user context filtering
            filtered_hints = self._filter_hints_by_context(sorted_hints)

            # Limit results
            final_hints = filtered_hints[:max_hints]

            # Update performance metrics
            elapsed_time = time.time() - start_time
            self._update_performance_metrics(len(final_hints), elapsed_time)

            # Emit signal
            self.navigation_hints_ready.emit(final_hints)

            logger.info(f"Generated {len(final_hints)} navigation hints in {elapsed_time:.3f}s")
            return final_hints

        except Exception as e:
            self._handle_error(e, "get_hints")
            raise
        finally:
            self._finish_operation("get_hints")

    def learn_from_navigation(
        self,
        hint: NavigationHint,
        actual_sprite: SpriteLocation | None
    ) -> None:
        """
        Learn from navigation results to improve future predictions.

        Args:
            hint: The hint that was followed
            actual_sprite: The sprite found (None if hint was incorrect)
        """
        if not self._start_operation("learn"):
            return

        try:
            # Get strategy that generated the hint
            strategy = self._strategy_registry.get_strategy(hint.strategy_used.value)
            if strategy:
                strategy.learn_from_discovery(hint, actual_sprite)

                # Update performance metrics
                success = actual_sprite is not None
                self._performance_metrics["successful_navigations"] += int(success)

                if success:
                    logger.debug(f"Successful navigation learned by {hint.strategy_used.value}")
                else:
                    logger.debug(f"Failed navigation learned by {hint.strategy_used.value}")

        except Exception as e:
            self._handle_error(e, "learn")
            raise
        finally:
            self._finish_operation("learn")

    def find_similar_sprites(
        self,
        rom_path: str,
        reference_sprite: SpriteLocation,
        max_results: int = 10
    ) -> list[tuple[SpriteLocation, float]]:
        """
        Find sprites similar to a reference sprite.

        Args:
            rom_path: Path to ROM file
            reference_sprite: Sprite to find similarities for
            max_results: Maximum number of results

        Returns:
            List of (sprite, similarity_score) tuples
        """
        if not self._start_operation("find_similar"):
            return []

        try:
            region_map = self._region_maps.get(rom_path)
            if not region_map:
                return []

            # Use similarity strategies
            similarity_strategies = [
                strategy for strategy in self._strategy_registry.get_enabled_strategies().values()
                if hasattr(strategy, "_calculate_similarity")
            ]

            if not similarity_strategies:
                logger.warning("No similarity strategies available")
                return []

            # Collect similarity results
            all_results = []
            for sprite in region_map:
                if sprite.offset == reference_sprite.offset:
                    continue

                for strategy in similarity_strategies:
                    try:
                        # Strategy has _calculate_similarity checked above
                        similarity = strategy._calculate_similarity(reference_sprite, sprite)  # type: ignore[attr-defined]
                        if similarity > 0.5:  # Minimum similarity threshold
                            all_results.append((sprite, similarity))
                        break  # Use first strategy result
                    except Exception as e:
                        logger.debug(f"Similarity calculation failed: {e}")
                        continue

            # Sort by similarity and limit results
            all_results.sort(key=lambda x: x[1], reverse=True)
            results = all_results[:max_results]

            # Emit signal
            if results:
                self.similarity_found.emit(reference_sprite.offset, [r[0] for r in results])

            return results

        except Exception as e:
            self._handle_error(e, "find_similar")
            raise
        finally:
            self._finish_operation("find_similar")

    def get_region_statistics(self, rom_path: str) -> dict[str, Any]:
        """
        Get statistics about the region map for a ROM.

        Args:
            rom_path: Path to ROM file

        Returns:
            Dictionary with region statistics
        """
        region_map = self._region_maps.get(rom_path)
        if region_map:
            return region_map.get_region_statistics()
        return {}

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get performance metrics for the navigation manager."""
        return self._performance_metrics.copy()

    def enable_strategy(self, strategy_name: str) -> None:
        """Enable a navigation strategy."""
        strategy = self._strategy_registry.get_strategy(strategy_name)
        if strategy:
            strategy.set_enabled(True)
            logger.info(f"Enabled navigation strategy: {strategy_name}")

    def disable_strategy(self, strategy_name: str) -> None:
        """Disable a navigation strategy."""
        strategy = self._strategy_registry.get_strategy(strategy_name)
        if strategy:
            strategy.set_enabled(False)
            logger.info(f"Disabled navigation strategy: {strategy_name}")

    def get_available_strategies(self) -> list[str]:
        """Get list of available strategy names."""
        return self._strategy_registry.get_strategy_names()

    def _setup_cache_directory(self) -> None:
        """Set up cache directory for region maps."""
        try:
            settings = self.settings_manager
            if settings:
                cache_location = settings.get_cache_location()
                if cache_location:
                    self._cache_dir = Path(cache_location) / "navigation"

            # Fallback to default location
            if not self._cache_dir:
                self._cache_dir = Path.home() / ".spritepal_cache" / "navigation"

            # Create directory
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Navigation cache directory: {self._cache_dir}")

        except Exception as e:
            logger.warning(f"Failed to set up cache directory: {e}")
            self._cache_dir = None

    def _register_default_strategies(self) -> None:
        """Register default navigation strategies."""
        # Import and register default strategies
        try:
            from .implementations import (
                LinearNavigationStrategy,
                PatternBasedStrategy,
                SimilarityStrategy,
            )

            self._strategy_registry.register_strategy(LinearNavigationStrategy())
            self._strategy_registry.register_strategy(PatternBasedStrategy())
            self._strategy_registry.register_strategy(SimilarityStrategy())

            logger.info("Registered default navigation strategies")

        except ImportError as e:
            logger.warning(f"Could not register default strategies: {e}")

    def _load_or_create_region_map(self, rom_path: str, rom_size: int) -> SpriteRegionMap:
        """Load existing region map or create new one."""
        if not self._cache_dir:
            return SpriteRegionMap(rom_size)

        # Generate cache filename
        cache_name = f"region_map_{Path(rom_path).stem}.json"
        cache_path = self._cache_dir / cache_name

        try:
            if cache_path.exists():
                region_map = SpriteRegionMap.load_from_file(cache_path)
                self._performance_metrics["cache_hits"] += 1
                logger.info(f"Loaded cached region map for {rom_path}")
                return region_map
        except Exception as e:
            logger.warning(f"Failed to load cached region map: {e}")

        # Create new region map
        self._performance_metrics["cache_misses"] += 1
        return SpriteRegionMap(rom_size)

    def _save_all_region_maps(self) -> None:
        """Save all region maps to cache."""
        if not self._cache_dir:
            return

        for rom_path, region_map in self._region_maps.items():
            try:
                cache_name = f"region_map_{Path(rom_path).stem}.json"
                cache_path = self._cache_dir / cache_name
                region_map.save_to_file(cache_path)
            except Exception as e:
                logger.exception(f"Failed to save region map for {rom_path}: {e}")

    def _deduplicate_hints(self, hints: list[NavigationHint]) -> list[NavigationHint]:
        """Remove duplicate hints, keeping highest confidence."""
        offset_map = {}

        for hint in hints:
            offset = hint.target_offset
            if offset not in offset_map or hint.confidence > offset_map[offset].confidence:
                offset_map[offset] = hint

        return list(offset_map.values())

    def _filter_hints_by_context(self, hints: list[NavigationHint]) -> list[NavigationHint]:
        """Filter hints based on user context and preferences."""
        filtered = []

        for hint in hints:
            # Skip rejected hints
            if hint.target_offset in self._navigation_context.rejected_hints:
                continue

            # Skip recently visited locations
            if hint.target_offset in self._navigation_context.recently_visited[:10]:
                continue

            # Apply distance penalty
            hint.distance_penalty = self._navigation_context.get_distance_penalty(hint.target_offset)

            # Only include hints above minimum confidence
            if hint.score >= self._navigation_context.min_confidence:
                filtered.append(hint)

        return filtered

    def _update_performance_metrics(self, hint_count: int, elapsed_time: float) -> None:
        """Update performance tracking metrics."""
        self._performance_metrics["total_hints_generated"] += hint_count

        # Update average hint time
        total_time = (
            self._performance_metrics["average_hint_time"] *
            (self._performance_metrics["total_hints_generated"] - hint_count)
        ) + elapsed_time

        if self._performance_metrics["total_hints_generated"] > 0:
            self._performance_metrics["average_hint_time"] = (
                total_time / self._performance_metrics["total_hints_generated"]
            )

    def _start_background_processing(self) -> None:
        """Start background processing thread."""
        if self._background_thread and self._background_thread.is_alive():
            return

        self._background_stop_event.clear()
        self._background_thread = threading.Thread(
            target=self._background_worker,
            name="NavigationBackgroundWorker",
            daemon=True
        )
        self._background_thread.start()
        logger.info("Started navigation background processing")

    def _background_worker(self) -> None:
        """Background processing worker."""
        while not self._background_stop_event.is_set():
            try:
                # Periodic maintenance tasks
                if self._auto_save_enabled:
                    self._save_all_region_maps()

                # Wait before next iteration
                self._background_stop_event.wait(60.0)  # Run every minute

            except Exception as e:
                logger.exception(f"Background worker error: {e}")
                self._background_stop_event.wait(60.0)

    def _trigger_background_learning(self, rom_path: str) -> None:
        """Trigger background pattern learning for a ROM."""
        # This would trigger more intensive pattern analysis
        # in a separate thread to avoid blocking the UI
        logger.debug(f"Triggered background learning for {rom_path}")

class NavigationException(Exception):
    """Navigation-specific error."""
