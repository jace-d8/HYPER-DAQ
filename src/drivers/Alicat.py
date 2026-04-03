from src.drivers.sensor_base import SensorBase
from alicat import FlowController

class Alicat(SensorBase):
    def __init__(self, name="alicat"):
        super().__init__(name)
        self.flowcontroller = FlowController()
        self.connected = False

    async def connect(self):
        await self.flowcontroller.get()
        self.connected = True

    async def read(self):
        if not self.connected:
            raise RuntimeError("Alicat not connected")
        return await self.flowcontroller.get()