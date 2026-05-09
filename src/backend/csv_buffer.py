import csv
import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock


class CsvBuffer:
    def __init__(
        self,
        data_csv="sensor_data.csv",
        buffer_csv="sensor_buffer.csv",
        max_rows=5000,
        data_rows_per_file=10000,
        data_dir=".",
        logging_state_file=None,
    ):
        self.data_csv = data_csv
        self.buffer_csv = buffer_csv
        self.max_rows = max_rows
        self.data_rows_per_file = data_rows_per_file
        self.data_dir = Path(data_dir)
        self.logging_state_file = Path(logging_state_file) if logging_state_file else None

        self._lock = Lock()
        self._rows = []
        self._latest_by_sensor = {}
        self._available_sensors = {}
        self._columns = ["time_min"]

        self._current_data_path_value = None
        self._data_rows_written = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_available_sensors(self, sensor_map):
        with self._lock:
            self._available_sensors = {
                group: list(sensors) for group, sensors in sensor_map.items()
            }
            columns = ["time_min"]
            for _, sensors in self._available_sensors.items():
                for sensor in sensors:
                    if sensor not in columns:
                        columns.append(sensor)
            self._columns = columns
            self._ensure_csv_headers()
            self._load_existing_buffer_rows()

    def update_sensor(self, sensor_name, timestamp, value):
        with self._lock:
            self._latest_by_sensor[sensor_name] = {
                "timestamp": timestamp,
                "value": value,
            }

    def append_snapshot(self, row):
        self.log_row(row)
        self.buffer_row(row)

    def log_row(self, row):
        """Write to data log only. Awaited — must never be skipped."""
        with self._lock:
            normalized_row = {col: row.get(col, "") for col in self._columns}
            self._append_data_row(normalized_row)

    def buffer_row(self, row):
        """Write to display buffer. Fire-and-forget — can lag without affecting data accuracy."""
        with self._lock:
            normalized_row = {col: row.get(col, "") for col in self._columns}
            self._append_buffer_row(normalized_row)
            self._rows.append(normalized_row)
            if len(self._rows) > self.max_rows:
                self._rows = self._rows[-self.max_rows:]
                self._rewrite_buffer_csv()

    def close(self):
        """Clear the buffer CSV when the program shuts down."""
        with self._lock:
            try:
                with open(self.buffer_csv, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=self._columns)
                    writer.writeheader()
            except Exception:
                pass  # Best-effort; don't crash on shutdown

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_data_path(self) -> str:
        return self._current_data_path_value

    def _is_logging_enabled(self) -> bool:
        if self.logging_state_file is None:
            return True
        try:
            with open(self.logging_state_file) as f:
                return bool(json.load(f).get("enabled", False))
        except Exception:
            return False

    def _rotate_data_file(self):
        """Start a new timestamped data file in data_dir and write a fresh header."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        stem, ext = os.path.splitext(self.data_csv)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{stem}_{timestamp}{ext}"
        self._current_data_path_value = str(self.data_dir / filename)
        self._data_rows_written = 0
        with open(self._current_data_path_value, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._columns)
            writer.writeheader()

    def _ensure_csv_headers(self):
        self._rotate_data_file()
        with open(self.buffer_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._columns)
            writer.writeheader()

    def _append_data_row(self, row):
        if not self._is_logging_enabled():
            return

        if self._data_rows_written >= self.data_rows_per_file:
            self._rotate_data_file()

        path = self._current_data_path()
        file_exists = os.path.exists(path) and os.path.getsize(path) > 0
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._columns)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

        self._data_rows_written += 1

    def _append_buffer_row(self, row):
        file_exists = os.path.exists(self.buffer_csv) and os.path.getsize(self.buffer_csv) > 0
        with open(self.buffer_csv, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._columns)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def _rewrite_buffer_csv(self):
        with open(self.buffer_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._columns)
            writer.writeheader()
            writer.writerows(self._rows)

    def _load_existing_buffer_rows(self):
        if not os.path.exists(self.buffer_csv) or os.path.getsize(self.buffer_csv) == 0:
            self._rows = []
            return
        try:
            with open(self.buffer_csv, "r", newline="") as f:
                reader = csv.DictReader(f)
                self._rows = list(reader)[-self.max_rows:]
        except Exception:
            self._rows = []
