# Test Health Monitoring and Verification Scripts

This directory contains a comprehensive suite of tools for monitoring, analyzing, and verifying improvements to the SpritePal test suite.

## Overview

With 2113+ tests and initially ~70-80% pass rate, these tools help you:
- **Monitor** test health and identify issues systematically
- **Verify** that fixes are working without introducing regressions
- **Track** progress toward the goal of 95%+ pass rate
- **Optimize** test execution for 60% faster runs

## Tools

### 1. Test Health Dashboard (`test_health_dashboard.py`)
**Purpose:** Comprehensive health monitoring and failure categorization

```bash
# Get complete health report
python test_health_dashboard.py --run-tests --report --save

# Quick smoke test check  
python test_health_dashboard.py --quick-check

# Historical trend analysis
python test_health_dashboard.py --historical --compare last-week
```

**Features:**
- Categorizes failures by root cause (type annotations, timeouts, imports, etc.)
- Identifies quick wins and high-impact fixes
- Tracks performance metrics and trends
- Generates actionable fix recommendations

### 2. Progressive Test Runner (`progressive_test_runner.py`)
**Purpose:** Efficient staged testing to quickly isolate issues

```bash
# Run full progressive suite
python progressive_test_runner.py

# Run specific stage only
python progressive_test_runner.py --stage infrastructure

# Continue even with high failure rates
python progressive_test_runner.py --continue-on-failure

# List all available stages
python progressive_test_runner.py --list-stages
```

**Stages:**
1. **infrastructure** - Core imports and basic functionality (CRITICAL)
2. **unit_core** - Essential business logic managers (CRITICAL) 
3. **hal_compression** - HAL compression functionality
4. **workers_basic** - Worker thread infrastructure
5. **extraction_core** - Sprite extraction algorithms
6. **injection_core** - Sprite injection algorithms
7. **ui_basic** - Basic UI components
8. **integration_light** - Lightweight integration tests
9. **gui_dialogs** - Dialog GUI components
10. **integration_heavy** - Complex integration scenarios
11. **performance** - Performance and benchmarking tests
12. **full_remaining** - All remaining tests

### 3. Regression Detector (`regression_detector.py`)
**Purpose:** Compare test results before/after fixes to detect improvements and regressions

```bash
# Create baseline before making changes
python regression_detector.py --baseline --tag "before_type_fixes" --description "Before type annotation fixes"

# Compare two specific results
python regression_detector.py --compare before.json after.json

# Auto-compare recent results
python regression_detector.py --auto-compare --days 7
```

**Features:**
- Detects improvements and regressions in test results
- Analyzes performance impact of changes
- Identifies risk factors and provides recommendations
- Tracks category-specific changes

### 4. Fix Verification Orchestrator (`fix_verification_orchestrator.py`)
**Purpose:** Complete fix verification workflow management

```bash
# Start verification session for type annotation fixes
python fix_verification_orchestrator.py --start-verification type_annotation --description "Fixing type hints across test suite"

# Check progress of active session
python fix_verification_orchestrator.py --check-progress type_annotation_20250808_143000

# Finalize and generate comprehensive report
python fix_verification_orchestrator.py --finalize-verification type_annotation_20250808_143000

# Run complete analysis with all tools
python fix_verification_orchestrator.py --full-analysis

# List all verification sessions
python fix_verification_orchestrator.py --list-sessions
```

## Workflow Examples

### Starting a New Fix Campaign

1. **Create Baseline**
   ```bash
   python fix_verification_orchestrator.py --start-verification "type_annotation" --description "Comprehensive type annotation fixes"
   ```

2. **Make Your Fixes**
   - Work on type annotations, timeouts, HAL mocking, etc.
   - Make incremental changes

3. **Check Progress Regularly**
   ```bash
   # Quick check with progressive testing
   python progressive_test_runner.py --stage infrastructure
   
   # Full progress check with checkpoint
   python fix_verification_orchestrator.py --check-progress your_session_id
   ```

4. **Finalize When Done**
   ```bash
   python fix_verification_orchestrator.py --finalize-verification your_session_id
   ```

### Quick Health Check

```bash
# Fast assessment of current state
python test_health_dashboard.py --quick-check

# Or run progressive stages
python progressive_test_runner.py --max-stage integration_light
```

### Investigating Specific Issues

```bash
# Focus on type annotation issues
python progressive_test_runner.py --stage unit_core

# Check if HAL compression is working
python progressive_test_runner.py --stage hal_compression

# Test GUI components
python progressive_test_runner.py --stage gui_dialogs
```

## Understanding Results

### Pass Rate Health Indicators
- **🟢 95%+** - Excellent (production ready)
- **🟡 85-94%** - Good (minor issues)
- **🟠 70-84%** - Needs improvement
- **🔴 <70%** - Critical issues

### Common Failure Categories
- **type_annotation** - Missing or incorrect type hints
- **timeout** - Tests exceeding time limits (potential deadlocks)
- **import_error** - Broken imports (critical - fix first)
- **qt_related** - Qt/GUI framework issues
- **mock_related** - Mock configuration problems
- **hal_compression** - HAL binary subprocess issues
- **threading** - Thread safety and concurrency bugs
- **logic_bugs** - Actual business logic errors

### Performance Targets
- **Average per test:** <2s (currently varies by complexity)
- **Total suite:** <30 minutes for full run
- **Progressive stages:** <10 minutes to critical issues

## File Structure

```
tests/scripts/
├── README.md                           # This file
├── test_health_dashboard.py           # Health monitoring and metrics
├── progressive_test_runner.py         # Staged testing strategy  
├── regression_detector.py             # Before/after comparison
├── fix_verification_orchestrator.py   # Complete workflow management
├── history/                           # Historical test data
│   ├── test_health_*.json            # Health snapshots
│   ├── baseline_*.json               # Fix baselines
│   └── regression_report_*.json      # Regression analyses
└── sessions/                          # Verification sessions
    └── *.json                        # Session data and progress
```

## Integration with Development Workflow

### Before Making Changes
1. Run health dashboard to understand current state
2. Start verification session for your fix category
3. Note baseline metrics and problem areas

### During Development
1. Use progressive runner for quick feedback
2. Check progress periodically to catch regressions early
3. Focus on categories showing improvement

### After Changes
1. Finalize verification session
2. Review regression report for unexpected issues
3. Address any new failures before proceeding

### Continuous Monitoring
1. Set up regular health checks
2. Track trends over time
3. Maintain history of improvements

## Tips for Success

### Quick Wins Priority
1. **Import errors** - Fix these first (blocks other tests)
2. **Type annotations** - Many can be fixed quickly
3. **Simple mock issues** - Often just configuration problems

### High Impact Areas
1. **Infrastructure tests** - Affects everything else
2. **Core manager tests** - Central business logic
3. **Most affected files** - Check dashboard for top problem files

### Performance Optimization
1. Use progressive runner to avoid running slow tests repeatedly
2. Focus on timeout issues that indicate real problems
3. Profile before optimizing - measure impact

### Risk Management
1. Always create baselines before major changes
2. Watch for regressions in working areas
3. Test critical functionality manually after major changes
4. Keep change sets focused on single categories

## Troubleshooting

### Common Issues

**"No tests collected"**
- Make sure you're in the correct directory
- Check that pytest can find tests/ directory
- Verify virtual environment is activated

**"Permission denied" or "File not found"**
- Ensure scripts are executable: `chmod +x *.py`
- Check file paths are correct (scripts expect to be in tests/scripts/)

**"Module not found" errors**
- Activate virtual environment: `source venv/bin/activate`
- Install missing dependencies: `pip install pytest pytest-qt`

**Tests hang or timeout**
- This is expected for some GUI tests
- Use progressive runner to skip problematic tests
- Check for actual deadlocks vs. expected slow tests

### Getting Help

1. **Check logs** - Tools provide detailed output about what they're doing
2. **Use --help** - All scripts have detailed help information
3. **Start small** - Use progressive runner to isolate issues
4. **Check history** - Look at previous successful runs for comparison

## Target Metrics

By the end of the fix campaign, we should achieve:
- **Pass Rate:** 95%+ (from ~70-80%)
- **Execution Time:** <30 minutes full suite (60% improvement)
- **Stability:** <5% variance between runs
- **Categories:** Zero critical failures (import_error, infrastructure)

These tools provide the visibility and verification needed to reach these goals systematically.