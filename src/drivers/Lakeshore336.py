import asyncio
from lakeshore import Model336
from src.drivers.sensor_base import SensorBase


class TemperatureSensor(SensorBase):  # First 3 lines "standard"
    def __init__(self, name="336_temp", channel="A"):
        super().__init__(name)
        self.channel = channel
        self.instrument = Model336()

    async def read(self):
        return await asyncio.to_thread(  # run a thread (separate program) so we don't get blocking
            self.instrument.get_kelvin_reading,  # function
            self.channel  # argument
        )


    # If close is sought: self.instrument.disconnect_usb()