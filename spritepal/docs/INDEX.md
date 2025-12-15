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
| [UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md](../UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md) | Comprehensive testing patterns |
| [TESTING_DEBUG_GUIDE_DO_NOT_DELETE.md](../TESTING_DEBUG_GUIDE_DO_NOT_DELETE.md) | Debugging test failures |
| [QT_TESTING_BEST_PRACTICES.md](QT_TESTING_BEST_PRACTICES.md) | pytest-qt specific patterns |

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

# Type check
uv run basedpyright core ui utils

# Run tests (headless)
QT_QPA_PLATFORM=offscreen uv run pytest tests --maxfail=1 --tb=short

# Run specific test
QT_QPA_PLATFORM=offscreen uv run pytest tests/path/test_file.py::test_name -vv
```
