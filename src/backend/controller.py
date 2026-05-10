import ctypes
import logging
import queue
import sys
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


def _windows_timer_boost():
    """Force 1ms timer resolution. Idempotent; no-op off Windows."""
    if sys.platform != "win32":
        return None
    try:
        winmm = ctypes.WinDLL("winmm")
        winmm.timeBeginPeriod(1)
        return winmm
    except Exception:
        return None


def _windows_thread_priority_highest():
    """Raise the calling thread's priority. No-op off Windows."""
    if sys.platform != "win32":
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32")
        handle = kernel32.GetCurrentThread()
        kernel32.SetThreadPriority(handle, 2)  # THREAD_PRIORITY_HIGHEST
    except Exception:
        pass


class SensorThread(threading.Thread):
    """
    Polls one sensor in its own thread. Driver presents a sync interface
    (connect/read/close); any asyncio plumbing lives inside the driver.
    A slow or hung read on this sensor never affects others.
    """

    def __init__(self, sensor, on_reading, stop_event: threading.Event):
        super().__init__(daemon=True, name=f"sensor.{sensor.name}")
        self.sensor = sensor
        self.on_reading = on_reading
        self.stop_event = stop_event
        self.period = 1.0 / getattr(sensor, "poll_hz", SAMPLE_HZ)

    def run(self):
        if hasattr(self.sensor, "connect"):
            try:
                self.sensor.connect()
            except Exception as e:
                logging.error(f"{self.sensor.name} connect failed: {e}")
                return

        try:
            while not self.stop_event.is_set():
                t0 = time.monotonic()
                try:
                    payload = self.sensor.read()
                    if payload is not None:
                        self.on_reading(self.sensor.name, payload)
                except Exception as e:
                    logging.error(f"{self.sensor.name} read failed: {e}")
                self.stop_event.wait(max(0.0, self.period - (time.monotonic() - t0)))
        finally:
            if hasattr(self.sensor, "close"):
                try:
                    self.sensor.close()
                except Exception as e:
                    logging.error(f"{self.sensor.name} close failed: {e}")


class SnapshotThread(threading.Thread):
    """
    Produces one timestamped row per tick and pushes it to row_queue.
    Does no disk I/O — the WriterThread persists rows asynchronously,
    so this thread's timing is decoupled from filesystem stalls.
    """

    _BACKFILL_CAP = 60  # max rows produced in one wake-up after a long pause

    def __init__(self, shared_readings, readings_lock, row_queue, sample_hz, stop_event):
        super().__init__(daemon=True, name="snapshot")
        self.shared_readings = shared_readings
        self.readings_lock = readings_lock
        self.row_queue = row_queue
        self.period = 1.0 / sample_hz
        self.stop_event = stop_event

    def run(self):
        _windows_thread_priority_highest()
        start = time.monotonic()
        next_n = 0  # index of the next sample to emit
        _dbg_count = 0
        _dbg_prev_t0 = None
        while not self.stop_event.is_set():
            t0 = time.monotonic()

            cycle_ms = (t0 - _dbg_prev_t0) * 1000.0 if _dbg_prev_t0 is not None else 0.0
            _dbg_prev_t0 = t0

            # Highest sample index whose grid time has passed.
            target_n = int((t0 - start) / self.period)
            if target_n - next_n > self._BACKFILL_CAP:
                target_n = next_n + self._BACKFILL_CAP

            with self.readings_lock:
                readings = dict(self.shared_readings)

            rows_produced = 0
            while next_n <= target_n:
                row = {"time_min": (next_n * self.period) / 60.0}
                row.update(readings)
                self.row_queue.put(row)
                next_n += 1
                rows_produced += 1

            t_done = time.monotonic()
            iter_ms = (t_done - t0) * 1000.0
            _dbg_count += 1
            if cycle_ms > 150.0 or iter_ms > 20.0 or rows_produced > 1 or _dbg_count % 150 == 0:
                wait_ms = max(0.0, cycle_ms - iter_ms)
                qsize = self.row_queue.qsize()
                print(f"[snap] cycle={cycle_ms:6.1f}ms  wait={wait_ms:6.1f}  "
                      f"iter={iter_ms:5.2f}  produced={rows_produced:3d}  "
                      f"qsize={qsize:3d}  n={_dbg_count}",
                      flush=True)

            # Sleep until the next sample's grid time.
            next_target_t = start + next_n * self.period
            sleep_s = next_target_t - time.monotonic()
            if sleep_s > 0:
                self.stop_event.wait(sleep_s)


class WriterThread(threading.Thread):
    """
    Drains row_queue and persists rows. Decoupled from snapshot timing —
    if disk I/O stalls or this thread is descheduled, queued rows accumulate
    and get flushed in a batch on resume; timestamps stay accurate.
    """

    def __init__(self, row_queue, csv_buffer, stop_event):
        super().__init__(daemon=True, name="writer")
        self.row_queue = row_queue
        self.csv_buffer = csv_buffer
        self.stop_event = stop_event

    def run(self):
        _dbg_count = 0
        while not self.stop_event.is_set() or not self.row_queue.empty():
            try:
                first = self.row_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            batch = [first]
            while True:
                try:
                    batch.append(self.row_queue.get_nowait())
                except queue.Empty:
                    break

            t0 = time.monotonic()
            for r in batch:
                try:
                    self.csv_buffer.log_row(r)
                except Exception as e:
                    logging.error(f"Data log write failed: {e}")
                try:
                    self.csv_buffer.buffer_row(r)
                except Exception:
                    pass
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            _dbg_count += 1
            if elapsed_ms > 50.0 or len(batch) > 3 or _dbg_count % 150 == 0:
                qsize = self.row_queue.qsize()
                print(f"[wri ] batch={len(batch):3d}  elapsed={elapsed_ms:6.1f}ms  "
                      f"qsize_after={qsize:3d}  n={_dbg_count}", flush=True)


class SensorController:
    def __init__(self, csv_buffer, sample_hz=SAMPLE_HZ):
        self.sample_hz = sample_hz
        self.csv_buffer = csv_buffer
        self._stop_event = threading.Event()
        self._shared_readings: dict = {}
        self._readings_lock = threading.Lock()
        self._sensor_threads: list[SensorThread] = []
        self._snapshot_thread: SnapshotThread | None = None
        self._writer_thread: WriterThread | None = None
        self._row_queue: queue.Queue = queue.Queue()

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

    def run(self):
        """Blocks the calling thread until stop() is called or the process is interrupted."""
        _windows_timer_boost()

        sensors = self._build_sensors()
        if not sensors:
            logging.warning("No sensors initialized successfully")
            return

        self._stop_event.clear()

        for sensor in sensors:
            t = SensorThread(sensor, self._on_reading, self._stop_event)
            t.start()
            self._sensor_threads.append(t)

        self._writer_thread = WriterThread(
            self._row_queue, self.csv_buffer, self._stop_event,
        )
        self._writer_thread.start()

        self._snapshot_thread = SnapshotThread(
            self._shared_readings, self._readings_lock,
            self._row_queue, self.sample_hz, self._stop_event,
        )
        self._snapshot_thread.start()

        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(0.5)
        finally:
            self.close()

    def stop(self):
        self._stop_event.set()

    def close(self):
        self._stop_event.set()

        for t in self._sensor_threads:
            t.join(timeout=5.0)
        if self._snapshot_thread:
            self._snapshot_thread.join(timeout=5.0)
        if self._writer_thread:
            self._writer_thread.join(timeout=5.0)

        self._sensor_threads.clear()
        self._snapshot_thread = None
        self._writer_thread = None
