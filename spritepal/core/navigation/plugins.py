"""
Plugin framework for extensible navigation strategies.

Provides a flexible system for registering custom navigation algorithms,
format adapters, and scoring functions without modifying core code.
"""

from __future__ import annotations

import importlib
import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
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
from .strategies import (
    AbstractNavigationStrategy,
    AbstractPatternStrategy,
)

if TYPE_CHECKING:
    from pathlib import Path

    from .region_map import SpriteRegionMap

logger = get_logger(__name__)

class NavigationPlugin(ABC):
    """
    Abstract base class for navigation plugins.

    Plugins can provide custom navigation strategies, format adapters,
    or other extensions to the navigation system.
    """

    def __init__(self, name: str, version: str = "1.0.0") -> None:
        """
        Initialize plugin.

        Args:
            name: Plugin name
            version: Plugin version
        """
        self.name = name
        self.version = version
        self.enabled = True
        self._metadata = {}

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the plugin.

        Returns:
            True if initialization successful, False otherwise
        """
        ...

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up plugin resources."""
        ...

    def get_metadata(self) -> dict[str, Any]:
        """Get plugin metadata."""
        return {
            "name": self.name,
            "version": self.version,
            "enabled": self.enabled,
            **self._metadata
        }

    def set_metadata(self, key: str, value: Any) -> None:
        """Set plugin metadata."""
        self._metadata[key] = value

class StrategyPlugin(NavigationPlugin):
    """Plugin that provides navigation strategies."""

    def __init__(self, name: str, strategy_classes: list[type[AbstractNavigationStrategy]]) -> None:
        """
        Initialize strategy plugin.

        Args:
            name: Plugin name
            strategy_classes: List of strategy classes to register
        """
        super().__init__(name)
        self.strategy_classes = strategy_classes
        self.registered_strategies: list[AbstractNavigationStrategy] = []

    @override
    def initialize(self) -> bool:
        """Initialize and register strategies."""
        try:
            from .strategies import get_strategy_registry
            registry = get_strategy_registry()

            for strategy_class in self.strategy_classes:
                # Create and register strategy instance
                strategy = strategy_class(strategy_class.__name__)
                registry.register_strategy(strategy)
                self.registered_strategies.append(strategy)

                logger.info(f"Registered strategy: {strategy.get_strategy_name()}")

            return len(self.registered_strategies) > 0

        except Exception as e:
            logger.exception(f"Failed to initialize strategy plugin {self.name}: {e}")
            return False

    @override
    def cleanup(self) -> None:
        """Unregister strategies."""
        try:
            from .strategies import get_strategy_registry
            registry = get_strategy_registry()

            for strategy in self.registered_strategies:
                registry.unregister_strategy(strategy.get_strategy_name())

            self.registered_strategies.clear()

        except Exception as e:
            logger.exception(f"Error cleaning up strategy plugin {self.name}: {e}")

class FormatAdapterPlugin(NavigationPlugin):
    """Plugin that provides format-specific adapters."""

    def __init__(self, name: str, format_adapters: dict[str, Callable[..., Any]]) -> None:
        """
        Initialize format adapter plugin.

        Args:
            name: Plugin name
            format_adapters: Dictionary mapping format names to adapter functions
        """
        super().__init__(name)
        self.format_adapters = format_adapters

    @override
    def initialize(self) -> bool:
        """Register format adapters."""
        try:
            # Register with format registry (would be implemented)
            for format_name in self.format_adapters:
                logger.info(f"Registered format adapter: {format_name}")

            return True

        except Exception as e:
            logger.exception(f"Failed to initialize format adapter plugin {self.name}: {e}")
            return False

    @override
    def cleanup(self) -> None:
        """Unregister format adapters."""
        logger.info(f"Cleaned up format adapter plugin: {self.name}")

class ScoringAlgorithmPlugin(NavigationPlugin):
    """Plugin that provides custom scoring algorithms."""

    def __init__(self, name: str, scoring_functions: dict[str, Callable[..., Any]]) -> None:
        """
        Initialize scoring algorithm plugin.

        Args:
            name: Plugin name
            scoring_functions: Dictionary mapping algorithm names to scoring functions
        """
        super().__init__(name)
        self.scoring_functions = scoring_functions

    @override
    def initialize(self) -> bool:
        """Register scoring algorithms."""
        try:
            for algorithm_name in self.scoring_functions:
                logger.info(f"Registered scoring algorithm: {algorithm_name}")

            return True

        except Exception as e:
            logger.exception(f"Failed to initialize scoring plugin {self.name}: {e}")
            return False

    @override
    def cleanup(self) -> None:
        """Unregister scoring algorithms."""
        logger.info(f"Cleaned up scoring plugin: {self.name}")

class PluginManager:
    """
    Manager for navigation plugins.

    Handles plugin discovery, loading, lifecycle management, and
    provides a registry for plugin capabilities.
    """

    def __init__(self, plugin_directories: list[Path] | None = None) -> None:
        """
        Initialize plugin manager.

        Args:
            plugin_directories: Directories to search for plugins
        """
        self.plugin_directories = plugin_directories or []
        self.loaded_plugins: dict[str, NavigationPlugin] = {}
        self.plugin_metadata: dict[str, dict[str, Any]] = {}

        # Plugin capabilities registry
        self.strategy_plugins: dict[str, StrategyPlugin] = {}
        self.format_plugins: dict[str, FormatAdapterPlugin] = {}
        self.scoring_plugins: dict[str, ScoringAlgorithmPlugin] = {}

    def add_plugin_directory(self, directory: Path) -> None:
        """
        Add a directory to search for plugins.

        Args:
            directory: Directory path to add
        """
        if directory not in self.plugin_directories:
            self.plugin_directories.append(directory)
            logger.info(f"Added plugin directory: {directory}")

    def discover_plugins(self) -> list[str]:
        """
        Discover available plugins in plugin directories.

        Returns:
            List of discovered plugin module names
        """
        discovered = []

        for plugin_dir in self.plugin_directories:
            if not plugin_dir.exists():
                continue

            # Look for Python files that might be plugins
            for python_file in plugin_dir.glob("*.py"):
                if python_file.stem.startswith("_"):
                    continue  # Skip private modules

                module_name = python_file.stem
                discovered.append(module_name)

                logger.debug(f"Discovered potential plugin: {module_name}")

        return discovered

    def load_plugin(self, plugin_name: str, plugin_class: type[NavigationPlugin] | None = None) -> bool:
        """
        Load a plugin by name or class.

        Args:
            plugin_name: Name of plugin to load
            plugin_class: Optional plugin class to instantiate directly

        Returns:
            True if plugin loaded successfully, False otherwise
        """
        try:
            if plugin_class:
                # Direct class instantiation
                plugin = plugin_class(plugin_name)
            else:
                # Dynamic module loading
                plugin = self._load_plugin_from_module(plugin_name)

            if not plugin:
                return False

            # Initialize plugin
            if not plugin.initialize():
                logger.error(f"Plugin initialization failed: {plugin_name}")
                return False

            # Register plugin
            self.loaded_plugins[plugin.name] = plugin
            self.plugin_metadata[plugin.name] = plugin.get_metadata()

            # Register by type
            self._register_plugin_by_type(plugin)

            logger.info(f"Successfully loaded plugin: {plugin.name} v{plugin.version}")
            return True

        except Exception as e:
            logger.exception(f"Failed to load plugin {plugin_name}: {e}")
            return False

    def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload a plugin.

        Args:
            plugin_name: Name of plugin to unload

        Returns:
            True if plugin unloaded successfully, False otherwise
        """
        if plugin_name not in self.loaded_plugins:
            logger.warning(f"Plugin not loaded: {plugin_name}")
            return False

        try:
            plugin = self.loaded_plugins[plugin_name]

            # Cleanup plugin
            plugin.cleanup()

            # Remove from registries
            self._unregister_plugin_by_type(plugin)

            # Remove from loaded plugins
            del self.loaded_plugins[plugin_name]
            del self.plugin_metadata[plugin_name]

            logger.info(f"Successfully unloaded plugin: {plugin_name}")
            return True

        except Exception as e:
            logger.exception(f"Failed to unload plugin {plugin_name}: {e}")
            return False

    def get_loaded_plugins(self) -> dict[str, NavigationPlugin]:
        """Get all loaded plugins."""
        return self.loaded_plugins.copy()

    def get_plugin_metadata(self) -> dict[str, dict[str, Any]]:
        """Get metadata for all loaded plugins."""
        return self.plugin_metadata.copy()

    def enable_plugin(self, plugin_name: str) -> bool:
        """
        Enable a plugin.

        Args:
            plugin_name: Name of plugin to enable

        Returns:
            True if plugin enabled successfully, False otherwise
        """
        if plugin_name not in self.loaded_plugins:
            return False

        plugin = self.loaded_plugins[plugin_name]
        plugin.enabled = True

        logger.info(f"Enabled plugin: {plugin_name}")
        return True

    def disable_plugin(self, plugin_name: str) -> bool:
        """
        Disable a plugin.

        Args:
            plugin_name: Name of plugin to disable

        Returns:
            True if plugin disabled successfully, False otherwise
        """
        if plugin_name not in self.loaded_plugins:
            return False

        plugin = self.loaded_plugins[plugin_name]
        plugin.enabled = False

        logger.info(f"Disabled plugin: {plugin_name}")
        return True

    def get_strategy_plugins(self) -> dict[str, StrategyPlugin]:
        """Get all loaded strategy plugins."""
        return {name: plugin for name, plugin in self.strategy_plugins.items()
                if plugin.enabled}

    def get_format_plugins(self) -> dict[str, FormatAdapterPlugin]:
        """Get all loaded format adapter plugins."""
        return {name: plugin for name, plugin in self.format_plugins.items()
                if plugin.enabled}

    def get_scoring_plugins(self) -> dict[str, ScoringAlgorithmPlugin]:
        """Get all loaded scoring algorithm plugins."""
        return {name: plugin for name, plugin in self.scoring_plugins.items()
                if plugin.enabled}

    def reload_plugin(self, plugin_name: str) -> bool:
        """
        Reload a plugin (unload and load again).

        Args:
            plugin_name: Name of plugin to reload

        Returns:
            True if plugin reloaded successfully, False otherwise
        """
        if plugin_name in self.loaded_plugins:
            if not self.unload_plugin(plugin_name):
                return False

        return self.load_plugin(plugin_name)

    def shutdown_all_plugins(self) -> None:
        """Shutdown and unload all plugins."""
        plugin_names = list(self.loaded_plugins.keys())

        for plugin_name in plugin_names:
            try:
                self.unload_plugin(plugin_name)
            except Exception as e:
                logger.exception(f"Error unloading plugin {plugin_name}: {e}")

        logger.info("Shutdown all navigation plugins")

    def _load_plugin_from_module(self, module_name: str) -> NavigationPlugin | None:
        """Load plugin from module name."""
        try:
            # Try to import the module
            module = importlib.import_module(module_name)

            # Look for plugin classes in the module
            for _name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and
                    issubclass(obj, NavigationPlugin) and
                    obj != NavigationPlugin):

                    # Found a plugin class, instantiate it
                    return obj(module_name)

            logger.warning(f"No plugin class found in module: {module_name}")
            return None

        except ImportError as e:
            logger.exception(f"Could not import plugin module {module_name}: {e}")
            return None

    def _register_plugin_by_type(self, plugin: NavigationPlugin) -> None:
        """Register plugin in appropriate type-specific registry."""
        if isinstance(plugin, StrategyPlugin):
            self.strategy_plugins[plugin.name] = plugin
        elif isinstance(plugin, FormatAdapterPlugin):
            self.format_plugins[plugin.name] = plugin
        elif isinstance(plugin, ScoringAlgorithmPlugin):
            self.scoring_plugins[plugin.name] = plugin

    def _unregister_plugin_by_type(self, plugin: NavigationPlugin) -> None:
        """Unregister plugin from type-specific registries."""
        if isinstance(plugin, StrategyPlugin) and plugin.name in self.strategy_plugins:
            del self.strategy_plugins[plugin.name]
        elif isinstance(plugin, FormatAdapterPlugin) and plugin.name in self.format_plugins:
            del self.format_plugins[plugin.name]
        elif isinstance(plugin, ScoringAlgorithmPlugin) and plugin.name in self.scoring_plugins:
            del self.scoring_plugins[plugin.name]

# Example plugin implementations for reference

class LinearPatternStrategy(AbstractPatternStrategy):
    """Example strategy that learns linear spacing patterns."""

    def __init__(self) -> None:
        super().__init__("LinearPattern")

    @override
    def find_next_sprites(
        self,
        context: NavigationContext,
        region_map: SpriteRegionMap,
        rom_data: bytes | None = None
    ) -> list[NavigationHint]:
        """Find sprites based on linear patterns."""
        hints = []

        # Simple linear prediction based on last few sprites
        nearby_sprites = region_map.find_nearest_sprites(context.current_offset, count=3)

        if len(nearby_sprites) >= 2:
            # Calculate average spacing
            distances = []
            for i in range(len(nearby_sprites) - 1):
                dist = abs(nearby_sprites[i][0].offset - nearby_sprites[i+1][0].offset)
                distances.append(dist)

            if distances:
                avg_distance = sum(distances) / len(distances)
                predicted_offset = context.current_offset + int(avg_distance)

                hint = NavigationHint(
                    target_offset=predicted_offset,
                    confidence=0.7,
                    reasoning=f"Linear pattern: avg spacing {avg_distance:.0f}",
                    strategy_used=context.preferred_strategies[0] if context.preferred_strategies else NavigationStrategy.PATTERN_BASED,
                    expected_region_type=RegionType.UNKNOWN
                )
                hints.append(hint)

        return hints

    @override
    def learn_from_discovery(self, hint: NavigationHint, actual_location: SpriteLocation | None) -> None:
        """Learn from discovery results."""
        success = actual_location is not None
        self._update_statistics(success)

        if success:
            # Update patterns based on successful prediction
            pass

    @override
    def get_confidence_estimate(self, context: NavigationContext) -> float:
        """Estimate confidence for current context."""
        return 0.6  # Moderate confidence for linear patterns

    @override
    def _extract_patterns(self, region_map: SpriteRegionMap) -> dict[str, Any]:
        """Extract linear patterns from region map."""
        sprites = list(region_map)
        if len(sprites) < 3:
            return {}

        # Calculate spacing patterns
        spacings = []
        for i in range(len(sprites) - 1):
            spacing = sprites[i + 1].offset - sprites[i].end_offset
            if spacing > 0:
                spacings.append(spacing)

        return {"spacings": spacings, "avg_spacing": sum(spacings) / len(spacings) if spacings else 0}

    @override
    def _apply_patterns(self, patterns: dict[str, Any], context: NavigationContext) -> list[NavigationHint]:
        """Apply learned patterns to generate hints."""
        hints = []

        if "avg_spacing" in patterns:
            predicted_offset = context.current_offset + patterns["avg_spacing"]

            hint = NavigationHint(
                target_offset=int(predicted_offset),
                confidence=0.8,
                reasoning="Applied learned linear pattern",
                strategy_used=NavigationStrategy.PATTERN_BASED,
                expected_region_type=RegionType.UNKNOWN
            )
            hints.append(hint)

        return hints

class ExampleStrategyPlugin(StrategyPlugin):
    """Example plugin that provides a linear pattern strategy."""

    def __init__(self) -> None:
        super().__init__(
            name="ExampleLinearStrategy",
            strategy_classes=[LinearPatternStrategy]
        )
        self.set_metadata("author", "SpritePal Team")
        self.set_metadata("description", "Example linear pattern strategy plugin")

class _PluginManagerSingleton:
    """Singleton holder for PluginManager."""
    _instance: PluginManager | None = None
    _plugin_directories: list[Path] | None = None

    @classmethod
    def get(cls, plugin_directories: list[Path] | None = None) -> PluginManager:
        """
        Get global plugin manager instance.

        Args:
            plugin_directories: Plugin directories (used only on first call)

        Returns:
            Global plugin manager instance
        """
        if cls._instance is None:
            # Use provided directories or stored ones
            cls._instance = PluginManager(plugin_directories or cls._plugin_directories)
            if plugin_directories:
                cls._plugin_directories = plugin_directories
        return cls._instance

    @classmethod
    def shutdown(cls) -> None:
        """Shutdown global plugin manager."""
        if cls._instance:
            cls._instance.shutdown_all_plugins()
            cls._instance = None

def get_plugin_manager(plugin_directories: list[Path] | None = None) -> PluginManager:
    """
    Get global plugin manager instance.

    Args:
        plugin_directories: Plugin directories (used only on first call)

    Returns:
        Global plugin manager instance
    """
    return _PluginManagerSingleton.get(plugin_directories)

def shutdown_plugin_manager() -> None:
    """Shutdown global plugin manager."""
    _PluginManagerSingleton.shutdown()
