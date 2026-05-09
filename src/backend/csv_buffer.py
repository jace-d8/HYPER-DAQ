import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path
from threading import Lock


class CsvBuffer:
    _LOG_CACHE_TTL = 1.0  # re-read logging_state.json at most once per second

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
        self._columns = ["time_min"]
        self._data_rows_written = 0

        self._data_fh = None
        self._data_writer = None
        self._buf_fh = None
        self._buf_writer = None

        self._log_enabled_cache = False
        self._log_cache_ts = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_available_sensors(self, sensor_map):
        with self._lock:
            columns = ["time_min"]
            for sensors in sensor_map.values():
                for sensor in sensors:
                    if sensor not in columns:
                        columns.append(sensor)
            self._columns = columns
            self._open_data_file()
            self._open_buffer_file()
            self._load_existing_buffer_rows()

    def update_sensor(self, sensor_name, timestamp, value):
        pass  # readings now flow through shared_readings in controller

    def log_row(self, row):
        """Write to data log only. Called from snapshot thread — reliable, never skipped."""
        with self._lock:
            if not self._is_logging_enabled():
                return
            if self._data_fh is None:
                self._open_data_file()
            if self._data_rows_written >= self.data_rows_per_file:
                self._open_data_file()
            normalized = {col: row.get(col, "") for col in self._columns}
            self._data_writer.writerow(normalized)
            self._data_fh.flush()
            self._data_rows_written += 1

    def buffer_row(self, row):
        """Write to display buffer. Can lag without affecting data accuracy."""
        with self._lock:
            if self._buf_fh is None:
                self._open_buffer_file()
            normalized = {col: row.get(col, "") for col in self._columns}
            self._buf_writer.writerow(normalized)
            self._buf_fh.flush()
            self._rows.append(normalized)
            if len(self._rows) > self.max_rows:
                self._rows = self._rows[-self.max_rows:]
                self._rewrite_buffer_file()

    def append_snapshot(self, row):
        self.log_row(row)
        self.buffer_row(row)

    def close(self):
        with self._lock:
            for fh in (self._data_fh, self._buf_fh):
                if fh:
                    try:
                        fh.close()
                    except Exception:
                        pass
            self._data_fh = None
            self._buf_fh = None
            try:
                with open(self.buffer_csv, "w", newline="") as f:
                    csv.DictWriter(f, fieldnames=self._columns).writeheader()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_logging_enabled(self) -> bool:
        now = time.monotonic()
        if now - self._log_cache_ts >= self._LOG_CACHE_TTL:
            if self.logging_state_file is None:
                self._log_enabled_cache = True
            else:
                try:
                    with open(self.logging_state_file) as f:
                        self._log_enabled_cache = bool(json.load(f).get("enabled", False))
                except Exception:
                    pass
            self._log_cache_ts = now
        return self._log_enabled_cache

    def _open_data_file(self):
        if self._data_fh:
            try:
                self._data_fh.close()
            except Exception:
                pass
        self.data_dir.mkdir(parents=True, exist_ok=True)
        stem, ext = os.path.splitext(self.data_csv)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = self.data_dir / f"{stem}_{timestamp}{ext}"
        self._data_fh = open(path, "w", newline="")
        self._data_writer = csv.DictWriter(self._data_fh, fieldnames=self._columns)
        self._data_writer.writeheader()
        self._data_fh.flush()
        self._data_rows_written = 0

    def _open_buffer_file(self):
        if self._buf_fh:
            try:
                self._buf_fh.close()
            except Exception:
                pass
        self._buf_fh = open(self.buffer_csv, "w", newline="")
        self._buf_writer = csv.DictWriter(self._buf_fh, fieldnames=self._columns)
        self._buf_writer.writeheader()
        self._buf_fh.flush()

    def _rewrite_buffer_file(self):
        if self._buf_fh:
            try:
                self._buf_fh.close()
            except Exception:
                pass
        self._buf_fh = open(self.buffer_csv, "w", newline="")
        self._buf_writer = csv.DictWriter(self._buf_fh, fieldnames=self._columns)
        self._buf_writer.writeheader()
        self._buf_writer.writerows(self._rows)
        self._buf_fh.flush()

    def _load_existing_buffer_rows(self):
        if not os.path.exists(self.buffer_csv) or os.path.getsize(self.buffer_csv) == 0:
            self._rows = []
            return
        try:
            with open(self.buffer_csv, "r", newline="") as f:
                self._rows = list(csv.DictReader(f))[-self.max_rows:]
        except Exception:
            self._rows = []
