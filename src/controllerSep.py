import asyncio
import logging
from datetime import datetime

from drivers.Lakeshore218 import SerialTemperatureSensor
from drivers.Lakeshore336 import TemperatureSensor
from drivers.Alicat import Alicat


class SensorControllerAsync:
    def __init__(self, sample_hz=1):
        self.sample_hz = sample_hz
        self.period = 1 / sample_hz
        self.sensors = []
        self.latest_readings = {}

    async def _init_sensors(self):
        sensors_specifications = [
            ("Lakeshore336", lambda: TemperatureSensor(name="temp_A", channel="A")),
            ("Lakeshore218", lambda: SerialTemperatureSensor()),
            ("Alicat", lambda: Alicat(name="alicat")),
        ]

        for sensor_name, sensor_init in sensors_specifications:
            try:
                sensor = sensor_init()

                if hasattr(sensor, "connect") and callable(sensor.connect):
                    await sensor.connect()

                sensor.failed = False
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

            print({
                "sensor": sensor.name,
                "timestamp": timestamp,
                "value": value,
            })

            return sensor.name, value

        except Exception as e:
            logging.error(f"{sensor.name} read failed: {e}")
            sensor.failed = True
            return sensor.name, None

    async def sensor_loop(self, sensor):
        while not getattr(sensor, "failed", False):
            start = asyncio.get_running_loop().time()

            await self.read_one(sensor)

            elapsed = asyncio.get_running_loop().time() - start
            sleep_time = max(0, self.period - elapsed)
            await asyncio.sleep(sleep_time)

        logging.warning(f"{sensor.name} loop stopped after read failure")

    async def run(self):
        await self._init_sensors()

        if not self.sensors:
            logging.warning("No sensors initialized successfully")
            return

        tasks = [asyncio.create_task(self.sensor_loop(sensor)) for sensor in self.sensors]
        await asyncio.gather(*tasks)

    def close(self):
        for sensor in self.sensors:
            try:
                sensor.close()
            except Exception as e:
                logging.error(f"Failed to close {sensor.name}: {e}")