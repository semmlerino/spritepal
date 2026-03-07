# Agent Orchestration Commands - Quick Reference

## Phase 1: Fix Critical Issues

### Parallel Batch 1 (Can run simultaneously)
```bash
# Task 1: Fix dynamic class creation
Agent: python-implementation-specialist
Prompt: "Replace the unsafe dynamic class creation using type() in ui/dialogs/manual_offset/manual_offset_dialog_adapter.py with a proper factory pattern or __new__ method that maintains type safety while supporting runtime selection between implementations."

# Task 2: Add type annotations
Agent: type-system-expert
Prompt: "Add comprehensive type annotations to all files in ui/dialogs/manual_offset/, focusing on: ComponentFactory methods, Signal declarations with proper types, component interfaces as protocols, and all method return types. Use TYPE_CHECKING imports to avoid circular dependencies."
```

### Parallel Batch 2 (After Batch 1)
```bash
# Task 3: Implement thread safety
Agent: qt-concurrency-architect
Prompt: "Review and fix thread safety issues in ui/dialogs/manual_offset/components/, ensuring all shared state access uses QMutexLocker consistently, component initialization/cleanup is thread-safe, and signal disconnection handles Qt threading properly."

# Task 4: Fix error handling
Agent: python-code-reviewer
Prompt: "Replace all bare except clauses in ui/dialogs/manual_offset/ with specific exception handling. Focus on signal disconnection (RuntimeError, TypeError), file operations (IOError, OSError), and Qt operations (RuntimeError). Add appropriate logging for each exception type."
```

## Phase 2: Dialog Migration

### Analysis Tasks (Parallel)
```bash
# Analyze all 4 dialogs simultaneously
Agent: python-code-reviewer (4 parallel instances)

Prompts:
1. "Analyze ui/dialogs/advanced_search_dialog.py and create a component breakdown showing how to split it into single-responsibility components for the composition pattern migration."

2. "Analyze ui/dialogs/similarity_results_dialog.py and create a component breakdown showing how to split it into single-responsibility components for the composition pattern migration."

3. "Analyze ui/grid_arrangement_dialog.py and create a component breakdown showing how to split it into single-responsibility components for the composition pattern migration."

4. "Analyze ui/row_arrangement_dialog.py and create a component breakdown showing how to split it into single-responsibility components for the composition pattern migration."
```

### Implementation Tasks (Parallel)
```bash
# Implement all 4 migrations simultaneously
Agent: python-implementation-specialist (3 instances) + qt-modelview-painter (1 instance)

Prompts:
1. "Migrate advanced_search_dialog to composition pattern with SearchEngineComponent, ResultsViewComponent, and FilterManagerComponent. Use the UnifiedManualOffsetDialog migration as a template."

2. "Migrate similarity_results_dialog to composition pattern with SimilarityEngineComponent and ResultsDisplayComponent. Maintain API compatibility with feature flag support."

3. [qt-modelview-painter] "Migrate grid_arrangement_dialog to composition pattern with GridManagerComponent, PreviewComponent (handle custom painting), and ArrangementControlsComponent. Pay special attention to QPainter operations."

4. "Migrate row_arrangement_dialog to composition pattern with RowManagerComponent and ArrangementUIComponent. Ensure backward compatibility."
```

### Testing Task
```bash
Agent: test-development-master
Prompt: "Create comprehensive test suites for the 4 newly migrated dialogs (advanced_search, similarity_results, grid_arrangement, row_arrangement). Test both legacy and composed implementations via feature flag, verify API compatibility, and check signal/slot connections."
```

## Phase 3: Validation

### Parallel Validation Tasks
```bash
# Task 1: Performance profiling
Agent: performance-profiler
Prompt: "Benchmark the dialog migration comparing legacy vs composed implementations. Measure dialog creation time, memory usage, signal propagation latency, component initialization overhead, and cleanup efficiency. Flag any regression over 5%."

# Task 2: Memory leak detection
Agent: deep-debugger  
Prompt: "Test for memory leaks in the migrated dialogs by running 1000 create/destroy cycles. Monitor QObject parent-child relationships, signal disconnection, worker thread cleanup, and cache cleanup. Use weak references to track object lifecycle."

# Task 3: Type safety validation
Agent: type-system-expert
Prompt: "Run comprehensive type checking on all migrated dialogs using basedpyright --strict. Fix any type errors, add missing annotations, and ensure protocol conformance for all component interfaces."
```

## Phase 4: Final Review

### Parallel Review Tasks
```bash
# Run all reviews simultaneously
Agent: python-code-reviewer
Prompt: "Perform final code quality review of all migrated dialogs, checking for code duplication, consistent patterns, proper error handling, and adherence to PySide6 best practices."

Agent: qt-concurrency-architect
Prompt: "Audit thread safety across all migrated dialogs, verifying mutex usage, signal thread affinity, worker cleanup, and absence of race conditions."

Agent: api-documentation-specialist
Prompt: "Generate comprehensive API documentation for the new composition-based dialog system, including migration guide, component patterns, and code examples."

Agent: review-synthesis-agent
Prompt: "Synthesize findings from all review agents into a prioritized action plan with specific recommendations for production deployment."
```

## Useful Test Commands

```bash
# Quick validation of a single dialog
SPRITEPAL_USE_COMPOSED_DIALOGS=true python -c "from ui.dialogs import AdvancedSearchDialog; d = AdvancedSearchDialog(); print('✓')"

# Run specific dialog tests
pytest tests/test_advanced_search_dialog_migration.py -v

# Check type safety
python -m pyright ui/dialogs/ --strict

# Memory leak test
python -c "
import gc
from ui.dialogs import UnifiedManualOffsetDialog
for i in range(100):
    d = UnifiedManualOffsetDialog()
    d.cleanup()
    del d
    if i % 10 == 0:
        gc.collect()
        print(f'Cycle {i}: {len(gc.get_objects())} objects')
"

# Performance comparison
python scripts/benchmark_dialogs.py --legacy --composed --compare
```

## Agent Coordination Rules

1. **Never run code-modifying agents on the same file simultaneously**
2. **Always run type-system-expert after python-implementation-specialist**
3. **Run test-development-master after implementation is complete**
4. **Use review-synthesis-agent to consolidate findings from multiple review agents**
5. **Run performance-profiler before and after optimizations**

## Emergency Rollback

If critical issues arise:
```bash
# Immediately revert to legacy implementation
export SPRITEPAL_USE_COMPOSED_DIALOGS=false

# Test legacy implementation
pytest tests/ -k dialog -v

# Check for regressions
git diff HEAD~1 ui/dialogs/
```

## Success Checklist

- [ ] Phase 1: All critical issues fixed
- [ ] Phase 2: All 4 dialogs migrated  
- [ ] Phase 3: Performance validated, no memory leaks
- [ ] Phase 4: All reviews passed
- [ ] Feature flags working for all dialogs
- [ ] Documentation complete
- [ ] Team sign-off obtained

This orchestration guide provides the exact commands and prompts needed to complete the dialog migration efficiently using parallel agent execution.