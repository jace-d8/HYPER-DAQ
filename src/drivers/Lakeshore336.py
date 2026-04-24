import asyncio
from lakeshore import Model336
from src.drivers.sensor_base import SensorBase

class TemperatureSensor(SensorBase):
    def __init__(self, name="336_1", channels=None):
        super().__init__(name)

        if not channels:
            raise ValueError("TemperatureSensor requires a non-empty channels dict")

        self.channels = channels
        self.instrument = Model336()

    async def read(self):
        readings = {}

        for sensor_name, channel in self.channels.items():
            value = await asyncio.to_thread(
                self.instrument.get_kelvin_reading,
                channel
            )
            readings[sensor_name] = value

        return readings