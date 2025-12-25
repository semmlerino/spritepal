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
# Using uv (recommended) - run from spritepal/ directory
cd spritepal
uv run python -c "
from ui.main_window import MainWindow
from core.controller import SpritePalController
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
from core.controller import SpritePalController
from ui.main_window import MainWindow

controller = SpritePalController()
window = MainWindow(controller)
window.show()
```

## Documentation

- [docs/INDEX.md](docs/INDEX.md) - Documentation index
- [docs/architecture.md](docs/architecture.md) - Architecture guidelines
- [tests/README.md](tests/README.md) - Testing guide

## License

MIT

---

*Last updated: December 25, 2025*
