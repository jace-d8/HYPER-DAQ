import asyncio
import logging
from datetime import datetime

from src.drivers.Lakeshore218 import SerialTemperatureSensor
from src.drivers.Lakeshore336 import TemperatureSensor
from src.drivers.Alicat import Alicat

# try:
#     from src.drivers.niDaq import NiDaqAnalogInput, NiDaqChannelConfig
# except Exception:
#     NiDaqAnalogInput = None
#     NiDaqChannelConfig = None


class SensorControllerAsync:
    def __init__(self, csv_buffer, sample_hz=1):
        self.sample_hz = sample_hz
        self.period = 1 / sample_hz
        self.sensors = []
        self.latest_readings = {}
        self.csv_buffer = csv_buffer
        self.start_loop_time = None
        self.transferred_total_kg = 0.0
        self._tasks = []
        self._stop_event = asyncio.Event()

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
            sensor = None
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

                if sensor is not None:
                    try:
                        if hasattr(sensor, "close") and callable(sensor.close):
                            maybe = sensor.close()
                            if asyncio.iscoroutine(maybe):
                                await maybe
                    except Exception as close_err:
                        logging.error(f"Failed to close partially initialized sensor: {close_err}")

        self.csv_buffer.set_available_sensors(available)

    async def read_one(self, sensor):
        try:
            payload = await sensor.read()

            if isinstance(payload, dict) and payload.get("kind") == "timeseries":
                timestamps = payload["timestamps"]
                values = payload["values"]

                self.latest_readings[sensor.name] = {
                    "timestamp": timestamps[-1],
                    "value": values[-1],
                    "series": payload,
                }

                for ts, val in zip(timestamps, values):
                    self.csv_buffer.update_sensor(sensor.name, ts, val)

                return sensor.name, payload

            timestamp = datetime.now().isoformat(timespec="milliseconds")

            self.latest_readings[sensor.name] = {
                "timestamp": timestamp,
                "value": payload,
            }

            self.csv_buffer.update_sensor(sensor.name, timestamp, payload)
            return sensor.name, payload

        except Exception as e:
            logging.error(f"{sensor.name} read failed: {e}")
            sensor.failed = True
            return sensor.name, None

    async def sensor_loop(self, sensor):
        try:
            while not self._stop_event.is_set() and not getattr(sensor, "failed", False):
                start = asyncio.get_running_loop().time()

                await self.read_one(sensor)

                elapsed = asyncio.get_running_loop().time() - start
                sleep_time = max(0, self.period - elapsed)

                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_time)
                except asyncio.TimeoutError:
                    pass

            if getattr(sensor, "failed", False):
                logging.warning(f"{sensor.name} loop stopped after read failure")

        except asyncio.CancelledError:
            logging.info(f"{sensor.name} loop cancelled")
            raise

    async def snapshot_loop(self):
        if self.start_loop_time is None:
            self.start_loop_time = asyncio.get_running_loop().time()

        try:
            while not self._stop_event.is_set():
                elapsed_seconds = asyncio.get_running_loop().time() - self.start_loop_time

                row = {
                    "time_min": elapsed_seconds / 60.0,
                }

                for sensor_name, payload in self.latest_readings.items():
                    row[sensor_name] = payload["value"]

                self.csv_buffer.append_snapshot(row)

                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.period)
                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:
            logging.info("Snapshot loop cancelled")
            raise

    async def run(self):
        await self._init_sensors()

        if not self.sensors:
            logging.warning("No sensors initialized successfully")
            return

        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(self.sensor_loop(sensor), name=f"sensor_loop:{sensor.name}")
            for sensor in self.sensors
        ]
        self._tasks.append(asyncio.create_task(self.snapshot_loop(), name="snapshot_loop"))

        try:
            await asyncio.gather(*self._tasks)

        except asyncio.CancelledError:
            logging.info("Sensor controller run cancelled")
            raise

        finally:
            await self.shutdown()

    async def shutdown(self):
        self._stop_event.set()

        tasks = [task for task in self._tasks if not task.done()]
        for task in tasks:
            task.cancel()

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logging.error(f"Task shutdown error: {result}")

        self._tasks.clear()
        await self.close()

    async def close(self):
        for sensor in self.sensors:
            try:
                if hasattr(sensor, "close") and callable(sensor.close):
                    maybe = sensor.close()
                    if asyncio.iscoroutine(maybe):
                        await maybe
            except Exception as e:
                name = getattr(sensor, "name", repr(sensor))
                logging.error(f"Failed to close {name}: {e}")