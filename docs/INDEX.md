# SpritePal Documentation Index

This is the central entry point for all SpritePal documentation.

## Getting Started

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Project overview, installation, quick start, **Frame Mapping** |
| [CLAUDE.md](../CLAUDE.md) | Development workflow, tooling, testing quick reference |

## Core Documentation

| Document | Purpose |
|----------|---------|
| [architecture.md](architecture.md) | Layer structure, import rules, DI, dialogs, singletons, **Mesen integration**, **Frame Mapping** |
| [application_flows.md](application_flows.md) | Initialization, extraction, injection, error flows, **Frame Mapping workflow** |
| [testing_guide.md](testing_guide.md) | Comprehensive testing patterns, Qt signals, threading |
| [configuration_guide.md](configuration_guide.md) | Settings and configuration system |

## Frame Mapping Workspace

| Document | Purpose |
|----------|---------|
| [README.md → Frame Mapping](../README.md#frame-mapping-workspace) | 4-zone UI layout, workflow, features |
| [architecture.md → Frame Mapping](architecture.md#frame-mapping-subsystem) | Frame Mapping architecture and data flow |
| [application_flows.md → Frame Mapping](application_flows.md#8-frame-mapping-workflow) | Frame pairing and injection workflow |

## Mesen 2 Integration

| Document | Purpose |
|----------|---------|
| [mesen2_integration/README.md](../mesen2_integration/README.md) | Lua scripts, click-to-find workflow, batch files |
| [mesen2/architecture.md](mesen2/architecture.md) | Python subsystem architecture, data flow, SA-1 address space |

## Test Documentation

| Document | Purpose |
|----------|---------|
| [tests/README.md](../tests/README.md) | Test suite overview, fixtures, headless testing |

## Domain Knowledge

| Document | Purpose |
|----------|---------|
| [docs/mesen2/00_STABLE_SNES_FACTS.md](mesen2/00_STABLE_SNES_FACTS.md) | SNES hardware facts (VRAM, OBJSEL, tiles) |
| [docs/mesen2/01_BUILD_SPECIFIC_CONTRACT.md](mesen2/01_BUILD_SPECIFIC_CONTRACT.md) | Mesen2 build-specific API contract + tool runbook |
| [docs/mesen2/02_DATA_CONTRACTS.md](mesen2/02_DATA_CONTRACTS.md) | Capture JSON schema and invariants |
| [docs/mesen2/03_GAME_MAPPING_KIRBY_SA1.md](mesen2/03_GAME_MAPPING_KIRBY_SA1.md) | Kirby Super Star SA-1 mapping notes |
| [docs/mesen2/04_TROUBLESHOOTING.md](mesen2/04_TROUBLESHOOTING.md) | Fail-fast checks and diagnostics |

## Quick Reference

### Common Tasks

| Task | Document |
|------|----------|
| Add a new feature | [architecture.md](architecture.md) → Import Rules |
| Write tests | [tests/README.md](../tests/README.md) → Fixture Quick Reference |
| Create a dialog | [architecture.md](architecture.md) → Dialog Patterns |
| Signal cleanup in dialogs | [architecture.md](architecture.md) → Signal Disconnection Pattern |
| Understand DI | [architecture.md](architecture.md) → Dependency Injection |
| Debug singletons | [architecture.md](architecture.md) → Singletons and Cleanup |
| Trace data flows | [application_flows.md](application_flows.md) |
| Qt signals/workers | [testing_guide.md](testing_guide.md) → Signal Reference |
| Find sprite ROM offset | [mesen2_integration/README.md](../mesen2_integration/README.md) → Click-to-Find |
| Understand Mesen integration | [mesen2/architecture.md](mesen2/architecture.md) |
| Run Mesen2 capture pipeline | [docs/mesen2/01_BUILD_SPECIFIC_CONTRACT.md](mesen2/01_BUILD_SPECIFIC_CONTRACT.md) → Runbook |
| Use embedded Sprite Editor | [application_flows.md](application_flows.md) → Section 5 (Sprite Editor Tab) |
| Map AI frames to game frames | [README.md](../README.md) → Frame Mapping Workspace |
| Frame alignment and injection | [application_flows.md](application_flows.md) → Section 8 (Frame Mapping) |
| Keyboard shortcuts | [README.md](../README.md) → Keyboard Shortcuts |

### Key Commands

```bash
# Lint
uv run ruff check .
uv run ruff check . --fix

# Type check
uv run basedpyright core ui utils

# Run tests
uv run pytest

# Quick triage
uv run pytest --tb=no -q

# Re-run failures
uv run pytest --lf -vv --tb=short

# Specific test (serial, verbose)
uv run pytest tests/path/test_file.py::test_name -vv --tb=long -s -n 0
```

---

*Last updated: January 24, 2026 (Test directory structure consolidated)*
