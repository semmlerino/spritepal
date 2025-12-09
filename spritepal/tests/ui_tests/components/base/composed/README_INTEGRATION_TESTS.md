# ComposedDialog Integration Tests - Real Component Testing

This document describes the comprehensive integration tests for the ComposedDialog architecture using **real Qt components** with minimal mocking.

## Key Features

### ✅ Real Component Testing
- Uses actual Qt widgets and components
- Tests real widget properties and behavior
- Validates actual UI state changes
- Minimal mocking (only for blocking operations)

### ✅ Enhanced TestDialog Implementation
The `TestDialog` class provides a realistic test environment with:

- **Form validation** with name input and validation button
- **Progress simulation** with progress bar and status updates
- **Real UI elements**: QLabel, QLineEdit, QPushButton, QProgressBar
- **Component integration** that demonstrates real-world usage patterns

### ✅ Proper Signal Testing
Replaced `QSignalSpy` (not available in PySide6) with manual signal collection:

```python
# Instead of QSignalSpy
signal_args: List[tuple] = []
message_manager.message_shown.connect(lambda msg_type, msg: signal_args.append((msg_type, msg)))

# Trigger action
message_manager.show_info("Title", "Message")
QApplication.processEvents()

# Verify results
assert len(signal_args) == 1
assert signal_args[0] == ("info", "Message")
```

### ✅ Strategic Mocking
Only mocks **blocking operations** that would interfere with tests:

```python
@patch('PySide6.QtWidgets.QMessageBox.information')
@patch('PySide6.QtWidgets.QMessageBox.critical')
@patch('PySide6.QtWidgets.QMessageBox.warning')
@patch('PySide6.QtWidgets.QMessageBox.question')
```

All other components use **real Qt widgets**.

## Test Coverage

### Core Architecture Tests
1. **Basic dialog creation** with default configuration
2. **Component configuration** (with/without button box, status bar)
3. **Component retrieval** via `get_component()`
4. **Cleanup validation** on dialog close

### Real Component Integration Tests
1. **MessageDialogManager** - Tests all message types with real signal emission
2. **ButtonBoxManager** - Tests real button clicks with Qt events
3. **StatusBarManager** - Tests real status bar state and messages
4. **Custom buttons** - Tests custom button creation and callbacks

### Enhanced Realistic Scenarios
1. **Form validation workflow** - Tests real form elements and state management
2. **Progress and status integration** - Tests progress bar visibility and status updates
3. **Component state consistency** - Validates component references and lifecycle
4. **Widget properties and behavior** - Tests actual Qt widget properties

### Complex Integration Workflows
1. **Multi-component workflows** - Tests components working together
2. **Real UI interaction** - Tests actual mouse clicks and form input
3. **State management** - Tests enable/disable states based on validation

## Usage Examples

### Creating a Real Integration Test

```python
def test_realistic_component_behavior(self, qtbot: Any) -> None:
    """Test real component behavior with minimal mocking."""
    dialog = TestDialog(with_status_bar=True)
    qtbot.addWidget(dialog)
    
    # Test real widget creation
    assert isinstance(dialog.name_input, QLineEdit)
    assert dialog.name_input.placeholderText() == "Enter name..."
    
    # Test real user interaction
    dialog.name_input.setText("test")
    QTest.mouseClick(dialog.validate_button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    
    # Verify real widget state changes
    assert dialog.form_valid
    assert "Valid name: test" in dialog.result_label.text()
    
    # Test real component integration
    status_manager = dialog.get_component("status_bar")
    status_bar = status_manager.status_bar
    dialog.simulate_progress(50)
    assert status_bar.currentMessage() == "Processing... 50%"
```

### Signal Testing Pattern

```python
def test_real_signal_emission(self, qtbot: Any) -> None:
    """Test real signal emission with manual collection."""
    dialog = TestDialog()
    qtbot.addWidget(dialog)
    
    button_manager = dialog.get_component("button_box")
    
    # Set up signal collection (replaces QSignalSpy)
    clicked_buttons: List[str] = []
    button_manager.button_clicked.connect(lambda btn: clicked_buttons.append(btn))
    
    # Add and click real button
    custom_button = button_manager.add_button("Test Button")
    QTest.mouseClick(custom_button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    
    # Verify signal was emitted
    assert len(clicked_buttons) == 1
    assert clicked_buttons[0] == "Test Button"
```

## Benefits of This Approach

### 1. **Real Behavior Testing**
- Tests actual Qt widget behavior, not mocked approximations
- Catches real Qt-specific issues (layout, styling, events)
- Validates actual user interaction patterns

### 2. **Minimal Test Maintenance**
- Less mocking means fewer mock configurations to maintain
- Real components self-validate their behavior
- Tests closer to production code paths

### 3. **Better Bug Detection**
- Catches real Qt timing issues with `QApplication.processEvents()`
- Validates actual widget states and properties
- Tests real signal/slot connections

### 4. **Realistic Test Environment**
- TestDialog represents a real-world dialog implementation
- Form validation and progress tracking mirror actual use cases
- Component interactions test the actual architecture

## Running the Tests

```bash
# Run all integration tests
pytest tests/ui/components/base/composed/test_composed_dialog_integration.py -v

# Run specific test with output
pytest tests/ui/components/base/composed/test_composed_dialog_integration.py::TestComposedDialogIntegration::test_realistic_form_validation_workflow -xvs

# Run with Qt markers
pytest -m "qt_real and integration" tests/ui/components/base/composed/
```

## Key Improvements Made

1. **Removed QSignalSpy dependency** - Replaced with manual signal collection
2. **Enhanced TestDialog** - Added realistic UI elements and behaviors
3. **Real widget testing** - Tests actual Qt widget properties and states
4. **Strategic mocking** - Only mocks blocking QMessageBox operations
5. **Comprehensive scenarios** - Added form validation, progress tracking, and complex workflows
6. **Proper cleanup** - Tests component cleanup and resource management

This integration test suite validates that the ComposedDialog architecture works correctly with real Qt components, providing confidence that the composition pattern delivers the expected functionality in a real application environment.