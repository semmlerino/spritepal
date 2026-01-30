# SpritePal

A PySide6-based sprite extraction and editing tool for SNES ROM hacking.

## Features

- **Extract sprites** from SNES ROMs with HAL compression support
- **Edit sprites** directly in embedded editor with full Extract→Edit→Inject workflow
- **Inject modified sprites** back into ROMs with compression
- **Frame Mapping Workspace**: Map AI-generated sprite frames to game animation frames captured from Mesen 2
- **Modern IDE-like UI**: Dock-based layout (QDockWidget) for flexible workspace management
- **Mesen 2 integration**: Click on sprites in emulator to find ROM offset automatically
- **Workbench Canvas**: Interactive sprite alignment with zoom, pan, and in-game preview
- **Multi-threaded thumbnail** generation for fast browsing
- **Keyboard shortcuts** for tab navigation (Ctrl+1/2/3/4) and quick capture access (F6)
- **WCAG 2.1 compliant** keyboard navigation
- **Session persistence** saves window state, file paths, and recent captures
- **Segmented UI controls**: Improved mode switching using `SegmentedToggle` widgets
- **Toggleable backgrounds** in sprite editor for better visibility during editing
- **Revert to Original** button to restore a sprite from ROM if edits go wrong
- **Per-category logging** control via Settings → Logging tab for detailed debugging
- **390+ UI integration tests** for signal-driven workflow validation

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Ctrl+1** | Switch to ROM Extraction tab |
| **Ctrl+2** | Switch to VRAM Extraction tab |
| **Ctrl+3** | Switch to Sprite Editor tab |
| **Ctrl+4** | Switch to Frame Mapping tab |
| **F6** | Jump to last Mesen2 capture in Sprite Editor |

## Quick Start

Launch the UI from the `spritepal/` directory:

```bash
# Using uv (recommended)
cd spritepal
uv run python launch_spritepal.py
```

## Development Setup

```bash
# Install uv if needed
pip install uv

# Sync dependencies (from spritepal/)
uv sync --extra dev

# Run tests (QT_QPA_PLATFORM=offscreen is set automatically by conftest.py)
uv run pytest

# Quick triage (for large test suites)
uv run pytest --tb=no -q

# Re-run only failures with details
uv run pytest --lf -vv --tb=short

# Run specific test (serial, verbose)
uv run pytest tests/path/test_file.py::test_name -vv --tb=long -s -n 0

# Lint
uv run ruff check .
uv run ruff check . --fix  # Auto-fix

# Type check
uv run basedpyright core ui utils
```

## Sample Assets

Requires SNES ROM files for testing (e.g., Kirby Super Star). ROM files are not included due to copyright.

## Requirements

- Python 3.12+
- PySide6 >= 6.5.0
- uv (for development)

## Installation

```bash
pip install -e .
```

For development with all tools:

```bash
pip install -e ".[dev]"
```

## Programmatic Usage

```python
# Run from spritepal/ directory
import sys

from core.app_context import create_app_context
from core.configuration_service import ConfigurationService
from launch_spritepal import SpritePalApp

# Initialize configuration and app context (required)
config_service = ConfigurationService()
config_service.ensure_directories_exist()

context = create_app_context(
    "SpritePal",
    settings_path=config_service.settings_file,
    configuration_service=config_service,
)

# Create and run application
app = SpritePalApp(sys.argv, context=context)
sys.exit(app.exec())
```

## Documentation

- [docs/INDEX.md](docs/INDEX.md) - Documentation index
- [docs/architecture.md](docs/architecture.md) - Architecture guidelines
- [tests/README.md](tests/README.md) - Testing guide

## Embedded Sprite Editor

SpritePal includes an embedded sprite editor as the 3rd tab in the main window. The editor provides:

- **Extract**: Load sprites from ROM using hex offset
- **Edit**: Modify sprite pixels and manage palettes
- **Inject**: Repack and compress modified sprites back into ROM
- **Multi-Palette**: Manage alternative palette variations

### Using with Mesen 2

1. Launch Mesen 2 with the Lua script that finds sprite ROM offsets
2. Click on a sprite in the emulator
3. The script outputs the ROM offset
4. Double-click the captured offset in SpritePal's Recent Captures panel
5. The sprite editor opens automatically with that offset loaded

For details on Mesen 2 integration, see [mesen2_integration/README.md](mesen2_integration/README.md).

## Frame Mapping Workspace

The Frame Mapping workspace (4th tab) helps map AI-generated sprite frames to game animation frames:

**4-Zone Layout:**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Toolbar: [Load AI Frames] [Import Capture] [Import Dir] [Load] [Save] [Inject] │
├────────────────┬─────────────────────────────┬─────────────────────────────┤
│                │                             │                             │
│  AI FRAMES     │     WORKBENCH CANVAS        │   CAPTURES LIBRARY          │
│  (Left Pane)   │     (Center Top)            │   (Right Pane)              │
│                │                             │                             │
├────────────────┼─────────────────────────────┤                             │
│                │                             │                             │
│                │   MAPPINGS DRAWER           │                             │
│                │   (Center Bottom)           │                             │
│                │                             │                             │
└────────────────┴─────────────────────────────┴─────────────────────────────┘
```

**Workflow:**
1. Load AI-generated sprite frames (PNG files)
2. Import game captures from Mesen 2
3. Pair frames by selecting one from each side
4. Align sprites using the Workbench Canvas with zoom/pan controls
5. Toggle in-game preview to see composite result
6. Inject paired frames directly to ROM

**Features:**
- **Contiguous tile grouping** for multi-tile sprites
- **In-game preview toggle** to see final sprite appearance
- **Zoom and pan** for precise alignment
- **ROM offset tracking** for direct injection
- **Auto-load last project** on startup

## License

MIT

---

*Last updated: January 30, 2026*
