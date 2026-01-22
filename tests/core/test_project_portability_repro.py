import json
import shutil
from pathlib import Path
from core.frame_mapping_project import FrameMappingProject, AIFrame

def test_project_portability_repro(tmp_path):
    # Setup: Create a project in one directory
    project_dir = tmp_path / "project_a"
    project_dir.mkdir()
    
    ai_dir = project_dir / "ai_frames"
    ai_dir.mkdir()
    ai_path = ai_dir / "frame_0.png"
    ai_path.touch()
    
    project_path = project_dir / "project.spritepal-mapping.json"
    project = FrameMappingProject(name="Test Project", ai_frames_dir=ai_dir)
    project.ai_frames.append(AIFrame(path=ai_path, index=0))
    project.save(project_path)
    
    # Verify relative paths are stored
    with open(project_path, "r") as f:
        data = json.load(f)
        # It should be relative now
        assert data["ai_frames_dir"] == "ai_frames"
        assert data["ai_frames"][0]["path"] == "ai_frames/frame_0.png"
        
    # Move the project to a new location
    new_project_dir = tmp_path / "project_b"
    new_project_dir.mkdir()
    
    # Simulate moving the whole tree
    shutil.copytree(ai_dir, new_project_dir / "ai_frames")
    new_project_path = new_project_dir / "project.spritepal-mapping.json"
    shutil.move(str(project_path), str(new_project_path))
    
    # DELETE ORIGINAL to break absolute paths
    shutil.rmtree(project_dir)
    
    # Load from new location
    loaded_project = FrameMappingProject.load(new_project_path)
    
    assert loaded_project.ai_frames_dir.exists(), f"Path {loaded_project.ai_frames_dir} should exist but it points to old location"
    assert loaded_project.ai_frames[0].path.exists(), f"Path {loaded_project.ai_frames[0].path} should exist"

def test_arrangement_config_portability(tmp_path):
    from core.arrangement_persistence import ArrangementConfig
    
    project_dir = tmp_path / "project_config_a"
    project_dir.mkdir()
    
    overlay_path = project_dir / "overlay.png"
    overlay_path.touch()
    
    config_path = project_dir / "test.arrangement.json"
    config = ArrangementConfig(
        rom_hash="hash",
        rom_offset=0x123456,
        sprite_name="test",
        grid_dimensions={"rows": 1, "cols": 1},
        arrangement_order=[],
        groups=[],
        total_tiles=1,
        logical_width=8,
        overlay_path=str(overlay_path)
    )
    config.save(config_path)
    
    # Verify relative path in JSON
    with open(config_path, "r") as f:
        data = json.load(f)
        assert data["overlay_path"] == "overlay.png"
        
    # Move
    new_project_dir = tmp_path / "project_config_b"
    new_project_dir.mkdir()
    shutil.copy(overlay_path, new_project_dir / "overlay.png")
    new_config_path = new_project_dir / "test.arrangement.json"
    shutil.move(config_path, new_config_path)
    shutil.rmtree(project_dir)
    
    # Load
    loaded = ArrangementConfig.load(new_config_path)
    assert Path(loaded.overlay_path).exists()
    assert Path(loaded.overlay_path).name == "overlay.png"
    # It should be absolute now because load() resolves it
    assert Path(loaded.overlay_path).is_absolute()