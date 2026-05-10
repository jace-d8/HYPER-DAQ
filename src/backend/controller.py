"""Multiprocessing-based sensor controller.

Each sensor runs in its own subprocess (one GIL per process), writing its
own CSV at native rate and pushing readings into a shared-memory ring
buffer for live consumers (the GUI).

A manifest file is written so the GUI can discover sensor names, channel
layouts, and shared-memory segment names without hard-coded coupling.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import time
from pathlib import Path

from src.backend.shared_buffer import SensorRingBuffer
from src.backend.sensor_runner import run_sensor


# ---------------------------------------------------------------------------
# Sensor specifications
#
# Each spec is a pickle-friendly dict so it can be passed to a subprocess.
# Drivers are loaded dynamically inside the subprocess via importlib.
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


def _shm_name(sensor_name: str) -> str:
    return f"hyperdaq_{sensor_name}"


class SensorController:
    """Spawns one subprocess per sensor and waits until stop is requested."""

    def __init__(self, data_dir: Path, manifest_path: Path, capacity: int = 4096):
        self.data_dir = Path(data_dir)
        self.manifest_path = Path(manifest_path)
        self.capacity = capacity

        self._stop_event = multiprocessing.Event()
        self._processes: list[multiprocessing.Process] = []
        self._buffers: list[SensorRingBuffer] = []

    def _write_manifest(self) -> None:
        manifest = {
            "capacity": self.capacity,
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

        # Pre-create shared memory in the parent so it survives even if a
        # subprocess crashes during init.
        for spec in SENSOR_SPECS:
            rb = SensorRingBuffer(
                name=_shm_name(spec["name"]),
                capacity=self.capacity,
                num_channels=len(spec["channels"]),
                create=True,
            )
            self._buffers.append(rb)

        self._write_manifest()

        for spec in SENSOR_SPECS:
            p = multiprocessing.Process(
                target=run_sensor,
                args=(
                    spec,
                    _shm_name(spec["name"]),
                    self.capacity,
                    str(self.data_dir),
                    self._stop_event,
                ),
                name=f"sensor.{spec['name']}",
                daemon=False,
            )
            p.start()
            self._processes.append(p)
            logging.info(f"spawned subprocess for {spec['name']} pid={p.pid}")

        try:
            while not self._stop_event.is_set():
                # Wake periodically so KeyboardInterrupt can land.
                self._stop_event.wait(0.5)
        finally:
            self.close()

    def stop(self) -> None:
        self._stop_event.set()

    def close(self) -> None:
        self._stop_event.set()

        for p in self._processes:
            p.join(timeout=5.0)
            if p.is_alive():
                logging.warning(f"terminating {p.name} (pid={p.pid})")
                p.terminate()
                p.join(timeout=2.0)
        self._processes.clear()

        for rb in self._buffers:
            rb.close()
            rb.unlink()
        self._buffers.clear()

        try:
            if self.manifest_path.exists():
                self.manifest_path.unlink()
        except Exception:
            pass
