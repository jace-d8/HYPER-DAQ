import asyncio
import logging
from datetime import datetime

from drivers.Lakeshore218 import SerialTemperatureSensor
from drivers.Lakeshore336 import TemperatureSensor


class SensorControllerAsync:
    def __init__(self, sample_hz=1):
        self.sample_hz = sample_hz
        self.period = 1 / sample_hz
        self.sensors = []
        self.latest_readings = {}
        self._init_sensors()

    def _init_sensors(self):
        sensors_specifications = [
            ("Lakeshore336", lambda: TemperatureSensor(name="temp_A", channel="A")),  # Lazy init
            ("Lakeshore218", lambda: SerialTemperatureSensor())
            # ("Name", lambda: Connect())
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
            timestamp = datetime.now().isoformat(timespec="milliseconds")

            self.latest_readings[sensor.name] = {
                "timestamp": timestamp,
                "value": value,
            }

            print({  # for demo
                "sensor": sensor.name,
                "timestamp": timestamp,
                "value": value,
            })

            return sensor.name, value
        except Exception as e:  # Purpose of try except here example: running a cryostat and a sensor gets unplugged
            logging.error(f"{sensor.name} read failed: {e}")
            return sensor.name, None

    async def sensor_loop(self, sensor):
        while True:
            start = asyncio.get_running_loop().time()

            await self.read_one(sensor)

            elapsed = asyncio.get_running_loop().time() - start
            sleep_time = max(0, self.period - elapsed)
            await asyncio.sleep(sleep_time)

    async def run(self):
        tasks = [asyncio.create_task(self.sensor_loop(sensor)) for sensor in self.sensors]
        await asyncio.gather(*tasks)
