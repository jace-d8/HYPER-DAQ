import csv
import os
from threading import Lock


class CsvBuffer:
    def __init__(self, data_csv="sensor_data.csv", buffer_csv="sensor_buffer.csv", max_rows=5000):
        self.data_csv = data_csv
        self.buffer_csv = buffer_csv
        self.max_rows = max_rows

        self._lock = Lock()
        self._rows = []
        self._latest_by_sensor = {}
        self._available_sensors = {}
        self._columns = ["time_min"]

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
        with self._lock:
            normalized_row = {col: row.get(col, "") for col in self._columns}

            self._append_data_row(normalized_row)
            self._append_buffer_row(normalized_row)

            self._rows.append(normalized_row)
            if len(self._rows) > self.max_rows:
                self._rows = self._rows[-self.max_rows:]
                self._rewrite_buffer_csv()

    def _ensure_csv_headers(self):
        if not os.path.exists(self.data_csv) or os.path.getsize(self.data_csv) == 0:
            with open(self.data_csv, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._columns)
                writer.writeheader()

        if not os.path.exists(self.buffer_csv) or os.path.getsize(self.buffer_csv) == 0:
            with open(self.buffer_csv, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._columns)
                writer.writeheader()

    def _append_data_row(self, row):
        file_exists = os.path.exists(self.data_csv) and os.path.getsize(self.data_csv) > 0

        with open(self.data_csv, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._columns)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

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