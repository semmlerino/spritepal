# Critical Bug Fixes Task for python-expert-architect

## Priority 1 Issues to Fix

### 1. Qt Boolean Evaluation Bug - ALREADY FIXED
**File**: `ui/common/worker_manager.py:44`
**Status**: Already fixed - line 44 correctly uses `if worker is None:`
**Action**: Verify no other Qt boolean issues exist in this file

### 2. BaseException Suppression Issue
**File**: `ui/common/collapsible_group_box.py:180-184`
**Current Code**:
```python
try:
    connection()
except (RuntimeError, TypeError):
    # Connection might already be disconnected or object deleted
    pass
```
**Issue**: Catching RuntimeError is too broad - it can hide actual bugs
**Fix Required**: 
- Replace with more specific Qt exceptions
- Consider using `except RuntimeError as e:` and checking the error message
- Qt typically raises RuntimeError with "wrapped C/C++ object has been deleted" for deleted objects

### 3. Thread Safety Issue
**File**: `ui/common/error_handler.py:91-100`
**Function**: `get_error_handler()`
**Current Code**:
```python
def get_error_handler(parent: QWidget | None = None) -> ErrorHandler:
    """Get or create the global error handler instance"""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler(parent)
    elif parent is not None and _error_handler._parent_widget is None:
        # Update parent if provided and not already set
        _error_handler._parent_widget = parent
        _error_handler.setParent(parent)
    return _error_handler
```
**Issue**: Not thread-safe - multiple threads could create multiple instances
**Fix Required**:
- Add threading.Lock for singleton creation
- Use double-checked locking pattern
- Ensure thread-safe access to _error_handler

## Additional Tasks

1. Run the Qt boolean audit script to find any other Qt boolean evaluation issues:
   ```bash
   python scripts/audit_qt_boolean_checks.py
   ```

2. Search for other instances of broad exception handling that might hide bugs

3. Look for other singleton patterns that might need thread safety

## Verification Steps
1. Run tests to ensure fixes don't break functionality
2. Verify thread safety with concurrent access tests
3. Check that exception handling still works but is more specific