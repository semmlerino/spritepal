from PySide6.QtCore import QObject, Signal


class Emitter(QObject):
    my_signal = Signal(str)


class Receiver(QObject):
    def my_slot(self, s):
        pass


e = Emitter()
r = Receiver()

print(f"Initial receivers: {e.receivers(e.my_signal)}")  # noqa: T201

e.my_signal.connect(r.my_slot)
print(f"Receivers after connect: {e.receivers(e.my_signal)}")  # noqa: T201

e.my_signal.disconnect(r.my_slot)
print(f"Receivers after disconnect: {e.receivers(e.my_signal)}")  # noqa: T201
