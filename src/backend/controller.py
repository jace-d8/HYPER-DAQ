"""Multiprocessing-based sensor controller.

Each sensor runs in its own subprocess (one GIL per process), pushing
readings into a shared-memory ring buffer for live consumers (the GUI).
The controller also runs a small UnifierThread in the parent process
that, while logging is enabled, drains all ring buffers at 30 Hz and
writes a unified wide-format CSV into the active run directory.

Logging is gated by ``logging_state.json``, which the GUI maintains.
A shared ``start_monotonic`` is written to the manifest so every CSV
``time_min`` value is in the same frame as the GUI display.
"""

from __future__ import annotations

import csv
import json
import logging
import multiprocessing
import threading
import time
from pathlib import Path

from src.backend.shared_buffer import SensorRingBuffer
from src.backend.sensor_runner import run_sensor

# Optional NI-DAQ import — only needed if NIDaq specs are uncommented below.
# Guarded so machines without nidaqmx installed can still import this module.
try:
    from src.drivers.niDaq import NiDaqChannelConfig  # noqa: F401
except ImportError:
    NiDaqChannelConfig = None  # type: ignore


# ---------------------------------------------------------------------------
# Sensor specifications
# ---------------------------------------------------------------------------

SENSOR_SPECS = [
    {
        "name": "LS336_1",
        "module": "src.drivers.Lakeshore336",
        "class": "TemperatureSensor",
        "kwargs": {
            "name": "LS336_1",
            "channels": {"TS1": "A"},
            # "TS2": "B", "TS3": "D2", "TS4": "D3", "TS5": "D4",
        },
        "channels": ["TS1"],
        "group": "Temperature",
    },
    {
        "name": "Alicat",
        "module": "src.drivers.Alicat",
        "class": "Alicat",
        "kwargs": {"name": "Total Flow"},
        "channels": ["Total Flow"],
        "group": "Mass Flow Rate",
    },
    # --- Example: 2 current sensors via NI-DAQ (4-20 mA loop) --------------
    # Uncomment, requires nidaqmx installed.
    {
        "name": "NI_Pressure",
        "module": "src.drivers.niDaq",
        "class": "NiDaqTask",
        "kwargs": {
            "name": "NI_Pressure",
            "channels": [
                NiDaqChannelConfig(name="PT1", physical_channel="cDAQ2Mod1/ai0", measurement_type="current", min_val=0.002, max_val = 0.004),
                NiDaqChannelConfig(name="PT2", physical_channel="cDAQ2Mod1/ai2", measurement_type="current", min_val=0.002, max_val = 0.004),
            ],
            "sample_hz": 15,
        },
        "channels": ["PT1", "PT2", "PT3", "PT4", "PT5", "PT6", "PT7"],
        "group": "Pressure",
    },
]


# Unified CSV configuration
# 10000 rows @ ~2.78 Hz ≈ 1 hour per file. Rotates to a new shard at the cap.
UNIFIED_RATE_HZ = 10_000 / 3600  # ≈ 2.78 Hz
UNIFIED_MAX_ROWS = 10_000


def _shm_name(sensor_name: str) -> str:
    return f"hyperdaq_{sensor_name}"


def _read_logging_state(path: Path) -> dict:
    """Returns {} if absent/malformed. Safe to call from any process."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_logging_state(path: Path, state: dict) -> None:
    """Atomic write via temp-file rename so readers never see a torn file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f)
    tmp.replace(path)


class UnifierThread(threading.Thread):
    """Background thread in the parent process. Drains every sensor's ring
    buffer at UNIFIED_RATE_HZ, takes the latest reading per channel, and
    writes a wide-format unified CSV when logging is enabled.

    Stops writing (and disables logging) when UNIFIED_MAX_ROWS is reached
    or when ``logging_state.json`` flips ``enabled`` back to false.
    """

    POLL_PERIOD = 1.0 / UNIFIED_RATE_HZ
    STATE_CHECK_PERIOD = 0.25  # seconds

    def __init__(self, buffers, all_channels, logging_state_file, start_monotonic, stop_event):
        super().__init__(daemon=True, name="unifier")
        self.buffers = buffers  # list of dicts: {"name", "channels", "rb"}
        self.all_channels = all_channels  # ordered list of "sensor.channel"
        self.logging_state_file = logging_state_file
        self.start_monotonic = start_monotonic
        self.stop_event = stop_event

    def _open_unified_shard(self, run_dir: Path, shard_idx: int):
        path = run_dir / f"unified_{shard_idx:03d}.csv"
        fh = open(path, "w", newline="")
        writer = csv.writer(fh)
        writer.writerow(["time_min"] + self.all_channels)
        fh.flush()
        logging.info(f"opened {path.name}")
        return fh, writer

    def run(self):
        latest: dict = {}                  # channel_key -> latest value
        per_sensor_last_idx: list = [0] * len(self.buffers)

        fh = None
        writer = None
        rows_written = 0
        shard_idx = 1
        current_run_dir = None
        last_state_check = 0.0

        def _close_current():
            nonlocal fh, writer, rows_written
            if fh is not None:
                try:
                    fh.close()
                except Exception:
                    pass
                logging.info(f"closed unified shard ({rows_written} rows)")
            fh = None
            writer = None
            rows_written = 0

        while not self.stop_event.is_set():
            tick_t0 = time.monotonic()

            # Refresh latest values from every ring buffer.
            for i, entry in enumerate(self.buffers):
                rows, new_idx = entry["rb"].snapshot(per_sensor_last_idx[i])
                per_sensor_last_idx[i] = new_idx
                if rows.shape[0] == 0:
                    continue
                last_row = rows[-1]
                for j, ch in enumerate(entry["channels"]):
                    key = f"{entry['name']}.{ch}"
                    latest[key] = float(last_row[1 + j])

            # Periodically re-check the logging state.
            if tick_t0 - last_state_check >= self.STATE_CHECK_PERIOD:
                last_state_check = tick_t0
                state = _read_logging_state(self.logging_state_file)
                want_logging = bool(state.get("enabled", False))
                want_run_dir = Path(state["run_dir"]) if state.get("run_dir") else None

                # Transition: start logging (or switch to a new run_dir)
                if want_logging and want_run_dir and want_run_dir != current_run_dir:
                    _close_current()
                    try:
                        want_run_dir.mkdir(parents=True, exist_ok=True)
                        shard_idx = 1
                        fh, writer = self._open_unified_shard(want_run_dir, shard_idx)
                        current_run_dir = want_run_dir
                    except Exception as e:
                        logging.error(f"unified open failed: {e}")
                        fh = None

                # Transition: user toggled logging off
                elif not want_logging and fh is not None:
                    _close_current()
                    current_run_dir = None

            # Write one unified row at the target rate, if logging.
            if fh is not None and writer is not None:
                t_min = (tick_t0 - self.start_monotonic) / 60.0
                row = [f"{t_min:.6f}"]
                for ch in self.all_channels:
                    v = latest.get(ch)
                    row.append(f"{v:.6f}" if v is not None and v == v else "")
                writer.writerow(row)
                fh.flush()
                rows_written += 1

                if rows_written >= UNIFIED_MAX_ROWS:
                    # Rotate to a new shard; logging stays on.
                    _close_current()
                    shard_idx += 1
                    try:
                        fh, writer = self._open_unified_shard(current_run_dir, shard_idx)
                    except Exception as e:
                        logging.error(f"unified shard rotation failed: {e}")
                        fh = None

            # Sleep to maintain UNIFIED_RATE_HZ.
            sleep_s = self.POLL_PERIOD - (time.monotonic() - tick_t0)
            if sleep_s > 0:
                self.stop_event.wait(sleep_s)

        _close_current()


class SensorController:
    """Spawns one subprocess per sensor and waits until stop is requested."""

    def __init__(
        self,
        data_dir: Path,
        manifest_path: Path,
        logging_state_file: Path,
        capacity: int = 4096,
    ):
        self.data_dir = Path(data_dir)
        self.manifest_path = Path(manifest_path)
        self.logging_state_file = Path(logging_state_file)
        self.capacity = capacity

        self._stop_event = multiprocessing.Event()
        self._unifier_stop = threading.Event()
        self._processes: list[multiprocessing.Process] = []
        self._buffers: list[dict] = []
        self._unifier: UnifierThread | None = None
        self._start_monotonic: float = 0.0

    def _write_manifest(self) -> None:
        manifest = {
            "capacity": self.capacity,
            "start_monotonic": self._start_monotonic,
            "sensors": [
                {
                    "name": spec["name"],
                    "channels": spec["channels"],
                    "group": spec.get("group", "Other"),
                    "shm_name": _shm_name(spec["name"]),
                }
                for spec in SENSOR_SPECS
            ],
        }
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(self.manifest_path.suffix + ".tmp")
        with open(tmp, "w") as f:
            json.dump(manifest, f, indent=2)
        tmp.replace(self.manifest_path)

    def run(self) -> None:
        """Blocks the caller until stop() is called or the process is killed."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Wipe any stale logging state from a previous crash — logging starts OFF.
        _write_logging_state(self.logging_state_file, {"enabled": False})

        # Establish the shared time origin for the entire run.
        self._start_monotonic = time.monotonic()

        # Pre-create shared memory in the parent.
        for spec in SENSOR_SPECS:
            rb = SensorRingBuffer(
                name=_shm_name(spec["name"]),
                capacity=self.capacity,
                num_channels=len(spec["channels"]),
                create=True,
            )
            self._buffers.append({
                "name": spec["name"],
                "channels": spec["channels"],
                "rb": rb,
            })

        self._write_manifest()

        # Spawn one subprocess per sensor.
        for spec in SENSOR_SPECS:
            p = multiprocessing.Process(
                target=run_sensor,
                args=(
                    spec,
                    _shm_name(spec["name"]),
                    self.capacity,
                    self._start_monotonic,
                    str(self.logging_state_file),
                    self._stop_event,
                ),
                name=f"sensor.{spec['name']}",
                daemon=False,
            )
            p.start()
            self._processes.append(p)
            logging.info(f"spawned subprocess for {spec['name']} pid={p.pid}")

        # Spin up the unifier thread (uses the parent-process ring buffers).
        all_channels = []
        for entry in self._buffers:
            for ch in entry["channels"]:
                all_channels.append(f"{entry['name']}.{ch}")
        self._unifier = UnifierThread(
            buffers=self._buffers,
            all_channels=all_channels,
            logging_state_file=self.logging_state_file,
            start_monotonic=self._start_monotonic,
            stop_event=self._unifier_stop,
        )
        self._unifier.start()

        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(0.5)
        finally:
            self.close()

    def stop(self) -> None:
        self._stop_event.set()

    def close(self) -> None:
        self._stop_event.set()
        self._unifier_stop.set()
        if self._unifier:
            self._unifier.join(timeout=2.0)
            self._unifier = None

        for p in self._processes:
            p.join(timeout=5.0)
            if p.is_alive():
                logging.warning(f"terminating {p.name} (pid={p.pid})")
                p.terminate()
                p.join(timeout=2.0)
        self._processes.clear()

        for entry in self._buffers:
            entry["rb"].close()
            entry["rb"].unlink()
        self._buffers.clear()

        try:
            if self.manifest_path.exists():
                self.manifest_path.unlink()
        except Exception:
            pass
