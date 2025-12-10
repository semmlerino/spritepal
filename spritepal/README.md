# SpritePal

A PySide6-based sprite extraction and editing tool for SNES ROM hacking.

## Features

- Extract sprites from SNES ROMs with HAL compression support
- Edit and preview sprites with palette management
- Inject modified sprites back into ROMs
- Multi-threaded thumbnail generation for fast browsing
- WCAG 2.1 compliant keyboard navigation

## Quick Start

Launch the UI from the project root (`exhal-master/`):

```bash
# Using uv (recommended)
uv run python -c "
from spritepal.ui.main_window import MainWindow
from spritepal.core.controller import SpritePalController
from PySide6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
controller = SpritePalController()
window = MainWindow(controller)
window.show()
sys.exit(app.exec())
"
```

## Development Setup

```bash
# Install uv if needed
pip install uv

# Sync dependencies (from exhal-master/)
uv sync --extra dev

# Run tests (use offscreen backend for headless environments)
QT_QPA_PLATFORM=offscreen uv run pytest spritepal/tests -v

# Run fast headless tests only
QT_QPA_PLATFORM=offscreen uv run pytest spritepal/tests -m "headless and not slow"

# Run GUI tests (offscreen backend works without display)
QT_QPA_PLATFORM=offscreen uv run pytest spritepal/tests -m gui

# Lint
uv run ruff check spritepal
uv run ruff check spritepal --fix  # Auto-fix

# Type check
uv run basedpyright spritepal/core spritepal/ui spritepal/utils
```

## Sample Assets

Requires SNES ROM files for testing (e.g., Kirby Super Star). ROM files are not included due to copyright.

## Requirements

- Python 3.11+
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
from spritepal.core.controller import SpritePalController
from spritepal.ui.main_window import MainWindow

controller = SpritePalController()
window = MainWindow(controller)
window.show()
```

## License

MIT
