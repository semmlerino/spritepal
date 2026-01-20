import os
import stat
from pathlib import Path

import pytest

from core.sprite_project import SpriteProject, SpriteProjectError


def create_dummy_project() -> SpriteProject:
    """Helper to create a minimal valid project."""
    return SpriteProject(
        name="Test Sprite",
        width=16,
        height=16,
        tile_data=b"\x00" * 128,  # 4 tiles * 32 bytes
        tile_count=4
    )

def test_save_load_path_with_spaces(tmp_path: Path):
    """Verify handling of paths with spaces."""
    # Setup
    space_dir = tmp_path / "My Projects Folder"
    space_dir.mkdir()
    project_path = space_dir / "my sprite.spritepal"
    project = create_dummy_project()

    # Execute Save
    project.save(project_path)
    assert project_path.exists()

    # Execute Load
    loaded = SpriteProject.load(project_path)
    assert loaded.name == project.name
    assert loaded.tile_data == project.tile_data

def test_save_load_unicode_path(tmp_path: Path):
    """Verify handling of paths with non-ASCII characters."""
    # Setup
    unicode_dir = tmp_path / "プロジェクト" # "Project" in Japanese
    unicode_dir.mkdir()
    project_path = unicode_dir / "スプライト.spritepal" # "Sprite.spritepal"
    project = create_dummy_project()

    # Execute Save
    project.save(project_path)
    assert project_path.exists()

    # Execute Load
    loaded = SpriteProject.load(project_path)
    assert loaded.name == project.name

def test_save_to_readonly_directory(tmp_path: Path):
    """Verify graceful failure when saving to read-only directory."""
    # Setup
    ro_dir = tmp_path / "readonly_dir"
    ro_dir.mkdir()
    project_path = ro_dir / "test.spritepal"
    project = create_dummy_project()

    # Make directory read-only (r-x) preventing file creation/renaming
    ro_dir.chmod(0o555) 

    try:
        with pytest.raises(SpriteProjectError) as exc_info:
            project.save(project_path)
        assert "Failed to save project" in str(exc_info.value)
    finally:
        # Cleanup: restore permissions so tmp_path can be cleaned up
        ro_dir.chmod(0o755)
