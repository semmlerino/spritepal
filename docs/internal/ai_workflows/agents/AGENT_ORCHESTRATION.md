# Agent Orchestration Guide

Unified reference for agent selection, parallel execution rules, and common workflows.

---

## Agent Lookup

### Development Agents

| Agent | Model | Use When | Key Capabilities |
|-------|-------|----------|------------------|
| **python-code-reviewer** | Sonnet | Code review, quality analysis | Bug detection, style violations, test coverage |
| **python-implementation-specialist** | Sonnet | Standard implementation | CRUD, utilities, straightforward features |
| **python-expert-architect** | Opus | Complex patterns, async, frameworks | Decorators, metaclasses, concurrency |
| **code-refactoring-expert** | Opus | Improve structure, reduce tech debt | Safe refactoring, pattern application |

### Testing Agents

| Agent | Model | Use When | Key Capabilities |
|-------|-------|----------|------------------|
| **test-development-master** | Sonnet | TDD, test creation, coverage | Red-green-refactor, pytest, Qt testing |
| **test-type-safety-specialist** | Sonnet | Type-safe test code | Mock typing, fixture type safety |
| **type-system-expert** | Sonnet | Type system, protocols | Type inference, protocol conformance |

### Qt Agents

| Agent | Model | Use When | Key Capabilities |
|-------|-------|----------|------------------|
| **qt-ui-modernizer** | Opus | UI/UX redesign | QSS styling, animations, usability |
| **qt-modelview-painter** | Opus | Model/View, custom painting | QAbstractItemModel, QPainter |
| **qt-concurrency-architect** | Opus | Qt threading issues | Signal-slot threading, event loops |
| **ui-ux-validator** | Sonnet | UI validation | Accessibility, keyboard nav, UX |

### Debugging Agents

| Agent | Model | Use When | Key Capabilities |
|-------|-------|----------|------------------|
| **deep-debugger** | Opus | Complex bugs, hard to reproduce | Root cause analysis, state tracking |
| **threading-debugger** | Opus | Deadlocks, race conditions | Thread dumps, concurrency bugs |
| **performance-profiler** | Sonnet | Performance issues | CPU/memory profiling, bottlenecks |

### Support Agents

| Agent | Model | Use When | Key Capabilities |
|-------|-------|----------|------------------|
| **venv-keeper** | Sonnet | Environment management | Dependencies, tool configuration |
| **api-documentation-specialist** | Sonnet | API docs | Documentation generation |

### Audit Agents (Read-Only)

| Agent | Purpose |
|-------|---------|
| **agent-consistency-auditor** | Check agent format compliance |
| **coverage-gap-analyzer** | Identify capability gaps |
| **cross-reference-validator** | Validate agent references |
| **review-synthesis-agent** | Synthesize findings from multiple agents |

---

## Decision Guide

### "I need to implement..."
- **Simple feature** → `python-implementation-specialist`
- **Complex async/concurrent** → `python-expert-architect`
- **Qt Model/View** → `qt-modelview-painter`
- **Modern UI** → `qt-ui-modernizer`

### "I need to fix..."
- **Hard-to-reproduce bug** → `deep-debugger`
- **Deadlock/race condition** → `threading-debugger`
- **Performance problems** → `performance-profiler`
- **Code structure issues** → `code-refactoring-expert`

### "I need to review..."
- **Code quality** → `python-code-reviewer`
- **Type safety** → `type-system-expert`
- **UI usability** → `ui-ux-validator`
- **Test coverage** → `test-development-master`

---

## Parallel Execution Rules

### Critical Rule

Agents can ONLY run in parallel if:
1. They work on **different files** (non-overlapping scopes)
2. They perform **read-only analysis** (no modifications)
3. They create **different new files** (no naming conflicts)

### Safe Parallel Combinations

| Agents | Why Safe |
|--------|----------|
| python-code-reviewer + type-system-expert + performance-profiler | All read-only analysis |
| deep-debugger + threading-debugger | Both perform analysis |
| qt-ui-modernizer + qt-modelview-painter | If assigned different files |

### Must Run Sequentially

| Pattern | Reason |
|---------|--------|
| Implementation → Testing | Tests depend on implementation |
| Analysis → Fix → Validation | Each step depends on previous |
| Any two agents modifying same file | Edit conflicts |

### Pre-Deployment Checklist

Before parallel execution:
- [ ] Do agents modify different files? → Safe
- [ ] Both read-only? → Safe
- [ ] Same file modifications? → Sequential only
- [ ] Explicit file scopes defined? → Required for parallel

---

## Common Workflows

### New Feature
```
python-expert-architect → python-implementation-specialist → (review + type-check) → test
```

### Bug Investigation
```
(deep-debugger + threading-debugger) → python-code-reviewer → implementation-specialist → test
```

### Refactoring
```
python-code-reviewer → code-refactoring-expert → (type-check + test)
```

### Qt Development
```
(qt-ui-modernizer + qt-modelview-painter) → qt-concurrency-architect → ui-ux-validator → test
```

### Performance Optimization
```
performance-profiler → python-expert-architect → code-refactoring-expert → (profiler + test)
```

### Code Quality Audit
```
Parallel: python-code-reviewer + type-system-expert + performance-profiler + test-development-master
Then: code-refactoring-expert (fixes) → test-development-master (verify)
```

---

## Model Selection

### Use Opus For
- Architectural decisions
- Complex debugging
- Major refactoring
- UI/UX redesign
- Threading issues

**Limit:** 2-3 parallel Opus agents

### Use Sonnet For
- Code review
- Standard implementation
- Testing
- Type checking
- Validation

**Can run:** 4-5 in parallel

---

## Anti-Patterns

| Don't | Why |
|-------|-----|
| Multiple agents editing same file | Causes conflicts |
| Parallel without explicit file scopes | Leads to overlaps |
| Tests while code is being modified | Inconsistent results |
| venv-keeper with other agents | Environment conflicts |
| Refactoring without review first | May break working code |
| python-expert-architect for simple tasks | Overkill |

---

## Notes

- Agents cannot delegate to other agents - only the main Claude orchestrates
- Always prefer the simplest agent that can accomplish the task
- Combine agent outputs for comprehensive solutions
- See individual agent YAML files in `.claude/agents/` for detailed capabilities

---

*Last updated: December 2025*
