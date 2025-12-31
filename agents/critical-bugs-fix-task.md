# Critical Bug Fix Task - Immediate Action Required

## Task Overview
Fix two critical bugs in the SpritePal codebase that pose immediate risks to application stability.

## Bug 1: Overly Broad Exception Handling
**File**: `ui/common/collapsible_group_box.py` lines 180-184
**Current Issue**: Catching RuntimeError too broadly could hide actual bugs

### Required Fix:
```python
# Current problematic code:
try:
    connection()
except (RuntimeError, TypeError):
    # Connection might already be disconnected or object deleted
    pass

# Should be replaced with:
try:
    connection()
except RuntimeError as e:
    # Only ignore the specific Qt object deletion error
    if "wrapped C/C++ object has been deleted" not in str(e):
        raise
except TypeError:
    # Connection might have incompatible signature
    pass
```

### Verification:
- Check if Qt signals/slots still disconnect properly
- Ensure real RuntimeErrors are not suppressed

## Bug 2: Thread Safety in Singleton Pattern
**File**: `ui/common/error_handler.py` lines 91-100
**Current Issue**: Singleton creation is not thread-safe

### Required Fix:
Add proper thread synchronization:

```python
import threading

# Add at module level after imports
_error_handler_lock = threading.Lock()

# Update get_error_handler function:
def get_error_handler(parent: QWidget | None = None) -> ErrorHandler:
    """Get or create the global error handler instance (thread-safe)"""
    global _error_handler
    
    # Fast path - check without lock
    if _error_handler is not None:
        if parent is not None and _error_handler._parent_widget is None:
            with _error_handler_lock:
                if _error_handler._parent_widget is None:
                    _error_handler._parent_widget = parent
                    _error_handler.setParent(parent)
        return _error_handler
    
    # Slow path - create with lock
    with _error_handler_lock:
        # Double-check pattern
        if _error_handler is None:
            _error_handler = ErrorHandler(parent)
        return _error_handler
```

### Verification:
- Test concurrent access doesn't create multiple instances
- Verify parent widget updates are thread-safe

## Additional Audit Task
Run the Qt boolean audit to catch any other issues:
```bash
python scripts/audit_qt_boolean_checks.py
```

## Success Criteria
1. Exception handling is specific and doesn't hide bugs
2. Singleton pattern is thread-safe
3. All tests pass
4. No new issues introduced

## Priority: CRITICAL - Fix immediately before any other work