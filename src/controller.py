import asyncio
import logging

from drivers.Lakeshore218 import SerialTemperatureSensor
from drivers.Lakeshore336 import TemperatureSensor
from drivers.Alicat import Alicat


# with these approaches, the same code can be run for every cryostat without adjustment
class SensorController:
    def __init__(self, sample_hz=1):
        self.sample_hz = sample_hz
        self.period = 1 / sample_hz  # our current "limitation"
        self.sensors = []
        self._init_sensors()

    def _init_sensors(self):
        sensors_specifications = [
            ("Lakeshore336", lambda: TemperatureSensor(name="temp_A", channel="A")),  # Generic or specific?
            ("Lakeshore218", lambda: SerialTemperatureSensor()), # remove the first name, its not used again
        ]

        for sensor_name, sensor_init in sensors_specifications:
            try:
                sensor = sensor_init()
                self.sensors.append(sensor)
                logging.info(f"{sensor_name} initialized")
            except Exception as e:
                logging.error(f"{sensor_name} failed to initialize: {e}")

    async def read_one(self, sensor):
        try:
            value = await sensor.read()
            return sensor.name, value
        except Exception as e:
            logging.error(f"{sensor.name} read failed: {e}")
            return sensor.name, None

    async def read_all(self):
        results = await asyncio.gather(
            *(self.read_one(sensor) for sensor in self.sensors)
        )
        return dict(results)

    async def run(self):
        while True:
            readings = await self.read_all()
            print(readings)
            await asyncio.sleep(self.period)
