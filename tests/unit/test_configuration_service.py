"""Tests for ConfigurationService and ApplicationPaths.

This module tests the centralized configuration service that provides
all application paths.
"""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.configuration_service import (
    ApplicationPaths,
    ConfigurationService,
)

pytestmark = [
    pytest.mark.headless,
]


@pytest.fixture
def clean_env(monkeypatch):
    """Remove environment overrides for clean testing."""
    monkeypatch.delenv("SPRITEPAL_SETTINGS_DIR", raising=False)
    monkeypatch.delenv("SPRITEPAL_CACHE_DIR", raising=False)
    monkeypatch.delenv("SPRITEPAL_LOG_DIR", raising=False)


class TestApplicationPaths:
    """Tests for the ApplicationPaths dataclass."""

    def test_application_paths_is_immutable(self, tmp_path):
        """ApplicationPaths should be frozen (immutable)."""
        paths = ApplicationPaths(
            app_root=tmp_path,
            settings_file=tmp_path / "settings.json",
            log_directory=tmp_path / "logs",
            cache_directory=tmp_path / "cache",
            config_directory=tmp_path / "config",
            default_dumps_directory=tmp_path / "dumps",
        )

        with pytest.raises(FrozenInstanceError):
            paths.app_root = tmp_path / "new_root"  # type: ignore[misc]

    def test_application_paths_all_fields_are_paths(self, tmp_path):
        """All fields of ApplicationPaths should be Path instances."""
        paths = ApplicationPaths(
            app_root=tmp_path,
            settings_file=tmp_path / "settings.json",
            log_directory=tmp_path / "logs",
            cache_directory=tmp_path / "cache",
            config_directory=tmp_path / "config",
            default_dumps_directory=tmp_path / "dumps",
        )

        assert isinstance(paths.app_root, Path)
        assert isinstance(paths.settings_file, Path)
        assert isinstance(paths.log_directory, Path)
        assert isinstance(paths.cache_directory, Path)
        assert isinstance(paths.config_directory, Path)
        assert isinstance(paths.default_dumps_directory, Path)


class TestConfigurationServiceInit:
    """Tests for ConfigurationService initialization."""

    def test_init_with_default_app_root(self, clean_env):
        """Init without app_root should use module's parent directory."""
        service = ConfigurationService()

        # The module is at core/configuration_service.py, so app_root
        # should be the parent of core/ (the spritepal directory)
        assert service.app_root.is_absolute()
        assert service.app_root.name == "spritepal"
        assert (service.app_root / "core").exists()

    def test_init_with_custom_app_root(self, tmp_path, clean_env):
        """Init with app_root should use that directory."""
        service = ConfigurationService(app_root=tmp_path)

        assert service.app_root == tmp_path.resolve()

    def test_init_with_settings_manager(self, tmp_path, clean_env):
        """Init with settings_manager should use custom cache location."""
        custom_cache = tmp_path / "custom_cache"
        mock_settings = MagicMock()
        mock_settings.get_cache_location.return_value = str(custom_cache)

        service = ConfigurationService(
            app_root=tmp_path,
            settings_manager=mock_settings,
        )

        # Verify observable behavior: cache_directory uses settings override
        assert service.cache_directory == custom_cache

    def test_init_resolves_paths_to_absolute(self, clean_env):
        """All paths should be absolute after initialization."""
        # Use relative path
        service = ConfigurationService(app_root=Path())

        assert service.app_root.is_absolute()
        assert service.settings_file.is_absolute()
        assert service.log_directory.is_absolute()
        assert service.cache_directory.is_absolute()
        assert service.config_directory.is_absolute()
        assert service.default_dumps_directory.is_absolute()


class TestConfigurationServicePaths:
    """Tests for ConfigurationService path properties."""

    @pytest.fixture
    def service(self, tmp_path, clean_env):
        """Create a ConfigurationService with tmp_path as app_root."""
        return ConfigurationService(app_root=tmp_path)

    def test_app_root_property(self, service, tmp_path):
        """app_root should return the configured root directory."""
        assert service.app_root == tmp_path.resolve()

    def test_settings_file_property(self, service, tmp_path):
        """settings_file should be in app_root with correct name."""
        assert service.settings_file == tmp_path.resolve() / ".spritepal_settings.json"
        assert service.settings_file.name == ".spritepal_settings.json"

    def test_log_directory_property(self, service):
        """log_directory should be in user's home directory."""
        assert service.log_directory == Path.home() / ".spritepal/logs"

    def test_cache_directory_property(self, service):
        """cache_directory should be in user's home directory by default."""
        assert service.cache_directory == Path.home() / ".spritepal_rom_cache"

    def test_cache_directory_with_settings_override(self, tmp_path, clean_env):
        """cache_directory should use settings override if set."""
        custom_cache = tmp_path / "custom_cache"
        mock_settings = MagicMock()
        mock_settings.get_cache_location.return_value = str(custom_cache)

        service = ConfigurationService(
            app_root=tmp_path,
            settings_manager=mock_settings,
        )

        assert service.cache_directory == custom_cache

    def test_cache_directory_with_empty_settings(self, tmp_path, clean_env):
        """cache_directory should use default if settings returns empty."""
        mock_settings = MagicMock()
        mock_settings.get_cache_location.return_value = ""

        service = ConfigurationService(
            app_root=tmp_path,
            settings_manager=mock_settings,
        )

        # Empty string should fall back to default
        assert service.cache_directory == Path.home() / ".spritepal_rom_cache"

    def test_config_directory_property(self, service, tmp_path):
        """config_directory should be in app_root."""
        assert service.config_directory == tmp_path.resolve() / "config"

    def test_default_dumps_directory_property(self, service):
        """default_dumps_directory should be in user's Documents."""
        expected = Path.home() / "Documents/Mesen2/Debugger"
        assert service.default_dumps_directory == expected

    def test_sprite_config_file_property(self, service, tmp_path):
        """sprite_config_file should be in config_directory."""
        expected = tmp_path.resolve() / "config" / "sprite_locations.json"
        assert service.sprite_config_file == expected


class TestConfigurationServiceResolve:
    """Tests for resolve_path method."""

    @pytest.fixture
    def service(self, tmp_path, clean_env):
        """Create a ConfigurationService with tmp_path as app_root."""
        return ConfigurationService(app_root=tmp_path)

    def test_resolve_path_valid_keys(self, service, tmp_path):
        """resolve_path should return correct paths for valid keys."""
        assert service.resolve_path("app_root") == tmp_path.resolve()
        assert service.resolve_path("settings_file") == tmp_path.resolve() / ".spritepal_settings.json"
        assert service.resolve_path("config_directory") == tmp_path.resolve() / "config"
        assert service.resolve_path("sprite_config_file") == tmp_path.resolve() / "config" / "sprite_locations.json"

    def test_resolve_path_invalid_key_raises_keyerror(self, service):
        """resolve_path should raise KeyError for invalid keys."""
        with pytest.raises(KeyError) as exc_info:
            service.resolve_path("invalid_key")

        # Should include the invalid key in message
        assert "invalid_key" in str(exc_info.value)
        # Should list valid keys
        assert "app_root" in str(exc_info.value)

    def test_resolve_path_all_keys_return_paths(self, service):
        """All valid keys should return Path instances."""
        valid_keys = [
            "app_root",
            "settings_file",
            "log_directory",
            "cache_directory",
            "config_directory",
            "default_dumps_directory",
            "sprite_config_file",
        ]

        for key in valid_keys:
            result = service.resolve_path(key)
            assert isinstance(result, Path), f"{key} should return Path"


class TestConfigurationServiceDirectories:
    """Tests for ensure_directories_exist method."""

    def test_ensure_directories_exist_creates_log_dir(self, tmp_path, monkeypatch, clean_env):
        """ensure_directories_exist should create log directory."""
        # Override log directory to tmp_path
        log_dir = tmp_path / "test_logs"
        monkeypatch.setenv("SPRITEPAL_LOG_DIR", str(log_dir))

        service = ConfigurationService(app_root=tmp_path)
        assert not log_dir.exists()

        service.ensure_directories_exist()

        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_ensure_directories_exist_creates_cache_dir(self, tmp_path, monkeypatch, clean_env):
        """ensure_directories_exist should create cache directory."""
        # Override cache directory to tmp_path
        cache_dir = tmp_path / "test_cache"
        monkeypatch.setenv("SPRITEPAL_CACHE_DIR", str(cache_dir))

        service = ConfigurationService(app_root=tmp_path)
        assert not cache_dir.exists()

        service.ensure_directories_exist()

        assert cache_dir.exists()
        assert cache_dir.is_dir()

    def test_ensure_directories_exist_is_idempotent(self, tmp_path, monkeypatch, clean_env):
        """ensure_directories_exist should be safe to call multiple times."""
        log_dir = tmp_path / "test_logs"
        cache_dir = tmp_path / "test_cache"
        monkeypatch.setenv("SPRITEPAL_LOG_DIR", str(log_dir))
        monkeypatch.setenv("SPRITEPAL_CACHE_DIR", str(cache_dir))

        service = ConfigurationService(app_root=tmp_path)

        # Call multiple times - should not raise
        service.ensure_directories_exist()
        service.ensure_directories_exist()
        service.ensure_directories_exist()

        assert log_dir.exists()
        assert cache_dir.exists()


class TestConfigurationServiceEnvOverrides:
    """Tests for environment variable overrides."""

    def test_settings_dir_env_override(self, tmp_path, monkeypatch):
        """SPRITEPAL_SETTINGS_DIR should override settings file location."""
        settings_dir = tmp_path / "custom_settings"
        settings_dir.mkdir()
        monkeypatch.setenv("SPRITEPAL_SETTINGS_DIR", str(settings_dir))

        service = ConfigurationService(app_root=tmp_path)

        expected = settings_dir / ".spritepal_settings.json"
        assert service.settings_file == expected

    def test_cache_dir_env_override(self, tmp_path, monkeypatch):
        """SPRITEPAL_CACHE_DIR should override cache directory."""
        cache_dir = tmp_path / "custom_cache"
        monkeypatch.setenv("SPRITEPAL_CACHE_DIR", str(cache_dir))

        service = ConfigurationService(app_root=tmp_path)

        assert service.cache_directory == cache_dir

    def test_log_dir_env_override(self, tmp_path, monkeypatch):
        """SPRITEPAL_LOG_DIR should override log directory."""
        log_dir = tmp_path / "custom_logs"
        monkeypatch.setenv("SPRITEPAL_LOG_DIR", str(log_dir))

        service = ConfigurationService(app_root=tmp_path)

        assert service.log_directory == log_dir


class TestConfigurationServiceSetSettingsManager:
    """Tests for set_settings_manager method."""

    def test_set_settings_manager_updates_cache_directory(self, tmp_path, clean_env):
        """set_settings_manager should allow cache override after init."""
        service = ConfigurationService(app_root=tmp_path)

        # Initially no settings manager, uses default
        assert service.cache_directory == Path.home() / ".spritepal_rom_cache"

        # Set settings manager with custom cache location
        custom_cache = tmp_path / "custom_cache"
        mock_settings = MagicMock()
        mock_settings.get_cache_location.return_value = str(custom_cache)

        service.set_settings_manager(mock_settings)

        # Now should use custom location
        assert service.cache_directory == custom_cache


class TestConfigurationServiceRepr:
    """Tests for __repr__ method."""

    def test_repr_includes_key_info(self, tmp_path, clean_env):
        """__repr__ should include app_root and settings_file."""
        service = ConfigurationService(app_root=tmp_path)

        repr_str = repr(service)

        assert "ConfigurationService" in repr_str
        assert "app_root=" in repr_str
        assert "settings_file=" in repr_str
