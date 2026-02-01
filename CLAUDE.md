# SpritePal Development Guidelines

**What is SpritePal?** A PySide6 desktop app for editing SNES sprite graphics. Key workflows: Extract sprites from ROM → Edit in pixel editor → Inject back. Also supports frame mapping of AI-generated frames for sprite animation replacement.

---

## TL;DR

**Stack:** PySide6 | Python 3.12+ | uv | `pyproject.toml`

**Workflow:**
```bash
ruff check . && ruff format . && basedpyright core ui utils && pytest
git add <files> && git commit -m "fix: description"
```

**Will crash or fail tests:**
- No `QPixmap` in worker threads → use `ThreadSafeTestImage`
- No `time.sleep()` in Qt tests → use `qtbot.wait(ms)`
- Always: `with qtbot.waitSignal(signal, timeout=...)`
- Use `tmp_path` fixture, never hardcode paths

**Testing:** `pytest` for TDD; `pytest -n auto --dist=loadscope` for full suite

**Launch:** `uv run python launch_spritepal.py`

---

## Development Workflow

```bash
uv run ruff check .                # Lint
uv run ruff format .               # Format
uv run basedpyright core ui utils  # Type check
uv run pytest                      # Tests (serial)
uv run pytest -n auto --dist=loadscope  # Tests (parallel, ~3 min)
```

**Environment:** `uv sync` to install; `uv sync --extra dev` for dev deps.

### Test Commands

| Goal | Command |
|------|---------|
| Quick triage | `pytest --tb=no -q 2>&1 \| tee /tmp/pytest.log` |
| Re-run failures | `pytest --lf -vv --tb=short` |
| Single test | `pytest tests/path/test.py::test_name -vv -s` |
| Unit tests only | `pytest tests/unit/ -q` |
| Stop on first fail | `pytest -x -vv` |

**Guides:** [docs/testing_guide.md](docs/testing_guide.md) | [tests/README.md](tests/README.md)

---

## Code Patterns

### Import Rules

```
UI ──→ Core ──→ Utils ──→ Stdlib only
```

- **UI** imports: core, utils, PySide6
- **Core** imports: utils, stdlib (no UI)
- **Utils** imports: stdlib only

### Manager Access

Never instantiate managers directly. Access via `AppContext`:

```python
from core.app_context import get_app_context
context = get_app_context()
state_mgr = context.application_state_manager
```

**In tests:** Use `app_context` fixture (provides clean state per-test).

### DI Order

`MainWindow.__init__()` creates UI before services. Use deferred injection with setters that cascade to children. Trace `__init__` → `_setup_ui()` → `_setup_managers()` before refactoring.

---

## Agent Delegation

**Default to agents for implementation.** After planning/analysis, delegate execution to agents. This preserves orchestrator context for verification and synthesis. Also delegate high-volume operations (full test runs, extensive exploration) to keep verbose output isolated.

### When to Delegate

| Delegate | Handle Directly |
|----------|-----------------|
| Phase is well-defined (know exactly what changes) | Tight exploration loop (reading informs next read) |
| Implementation is mechanical, even single-file | Complex reasoning required mid-edit |
| Prompt can fully specify the work | Need to adapt based on what you find |
| Independent files (parallelize with multiple agents) | Changes are sequential/dependent |

### Planning with Agents

When writing implementation plans, specify **agent** and **model** for each phase:

```markdown
## Phase N: Description
**Agent:** python-implementation-specialist | **Model:** haiku
**Parallel:** Yes (with Phase M) | No
**Rationale:** [why this agent + model]
```

### Built-in Agent Selection

| Work Type | Agent | Model |
|-----------|-------|-------|
| Codebase questions, understanding flow | `Explore` | haiku |
| Architecture design, tradeoff analysis | `Plan` | sonnet |
| Mechanical changes (delete, rename, pattern replace) | `python-implementation-specialist` | haiku |
| Standard implementation | `python-implementation-specialist` | sonnet |
| Complex patterns (metaclasses, protocols, decorators) | `python-expert-architect` | sonnet |
| Cross-cutting refactors, architecture changes | `python-expert-architect` | opus |
| Code review (routine) | `python-code-reviewer` | haiku |
| Code review (correctness matters) | `python-code-reviewer` | sonnet |
| Heisenbugs, security analysis | Orchestrator + specialists | opus |

**Model tradeoff:** Haiku is ~10x cheaper/faster. Use when prompt fully specifies work. Sonnet when judgment required. Opus for genuinely hard problems.

### Prompt Quality

Agents execute what you specify—vague prompts yield vague results.

- **Context-aware agents** see full conversation history—reference earlier context instead of repeating it
- Include file paths, symbol names, line numbers
- For parallel agents: "You own ONLY: file_a.py, file_b.py"
- Specify verification: "verify syntax after each edit"

### Background and Resume

- Use `run_in_background: true` for long-running verification (test suite, type checking) while continuing other work
- **Resume agents** for follow-up work on the same task—preserves full context from previous execution
- Check background results with `Read` on the output file
- Subagents cannot spawn other subagents—chain from the main conversation instead

### Post-Implementation

Spawn `python-code-reviewer` after multi-file or non-obvious changes, before committing. Skip for trivial single-file edits where correctness is obvious.

### Task Completion Checklist

Before reporting task completion, verify ALL of the following:

1. Tests pass (`uv run pytest` on affected areas)
2. Lint passes (`uv run ruff check .`)
3. Types pass (`uv run basedpyright core ui utils`)
4. **Committed** (if checks pass and work is coherent)
5. Then report completion

**NEVER report "done" or give a summary before committing.** The commit is part of completing the task, not a follow-up action.

---

## Gotchas

Qt/PySide6 pitfalls from real bugs:

| Pitfall | Why | Fix |
|---------|-----|-----|
| `QPixmap` in worker thread | Not thread-safe; crashes silently | `ThreadSafeTestImage` |
| `if pos:` for QPoint | `QPoint(0,0)` is falsy | `if pos is not None:` |
| `waitSignal()` no context | Signal emits before wait | `with qtbot.waitSignal(...):` |
| `time.sleep()` in tests | Blocks Qt event loop | `qtbot.wait(ms)` |
| `gc.collect()` in Qt cleanup | Finalizes during threads → segfault | `deleteLater()` + `processEvents()` |
| Mock inherits `QDialog` | Creates real dialog | Inherit `QObject` instead |
| Mock at definition site | Python patches at import site | `@patch('module.that.imports.Class')` |
| Multiple `QApplication` | One per process | Let pytest-qt manage |

**Safe cleanup:**
```python
worker.requestInterruption()
worker.quit()
worker.wait(5000)
worker.deleteLater()
QApplication.processEvents()
```

---

## Reference

### Key Locations

| Looking for... | Location |
|----------------|----------|
| Managers | `core/managers/` (`core_operations_manager.py`, `application_state_manager.py`) |
| Sprite Editor | `ui/sprite_editor/` |
| Frame Mapping | `ui/frame_mapping/` (controller, views, dialogs) |
| AppContext | `core/app_context.py` |
| Test fixtures | `tests/fixtures/` |
| Qt mocks | `tests/infrastructure/qt_mocks.py` |

**Project structure:** See [docs/architecture.md](docs/architecture.md)

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `PYTEST_TIMEOUT_MULTIPLIER` | Scale timeouts for slow CI |
| `SPRITEPAL_EXHAL_PATH` / `SPRITEPAL_INHAL_PATH` | HAL binary paths |
| `SPRITEPAL_LEAK_MODE` | `warn` (local) / `fail` (CI) |
| `SPRITEPAL_INJECT_DEBUG` | Save debug images to temp |
| `QT_QPA_PLATFORM` | `offscreen` for headless |

### Type Checking

- Use `| None` not `Optional`
- Qt signals need annotations: `finished = Signal(str, int)`
- Use `Mapping[str, object]` for read-only dict params

---

## Known Limitations

### Palette Index Painting

The injection pipeline converts to RGBA for compositing. Palette indices are re-quantized via RGB matching. If palette has duplicate colors, they'll map to the same index.

**Workaround:** Ensure all palette colors are unique.

---

## External Tools

**Mesen 2 Integration:** SNES emulator for runtime sprite capture. See [mesen2_integration/README.md](mesen2_integration/README.md).

Quick start:
- Find ROM offset: `run_sprite_rom_finder.bat` → click sprite → read `FILE: 0xNNNNNN`
- Capture: `run_sprite_capture.bat` → `mesen2_exchange/sprite_capture_*.json`
