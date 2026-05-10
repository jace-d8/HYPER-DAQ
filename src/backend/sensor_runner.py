"""Entry point for one sensor subprocess.

Spawned by the controller via multiprocessing.Process(target=run_sensor, ...).
Imports the driver, connects, then loops:
    read() → push to ring buffer → write CSV row.

Per-sensor CSV in data_dir captures every reading at native rate.
Ring buffer (shared memory) carries readings to live consumers.
"""

import csv
import importlib
import logging
import time
from datetime import datetime
from pathlib import Path

from src.backend.shared_buffer import SensorRingBuffer


def _coerce(values, channels):
    """Normalize a payload (dict or scalar) into an ordered list aligned with
    the declared channel names."""
    if isinstance(values, dict):
        return [values.get(ch) for ch in channels]
    if len(channels) == 1:
        return [values]
    raise ValueError(
        f"sensor returned a non-dict payload but {len(channels)} channels are declared"
    )


def run_sensor(spec: dict, shm_name: str, capacity: int, data_dir: str, stop_event):
    """Long-running entry point. Returns when stop_event is set."""
    name = spec["name"]
    channels = spec["channels"]

    logging.basicConfig(
        level=logging.INFO,
        format=f"[{name}] %(asctime)s %(levelname)s %(message)s",
    )

    # Construct the sensor inside the subprocess (drivers may grab hardware handles).
    mod = importlib.import_module(spec["module"])
    cls = getattr(mod, spec["class"])
    sensor = cls(**spec["kwargs"])

    if hasattr(sensor, "connect"):
        try:
            sensor.connect()
        except Exception as e:
            logging.error(f"connect failed: {e}")
            return

    rb = SensorRingBuffer(
        name=shm_name,
        capacity=capacity,
        num_channels=len(channels),
        create=False,
    )

    Path(data_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    csv_path = Path(data_dir) / f"{name}_{ts}.csv"
    csv_fh = open(csv_path, "w", newline="")
    csv_writer = csv.writer(csv_fh)
    csv_writer.writerow(["time_min"] + channels)
    csv_fh.flush()

    period = 1.0 / float(getattr(sensor, "poll_hz", 15))
    start = time.monotonic()

    try:
        while not stop_event.is_set():
            t0 = time.monotonic()
            try:
                payload = sensor.read()
                t_min = (t0 - start) / 60.0

                if payload is None:
                    values = [None] * len(channels)
                else:
                    values = _coerce(payload, channels)

                rb.push(t_min, values)

                row = [f"{t_min:.6f}"]
                for v in values:
                    if isinstance(v, (int, float)) and v == v:  # not NaN
                        row.append(f"{v:.6f}")
                    else:
                        row.append("")
                csv_writer.writerow(row)
                csv_fh.flush()
            except Exception as e:
                logging.error(f"read failed: {e}")

            if stop_event.wait(max(0.0, period - (time.monotonic() - t0))):
                break
    finally:
        try:
            csv_fh.close()
        except Exception:
            pass
        if hasattr(sensor, "close"):
            try:
                sensor.close()
            except Exception:
                pass
        rb.close()
