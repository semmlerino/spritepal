import pytest
from PySide6.QtCore import QObject, Signal

from ui.common.signal_utils import safe_disconnect


class MockController(QObject):
    changed = Signal()


class MockWorkspace(QObject):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.received = 0

    def on_changed(self):
        self.received += 1


def test_safe_disconnect_behavior():
    controller = MockController()
    ws1 = MockWorkspace("ws1")
    ws2 = MockWorkspace("ws2")

    controller.changed.connect(ws1.on_changed)
    controller.changed.connect(ws2.on_changed)

    controller.changed.emit()
    assert ws1.received == 1
    assert ws2.received == 1

    # safe_disconnect calls signal.disconnect()
    safe_disconnect(controller.changed)

    controller.changed.emit()
    assert ws1.received == 1, "WS1 should not have received signal after disconnect"
    assert ws2.received == 1, "WS2 was also disconnected by safe_disconnect!"
