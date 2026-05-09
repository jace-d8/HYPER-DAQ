import asyncio
import logging
import threading
import time

from src.drivers.Lakeshore218 import SerialTemperatureSensor
from src.drivers.Lakeshore336 import TemperatureSensor
from src.drivers.Alicat import Alicat
from src.frontend.config import SAMPLE_HZ

try:
    from src.drivers.niDaq import NiDaqTask, NiDaqChannelConfig
    _NIDAQMX_AVAILABLE = True
except ImportError:
    _NIDAQMX_AVAILABLE = False


class SensorThread(threading.Thread):
    """
    Dedicated thread per sensor with its own asyncio event loop.
    Async and sync drivers both work. Completely isolated from other sensors
    and the snapshot thread — a slow or hung read never affects anything else.
    """

    def __init__(self, sensor, on_reading, stop_event: threading.Event):
        super().__init__(daemon=True, name=f"sensor.{sensor.name}")
        self.sensor = sensor
        self.on_reading = on_reading
        self.stop_event = stop_event
        self.period = 1.0 / getattr(sensor, "poll_hz", SAMPLE_HZ)

    def run(self):
        asyncio.run(self._loop())

    async def _loop(self):
        if hasattr(self.sensor, "connect"):
            try:
                result = self.sensor.connect()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logging.error(f"{self.sensor.name} connect failed: {e}")
                return

        while not self.stop_event.is_set():
            t0 = asyncio.get_event_loop().time()
            try:
                if asyncio.iscoroutinefunction(self.sensor.read):
                    payload = await self.sensor.read()
                else:
                    payload = await asyncio.to_thread(self.sensor.read)
                if payload is not None:
                    self.on_reading(self.sensor.name, payload)
            except Exception as e:
                logging.error(f"{self.sensor.name} read failed: {e}")

            await asyncio.sleep(max(0.0, self.period - (asyncio.get_event_loop().time() - t0)))


class SnapshotThread(threading.Thread):
    """
    Writes one row per tick using OS-level threading.Event timer.
    Never shares resources with sensor threads — timing is consistent
    regardless of how slow or fast individual sensors are.
    """

    def __init__(self, shared_readings, readings_lock, csv_buffer, sample_hz, stop_event):
        super().__init__(daemon=True, name="snapshot")
        self.shared_readings = shared_readings
        self.readings_lock = readings_lock
        self.csv_buffer = csv_buffer
        self.period = 1.0 / sample_hz
        self.stop_event = stop_event

    def run(self):
        start = time.monotonic()
        while not self.stop_event.is_set():
            t0 = time.monotonic()

            with self.readings_lock:
                readings = dict(self.shared_readings)

            row = {"time_min": (t0 - start) / 60.0}
            row.update(readings)

            try:
                self.csv_buffer.log_row(row)
            except Exception as e:
                logging.error(f"Data log write failed: {e}")

            try:
                self.csv_buffer.buffer_row(row)
            except Exception:
                pass

            self.stop_event.wait(max(0.0, self.period - (time.monotonic() - t0)))


class SensorControllerAsync:
    def __init__(self, csv_buffer, sample_hz=SAMPLE_HZ):
        self.sample_hz = sample_hz
        self.csv_buffer = csv_buffer
        self._stop_event = threading.Event()
        self._shared_readings: dict = {}
        self._readings_lock = threading.Lock()
        self._sensor_threads: list[SensorThread] = []
        self._snapshot_thread: SnapshotThread | None = None

    def _on_reading(self, sensor_name: str, payload):
        with self._readings_lock:
            if isinstance(payload, dict):
                self._shared_readings.update(payload)
            else:
                self._shared_readings[sensor_name] = payload

    def _build_sensors(self) -> list:
        specs = [
            ("Temperature", lambda: TemperatureSensor(
                name="LS336_1",
                channels={
                    "TS1": "A",
                    # "TS2": "B",
                    # "TS3": "D2",
                    # "TS4": "D3",
                    # "TS5": "D4",
                },
            )),
            ("Mass Flow Rate", lambda: Alicat(name="Total Flow")),
            # --- Uncomment to enable NI-DAQ pressure sensors ---
            # ("Pressure", lambda: NiDaqTask(
            #     name="NI_Pressure",
            #     channels=[
            #         NiDaqChannelConfig("PT1", "Dev1/ai0", measurement_type="voltage"),
            #         NiDaqChannelConfig("PT2", "Dev1/ai1", measurement_type="voltage"),
            #         NiDaqChannelConfig("PT3", "Dev1/ai2", measurement_type="voltage"),
            #         NiDaqChannelConfig("PT4", "Dev1/ai3", measurement_type="voltage"),
            #         NiDaqChannelConfig("PT5", "Dev1/ai4", measurement_type="voltage"),
            #         NiDaqChannelConfig("PT6", "Dev1/ai5", measurement_type="voltage"),
            #         NiDaqChannelConfig("PT7", "Dev1/ai6", measurement_type="voltage"),
            #     ],
            #     sample_hz=SAMPLE_HZ,
            # )),
        ]

        available = {}
        sensors = []

        for group_name, sensor_init in specs:
            try:
                sensor = sensor_init()
                sensors.append(sensor)
                if hasattr(sensor, "channels"):
                    ch = sensor.channels
                    if isinstance(ch, dict):
                        available.setdefault(group_name, []).extend(ch.keys())
                    else:
                        available.setdefault(group_name, []).extend(cfg.name for cfg in ch)
                else:
                    available.setdefault(group_name, []).append(sensor.name)
                logging.info(f"{sensor.name} initialized")
            except Exception as e:
                logging.error(f"{group_name} sensor failed: {e}")

        self.csv_buffer.set_available_sensors(available)
        return sensors

    async def run(self):
        sensors = await asyncio.to_thread(self._build_sensors)
        if not sensors:
            logging.warning("No sensors initialized successfully")
            return

        self._stop_event.clear()

        for sensor in sensors:
            t = SensorThread(sensor, self._on_reading, self._stop_event)
            t.start()
            self._sensor_threads.append(t)

        self._snapshot_thread = SnapshotThread(
            self._shared_readings, self._readings_lock,
            self.csv_buffer, self.sample_hz, self._stop_event,
        )
        self._snapshot_thread.start()

        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            await self.close()

    async def close(self):
        self._stop_event.set()

        for t in self._sensor_threads:
            t.join(timeout=5.0)
        if self._snapshot_thread:
            self._snapshot_thread.join(timeout=5.0)

        for t in self._sensor_threads:
            sensor = t.sensor
            if hasattr(sensor, "close"):
                try:
                    result = sensor.close()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logging.error(f"Failed to close {sensor.name}: {e}")

        self._sensor_threads.clear()
        self._snapshot_thread = None
