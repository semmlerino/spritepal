# Dialog Development Guide

## Why This Guide Exists

We encountered a critical bug where the ManualOffsetDialog singleton was being deleted when its parent was destroyed, causing "wrapped C/C++ object has been deleted" errors. This guide helps prevent similar issues.

## Key Lessons Learned

1. **Qt Parent-Child Lifecycle**: When a parent widget is deleted, ALL its children are deleted, regardless of any attributes
2. **Singleton Pattern Incompatibility**: Singleton dialogs cannot have parents that might be deleted
3. **WA_DeleteOnClose Default**: BaseDialog sets this to True, which deletes dialogs on close
4. **Testing Gaps**: Heavy mocking in tests missed real Qt lifecycle issues

## Dialog Design Patterns

### 1. One-Time Dialogs (Default)
```python
class SimpleDialog(BaseDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent=parent, title="Simple Dialog")
        # WA_DeleteOnClose=True (default) - dialog deleted on close
        # Good for: file dialogs, message boxes, one-time forms
```

### 2. Singleton Dialogs (Special Requirements)
```python
class SingletonDialog(BaseDialog):
    _instance: ClassVar["SingletonDialog | None"] = None
    
    @classmethod
    def get_instance(cls, parent: QWidget | None = None) -> "SingletonDialog":
        """Get or create singleton instance
        
        Note: Parent parameter is ignored - singletons must be parentless
        """
        if cls._instance is None:
            cls._instance = cls(parent=None)  # ALWAYS None
        return cls._instance
    
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=None, title="Singleton Dialog")  # ALWAYS None
        
        # REQUIRED: Disable delete on close
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        
        # REQUIRED: Set proper modality for parentless dialog
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
    
    def closeEvent(self, event: QCloseEvent):
        """Hide instead of close to preserve singleton"""
        event.ignore()
        self.hide()
```

### 3. Reusable Non-Singleton Dialogs
```python
class ReusableDialog(BaseDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent=parent, title="Reusable Dialog")
        
        # Disable delete on close for reuse
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
    
    def closeEvent(self, event: QCloseEvent):
        """Hide for reuse"""
        event.ignore()
        self.hide()
```

## Testing Requirements

### 1. Lifecycle Tests (REQUIRED for all dialogs)
```python
@pytest.mark.gui
def test_dialog_lifecycle(qtbot):
    """Test dialog can be opened, closed, and reopened"""
    dialog = MyDialog()
    qtbot.addWidget(dialog)
    
    # Open
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    
    # Close
    dialog.close()
    qtbot.waitUntil(lambda: not dialog.isVisible())
    
    # Reopen (should not crash)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    
    # Access widgets (should not raise "deleted C++ object")
    assert dialog.some_widget is not None
```

### 2. Parent Deletion Tests (for non-singleton dialogs)
```python
@pytest.mark.gui
def test_dialog_parent_deletion(qtbot):
    """Test dialog handles parent deletion gracefully"""
    parent = QWidget()
    qtbot.addWidget(parent)
    
    dialog = MyDialog(parent)
    qtbot.addWidget(dialog)
    
    # Delete parent
    parent.deleteLater()
    QTest.qWait(100)
    
    # Dialog should be deleted too (for non-singletons)
    # Test should not crash
```

### 3. Real Widget Tests (avoid excessive mocking)
```python
# BAD: Too much mocking misses Qt behavior
with patch("MyDialog") as mock_dialog:
    mock_dialog.return_value.exec.return_value = 1

# GOOD: Test real Qt behavior
dialog = MyDialog()
qtbot.addWidget(dialog)
dialog.show()
# Test actual behavior
```

## Common Pitfalls to Avoid

1. **Creating singleton dialogs with parents**
   ```python
   # WRONG
   dialog = SingletonDialog.get_instance(self.main_window)
   
   # RIGHT - parent ignored for safety
   dialog = SingletonDialog.get_instance()
   ```

2. **Not testing dialog reopen scenarios**
   ```python
   # INCOMPLETE TEST
   dialog.show()
   dialog.close()
   
   # COMPLETE TEST
   dialog.show()
   dialog.close()
   dialog.show()  # Test reopen!
   ```

3. **Assuming WA_DeleteOnClose is False**
   ```python
   # WRONG - BaseDialog sets it to True
   class MyDialog(BaseDialog):
       pass
   
   # RIGHT - Explicitly set for singletons/reusables
   class MyDialog(BaseDialog):
       def __init__(self):
           super().__init__()
           self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
   ```

## Checklist for New Dialogs

- [ ] Decide lifecycle: one-time, singleton, or reusable
- [ ] For singletons: create with parent=None
- [ ] For singletons/reusables: set WA_DeleteOnClose=False
- [ ] For singletons: override closeEvent to hide instead of close
- [ ] For parentless dialogs: set appropriate window modality
- [ ] Write lifecycle tests (open/close/reopen)
- [ ] Write parent deletion tests (if applicable)
- [ ] Test with real widgets, not just mocks
- [ ] Document the dialog's lifecycle pattern

## Red Flags in Code Review

1. Singleton with parent parameter used
2. No WA_DeleteOnClose handling for reusable dialogs
3. No closeEvent override for singletons
4. Only mock-based tests
5. No reopen scenario tests
6. get_instance() that uses the parent parameter

## Example: Fixing a Broken Singleton

```python
# BEFORE (broken)
class BrokenSingleton(BaseDialog):
    _instance = None
    
    @classmethod
    def get_instance(cls, parent):
        if cls._instance is None:
            cls._instance = cls(parent)  # BUG: Parent can be deleted!
        return cls._instance
    
    def __init__(self, parent):
        super().__init__(parent)  # BUG: Has parent
        # BUG: WA_DeleteOnClose=True (default)

# AFTER (fixed)
class FixedSingleton(BaseDialog):
    _instance = None
    
    @classmethod
    def get_instance(cls, parent=None):
        if cls._instance is None:
            cls._instance = cls()  # No parent
        return cls._instance
    
    def __init__(self):
        super().__init__(parent=None)  # Parentless
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
    
    def closeEvent(self, event):
        event.ignore()
        self.hide()
```

## Summary

The key insight is that Qt's parent-child lifecycle is strict: when a parent dies, all children die. Singleton dialogs must be parentless to survive. Always test the full lifecycle with real Qt widgets to catch these issues early.

---

*Last updated: December 21, 2025*