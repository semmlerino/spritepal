# SpritePal Documentation Index

This is the central entry point for all SpritePal documentation. Start here to find what you need.

## Getting Started

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Project overview, installation, and quick start |
| [CLAUDE.md](../CLAUDE.md) | Development workflow and tooling |

## Architecture

| Document | Purpose |
|----------|---------|
| [architecture.md](architecture.md) | Layer structure, import rules, **DI patterns**, **singletons & cleanup** |

## UI Development

| Document | Purpose |
|----------|---------|
| [dialog_development_guide.md](dialog_development_guide.md) | Dialog patterns, singleton dialogs, lifecycle management |
| [main_window_flows.md](main_window_flows.md) | Key user action flows through MainWindow |

## Testing

| Document | Purpose |
|----------|---------|
| [tests/README.md](../tests/README.md) | Test suite overview, **fixture quick reference** |
| [testing_guide.md](testing_guide.md) | Comprehensive testing patterns (Qt, threading, mocking) |
| [QT_TESTING_BEST_PRACTICES.md](QT_TESTING_BEST_PRACTICES.md) | pytest-qt specific patterns |
| [WORKER_PATTERNS.md](WORKER_PATTERNS.md) | Background worker patterns and lifecycle |

## Domain Knowledge

| Document | Purpose |
|----------|---------|
| [SPRITE_LEARNINGS_DO_NOT_DELETE.md](../SPRITE_LEARNINGS_DO_NOT_DELETE.md) | Sprite extraction knowledge, SNES formats |
| [DEV_NOTES.md](../DEV_NOTES.md) | Mesen2 integration notes, historical context |

## Quick Reference

### Common Tasks

- **Add a new feature**: Start with [architecture.md](architecture.md) for import rules
- **Write tests**: See [tests/README.md](../tests/README.md) § Fixture Quick Reference
- **Create a dialog**: Follow [dialog_development_guide.md](dialog_development_guide.md)
- **Understand DI**: Read [architecture.md](architecture.md) § Dependency Injection
- **Debug singleton issues**: Check [architecture.md](architecture.md) § Singletons and Cleanup
- **Trace MainWindow flows**: See [main_window_flows.md](main_window_flows.md)

### Key Commands

```bash
# From spritepal/ directory

# Lint
uv run ruff check .
uv run ruff check . --fix  # Auto-fix

# Type check
uv run basedpyright core ui utils

# Run tests (QT_QPA_PLATFORM=offscreen is set automatically by conftest.py)
uv run pytest

# Quick triage for large test suite
uv run pytest --tb=no -q

# Re-run failures with details
uv run pytest --lf -vv --tb=short

# Run specific test (serial, verbose)
uv run pytest tests/path/test_file.py::test_name -vv --tb=long -s -n 0
```

---

*Last updated: December 21, 2025*
