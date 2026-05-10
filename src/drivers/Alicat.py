import asyncio
from src.drivers.sensor_base import SensorBase
from alicat import FlowController


class Alicat(SensorBase):
    """Sync wrapper over alicat's async FlowController. Drives a private event
    loop inside the driver so the controller can stay free of asyncio."""

    def __init__(self, name="alicat"):
        super().__init__(name)
        self.flowcontroller = FlowController()
        self.connected = False
        self.poll_hz = 40
        self._loop = None

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def connect(self):
        self._loop = asyncio.new_event_loop()
        self._run(self.flowcontroller.get())
        self.connected = True

    def read(self):
        if not self.connected:
            raise RuntimeError("Alicat not connected")
        return self._run(self.flowcontroller.get())

    def close(self):
        if self._loop and not self._loop.is_closed():
            self._loop.close()
