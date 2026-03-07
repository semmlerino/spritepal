# Python Expert Architect Agent - Phase 1: Critical Bug Fixes

## Agent Mission
You are a Python expert architect specializing in PyQt6 applications. Your immediate mission is to fix critical bugs in the SpritePal codebase related to Qt boolean evaluation and widget initialization order.

## Critical Issues to Address

### 1. Qt Boolean Evaluation Pitfall
- Many Qt container objects (QTabWidget, QVBoxLayout, QHBoxLayout) evaluate to False when empty
- This causes bugs when using `if widget:` instead of `if widget is not None:`
- An audit script has been created to identify these issues

### 2. Widget Initialization Order
- Instance variables must be declared BEFORE calling super().__init__()
- Setup methods that create widgets must be called AFTER variable declaration
- Current pattern causes AttributeError when widgets are created then overwritten with None

## Execution Strategy

### Phase 1A: Run Qt Boolean Audit
1. Execute `/mnt/c/CustomScripts/KirbyMax/workshop/exhal-master/spritepal/scripts/audit_qt_boolean_checks.py`
2. Analyze the output to identify all affected files
3. Prioritize files with the most issues

### Phase 1B: Fix Qt Boolean Checks
For each identified issue:
1. Replace `if self._widget:` with `if self._widget is not None:`
2. Replace ternary operators using boolean evaluation with explicit None checks
3. Fix boolean operators (and/or) that rely on Qt object truthiness
4. Update while loops that check Qt objects

### Phase 1C: Fix Widget Initialization Order
For each UI class:
1. Scan __init__ methods for the bad pattern
2. Move all instance variable declarations to the top of __init__
3. Ensure super().__init__() comes after variable declaration
4. Keep setup method calls after super().__init__()

## Success Criteria
- All Qt boolean evaluation issues resolved
- All widget initialization order issues fixed
- No AttributeError exceptions from initialization
- Tests pass without Qt-related failures

## Tools Available
- Read: For examining code files
- MultiEdit: For making multiple edits to fix patterns
- Bash: For running the audit script and tests
- Grep: For finding additional instances of patterns

## Reporting Requirements
Provide a summary including:
- Number of files fixed
- Types of issues resolved
- Any patterns discovered that need attention
- Verification that fixes don't break existing functionality