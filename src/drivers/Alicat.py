import asyncio
from src.drivers.sensor_base import SensorBase
from alicat import FlowController


class Alicat(SensorBase):
    """Sync wrapper over alicat's async FlowController.
    """

    def __init__(self, name="alicat"):
        super().__init__(name)
        self.flowcontroller = None
        self.connected = False
        self.poll_hz = 40
        self._loop = None

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    async def _setup(self):
        fc = FlowController()
        # The library kicks off a connect coroutine in its __init__; wait for
        # it to actually finish before we start querying.
        connect_task = getattr(fc, "connectTask", None)
        if connect_task is not None:
            await connect_task
        # Prime with a read so we fail loudly here if the device isn't reachable.
        await fc.get()
        return fc

    def connect(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.flowcontroller = self._run(self._setup())
        self.connected = True

    def read(self):
        if not self.connected:
            raise RuntimeError("Alicat not connected")
        return self._run(self.flowcontroller.get())

    def close(self):
        if self._loop and not self._loop.is_closed():
            try:
                close_coro = getattr(self.flowcontroller, "close", None)
                if asyncio.iscoroutinefunction(close_coro):
                    self._run(close_coro())
            except Exception:
                pass
            self._loop.close()
