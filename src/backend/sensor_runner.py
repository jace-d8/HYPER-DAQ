"""Entry point for one sensor subprocess.

Spawned by the controller via multiprocessing.Process(target=run_sensor, ...).
Imports the driver, connects, then loops:
    read() → push to ring buffer → (write CSV row if logging is ON)

Logging state is gated by ``logging_state.json``; we poll it every
LOGGING_POLL_PERIOD seconds. Per-sensor CSV lives in the active run
directory, only opened on the OFF→ON edge.

All time_min values use ``start_monotonic`` (passed in from the parent)
as the reference, so every CSV and the GUI display share a time frame.
"""

import csv
import importlib
import json
import logging
import time
from pathlib import Path

from src.backend.shared_buffer import SensorRingBuffer


LOGGING_POLL_PERIOD = 0.5  # seconds between logging_state.json checks


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


def _read_state(path: Path) -> dict:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def run_sensor(
    spec: dict,
    shm_name: str,
    capacity: int,
    start_monotonic: float,
    logging_state_path: str,
    stop_event,
):
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

    period = 1.0 / float(getattr(sensor, "poll_hz", 15))

    state_path = Path(logging_state_path)
    last_state_check = 0.0
    csv_fh = None
    csv_writer = None
    current_run_dir: Path | None = None

    def _open_csv(run_dir: Path):
        nonlocal csv_fh, csv_writer, current_run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{name}.csv"
        csv_fh = open(path, "w", newline="")
        csv_writer = csv.writer(csv_fh)
        csv_writer.writerow(["time_min"] + channels)
        csv_fh.flush()
        current_run_dir = run_dir
        logging.info(f"opened {path}")

    def _close_csv():
        nonlocal csv_fh, csv_writer, current_run_dir
        if csv_fh is not None:
            try:
                csv_fh.close()
            except Exception:
                pass
            logging.info("closed CSV")
        csv_fh = None
        csv_writer = None
        current_run_dir = None

    try:
        while not stop_event.is_set():
            t0 = time.monotonic()

            # Check logging state on a slower cadence than the read loop.
            if t0 - last_state_check >= LOGGING_POLL_PERIOD:
                last_state_check = t0
                state = _read_state(state_path)
                want_logging = bool(state.get("enabled", False))
                want_run_dir = Path(state["run_dir"]) if state.get("run_dir") else None

                if want_logging and want_run_dir and (csv_fh is None or want_run_dir != current_run_dir):
                    if csv_fh is not None:
                        _close_csv()
                    try:
                        _open_csv(want_run_dir)
                    except Exception as e:
                        logging.error(f"open csv failed: {e}")
                elif not want_logging and csv_fh is not None:
                    _close_csv()

            try:
                payload = sensor.read()
                t_min = (t0 - start_monotonic) / 60.0

                if payload is None:
                    values = [None] * len(channels)
                else:
                    values = _coerce(payload, channels)

                rb.push(t_min, values)

                if csv_writer is not None:
                    row = [f"{t_min:.6f}"]
                    for v in values:
                        if isinstance(v, (int, float)) and v == v:
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
        _close_csv()
        if hasattr(sensor, "close"):
            try:
                sensor.close()
            except Exception:
                pass
        rb.close()
