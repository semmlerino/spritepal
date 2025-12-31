# Development Scripts

This directory contains utility scripts for SpritePal development.

## Type Checking Scripts

### show_critical_errors.py
Quick script to show only the most critical basedpyright errors.

```bash
# Run from spritepal directory
python scripts/show_critical_errors.py
```

Shows:
- General type issues
- Missing type arguments
- Import cycles
- Argument/assignment type errors

### typecheck_analysis.py
Comprehensive type checking analysis tool with many options.

```bash
# Show full analysis
python scripts/typecheck_analysis.py

# Show only critical errors
python scripts/typecheck_analysis.py --critical

# Check specific files
python scripts/typecheck_analysis.py core/controller.py ui/main_window.py

# Save report to file
python scripts/typecheck_analysis.py --save

# Limit number of errors shown
python scripts/typecheck_analysis.py --limit 10
```

Features:
- Groups errors by type
- Shows files with most errors
- Prioritizes critical issues
- Can save JSON reports
- Tracks progress over time

## Usage

All scripts should be run from the `spritepal` directory with the virtual environment activated:

```bash
cd /path/to/exhal-master/spritepal
source ../venv/bin/activate
python scripts/[script_name].py
```