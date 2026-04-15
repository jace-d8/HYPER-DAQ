import asyncio
import logging
from datetime import datetime

from src.drivers.Lakeshore218 import SerialTemperatureSensor
from src.drivers.Lakeshore336 import TemperatureSensor
from src.drivers.Alicat import Alicat

try:
    from niDaq import NiDaqAnalogInput, NiDaqChannelConfig
except Exception:
    NiDaqAnalogInput = None
    NiDaqChannelConfig = None


class SensorControllerAsync:
    def __init__(self, csv_buffer, sample_hz=1):
        self.sample_hz = sample_hz
        self.period = 1 / sample_hz
        self.sensors = []
        self.latest_readings = {}
        self.csv_buffer = csv_buffer
        self.start_loop_time = None
        self.transferred_total_kg = 0.0

    async def _init_sensors(self):
        sensors_specifications = [
            ("Temperature", lambda: TemperatureSensor(name="TS1", channel="A")),
            ("Temperature", lambda: SerialTemperatureSensor(name="TS2")),
            ("Mass Flow Rate", lambda: Alicat(name="Total Flow")),
        ]

        # if NiDaqAnalogInput is not None and NiDaqChannelConfig is not None:
        #     sensors_specifications.append(
        #         (
        #             "Pressure",
        #             lambda: NiDaqAnalogInput(
        #                 NiDaqChannelConfig(
        #                     name="PT1",
        #                     physical_channel="Dev1/ai0",
        #                     measurement_type="voltage",
        #                     min_val=0.0,
        #                     max_val=5.0,
        #                     terminal_config="RSE",
        #                     sample_hz=1000,
        #                     samples_per_read=50,
        #                     reduction="mean",
        #                 )
        #             ),
        #         )
        #     )

        available = {}

        for group_name, sensor_init in sensors_specifications:
            try:
                sensor = sensor_init()

                if hasattr(sensor, "connect") and callable(sensor.connect):
                    maybe = sensor.connect()
                    if asyncio.iscoroutine(maybe):
                        await maybe

                sensor.failed = False
                self.sensors.append(sensor)
                available.setdefault(group_name, []).append(sensor.name)
                logging.info(f"{sensor.name} initialized")
            except Exception as e:
                logging.error(f"{group_name} sensor failed to initialize: {e}")

        self.csv_buffer.set_available_sensors(available)

    async def read_one(self, sensor):
        try:
            value = await sensor.read()
            timestamp = datetime.now().isoformat(timespec="milliseconds")

            self.latest_readings[sensor.name] = {
                "timestamp": timestamp,
                "value": value,
            }

            self.csv_buffer.update_sensor(sensor.name, timestamp, value)

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

    async def snapshot_loop(self):
        if self.start_loop_time is None:
            self.start_loop_time = asyncio.get_running_loop().time()

        while True:
            elapsed_seconds = asyncio.get_running_loop().time() - self.start_loop_time

            row = {
                "time_min": elapsed_seconds / 60.0,
            }

            for sensor_name, payload in self.latest_readings.items():
                row[sensor_name] = payload["value"]

            self.csv_buffer.append_snapshot(row)

            await asyncio.sleep(self.period)

    async def run(self):
        await self._init_sensors()

        if not self.sensors:
            logging.warning("No sensors initialized successfully")
            return

        sensor_tasks = [
            asyncio.create_task(self.sensor_loop(sensor))
            for sensor in self.sensors
        ]

        snapshot_task = asyncio.create_task(self.snapshot_loop())

        await asyncio.gather(*sensor_tasks, snapshot_task)

    def close(self):
        for sensor in self.sensors:
            try:
                sensor.close()
            except Exception as e:
                logging.error(f"Failed to close {sensor.name}: {e}")