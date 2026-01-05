# Unified Sprite Editor

A consolidated PyQt6/PySide6 application for SNES sprite extraction, pixel-level editing, and injection. Combines the capabilities of the legacy `sprite_editor/` and `pixel_editor/` into a single Extract → Edit → Inject workflow.

## Quick Start

### Launch the Editor

```bash
cd spritepal
python launch_editor.py
```

Or with uv:
```bash
uv run python launch_editor.py
```

### Features

- **Extract Tab**: Extract sprites from SNES ROM VRAM dumps
  - Supports custom offset and size
  - Multi-palette preview with OAM palette mapping
  - CGRAM integration for accurate color rendering

- **Edit Tab**: Pixel-level sprite editing
  - Drawing tools: Pencil, Fill, Color Picker
  - Adjustable brush size
  - Undo/Redo system
  - Real-time grid overlay

- **Inject Tab**: Inject edited sprites back into VRAM dumps
  - PNG to SNES 4bpp tile conversion
  - Validation and error reporting
  - Output file generation

- **Multi-Palette Tab**: Advanced palette management
  - Load and preview all 16 palettes from CGRAM
  - OAM-correct palette assignments
  - Palette validation

## Architecture

### Directory Structure

```
ui/sprite_editor/
├── __init__.py                    # Package exports
├── application.py                 # Main app entry point
├── constants.py                   # SNES format constants
├── core/                          # Shared utilities
│   ├── tile_utils.py              # 4bpp tile encoding/decoding
│   ├── palette_utils.py           # BGR555 ↔ RGB888 conversion
│   └── file_validators.py         # File validation helpers
├── models/                        # Data models
│   ├── image_model.py             # Pixel grid management
│   ├── palette_model.py           # Palette data
│   ├── vram_model.py              # VRAM file handling
│   └── project_model.py           # Project state
├── services/                      # Business logic
│   ├── sprite_renderer.py         # Sprite extraction
│   ├── image_converter.py         # PNG ↔ SNES conversion
│   ├── vram_service.py            # VRAM I/O
│   └── oam_palette_mapper.py      # OAM palette assignment
├── managers/                      # Qt managers
│   ├── tool_manager.py            # Drawing tools
│   ├── undo_manager.py            # Undo/Redo
│   └── settings_manager.py        # Persistent settings
├── controllers/                   # MVC controllers
│   ├── main_controller.py         # Workflow orchestration
│   ├── extraction_controller.py   # Extract tab logic
│   ├── editing_controller.py      # Edit tab logic
│   ├── injection_controller.py    # Inject tab logic
│   └── base_controller.py         # Common base class
├── workers/                       # Background threads
│   ├── extraction_worker.py       # Async extraction
│   ├── injection_worker.py        # Async injection
│   ├── file_io_worker.py          # Async file operations
│   └── base_worker.py             # Worker base class
├── views/                         # Qt UI components
│   ├── main_window.py             # Main application window
│   ├── tabs/                      # Tab implementations
│   │   ├── extract_tab.py
│   │   ├── edit_tab.py
│   │   ├── inject_tab.py
│   │   └── multi_palette_tab.py
│   ├── panels/                    # UI panels
│   │   ├── tool_panel.py
│   │   ├── palette_panel.py
│   │   ├── preview_panel.py
│   │   └── options_panel.py
│   ├── widgets/                   # Custom widgets
│   │   ├── pixel_canvas.py        # Sprite editing canvas
│   │   ├── color_palette_widget.py
│   │   └── zoomable_scroll_area.py
│   └── dialogs/                   # Dialog windows
│       └── palette_switcher_dialog.py
└── tests/                         # Unit tests
```

## Key Components

### Models

**ImageModel** - Manages pixel grid data
```python
model = ImageModel()
model.set_data(numpy_array)  # Set 2D index array
pixel = model.get_pixel(x, y)
model.set_pixel(x, y, color_index)
```

**VRAMModel** - Handles VRAM/CGRAM/OAM file operations
```python
vram = VRAMModel()
vram.set_vram_file("dump.bin")
data = vram.read_vram_data(offset, size)
```

**PaletteModel** - Palette data with multiple format support
```python
palette = PaletteModel()
palette.from_json_file("palette.json")
palette.from_cgram_file("cgram.bin", palette_num=8)
```

### Services

**SpriteRenderer** - Extract sprites from VRAM
```python
renderer = SpriteRenderer()
image, tiles = renderer.extract(vram_file, offset, size)
```

**ImageConverter** - Convert PNG ↔ SNES 4bpp format
```python
converter = ImageConverter()
tile_data, count = converter.png_to_tiles("sprite.png")
```

**VRAMService** - Direct VRAM file operations
```python
service = VRAMService()
data = service.read(vram_file, offset, size)
service.inject(tile_data, vram_file, offset, output_file)
```

### Managers

**ToolManager** - Drawing tool management
```python
tools = ToolManager()
tools.set_tool("pencil")
tool = tools.get_tool()
tool.on_press(x, y, color, image_model)
```

**UndoManager** - Undo/Redo system
```python
undo = UndoManager()
undo.record_action(action_name, undo_func, redo_func)
undo.undo()
undo.redo()
```

**SettingsManager** - Persistent settings
```python
settings = SettingsManager()
settings.set("zoom_level", 4)
settings.save_settings()
```

### Controllers

**MainController** - Orchestrates workflow
- Connects extraction → editing → injection
- Manages tab switching
- Handles file operations

**EditingController** - Manages editing operations
- Tool selection and configuration
- Pixel drawing operations
- Undo/Redo triggering

**ExtractionController** - Extraction workflow
- File validation
- VRAM/CGRAM loading
- Worker thread management

## SNES Format

### 4bpp Tile Format
- 8×8 pixel tiles
- 4 bits per pixel (16 colors per tile)
- 32 bytes per tile
- Stored in SNES VRAM (0x0000-0xFFFF)

### Color Format
- SNES uses BGR555 (5 bits each for blue, green, red)
- Editor converts to RGB888 for display
- CGRAM holds 16 palettes × 16 colors

### VRAM Layout
```
0x0000-0x1FFF: Sprite tiles 0-255
0x2000-0x3FFF: Sprite tiles 256-511
0x4000-0x5FFF: Sprite tiles 512-767
0x6000-0x7FFF: Background tiles
...
```

## File Formats

### JSON Palette Format
```json
{
  "palette": {
    "name": "Kirby Palette",
    "colors": [[255, 0, 0], [0, 255, 0], ...],
    "format": "RGB888"
  }
}
```

### VRAM Dump
Raw binary file containing VRAM memory (typically 64KB for standard SNES).

### CGRAM Dump
Raw binary file containing color RAM (512 bytes = 16 palettes × 16 colors × 2 bytes).

## Running Tests

```bash
# Unit tests
uv run pytest tests/ -v

# Integration tests
uv run pytest tests/ -k "integration" -v

# With coverage
uv run pytest tests/ --cov=ui/sprite_editor --cov-report=html
```

## Configuration

Settings are stored in `~/.spritepal/editor_settings.json`:

```json
{
  "default_offset": 49152,
  "default_size": 16384,
  "default_tiles_per_row": 16,
  "zoom_level": 4,
  "show_grid": true,
  "brush_size": 1,
  "last_tool": "pencil"
}
```

## Development

### Adding a New Tool

1. Create tool class in `managers/tool_manager.py`:
```python
class MyTool(Tool):
    def on_press(self, x, y, color, image_model):
        # Implement tool logic
        pass
```

2. Register in `ToolManager.tools` dict
3. Add UI button in `views/panels/tool_panel.py`

### Adding a New Tab

1. Create tab class in `views/tabs/`:
```python
class MyTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Setup UI
```

2. Register in `views/main_window.py`
3. Create corresponding controller in `controllers/`

## Integration with SpritePal

The unified editor is integrated into the main SpritePal application:

```python
from ui.sprite_editor import SpriteEditorApplication

app = SpriteEditorApplication()
app.run()
```

Can also be used as standalone:

```bash
python launch_editor.py
```

## Known Limitations

- Maximum sprite size: 64KB (limited by VRAM)
- Palette editing not yet supported (view-only)
- No batch operations
- Detached editor window not yet implemented

## Future Enhancements

- Palette editing interface
- Batch sprite operations
- Animation preview
- Sprite collision map editor
- ROM patching support
- Custom compression formats

## References

- SNES Development Manual: Tile format and color space
- Mesen-X Documentation: Debugger and memory dumping
- SpritePal Docs: ROM structure and sprite layout
