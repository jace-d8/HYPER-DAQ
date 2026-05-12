"""Lock-free single-producer / multi-consumer ring buffer in shared memory.

Layout (all little-endian, native byte order):
    bytes  0..7   write_idx     int64, monotonically increasing across the run
    bytes  8..15  num_channels  int64
    bytes 16..23  capacity      int64
    bytes 24..    capacity rows of (1 + num_channels) float64 values
                  each row: (timestamp_min, ch0, ch1, ..., chN-1)

"""

from __future__ import annotations

import numpy as np
from multiprocessing import shared_memory
from typing import Tuple

_HEADER_SIZE = 24  # 3 × int64


class SensorRingBuffer:
    def __init__(
        self,
        name: str,
        capacity: int = 4096,
        num_channels: int = 1,
        create: bool = False,
    ):
        self.name = name
        row_bytes = (1 + num_channels) * 8

        if create:
            total = _HEADER_SIZE + capacity * row_bytes
            try:
                self._shm = shared_memory.SharedMemory(name=name, create=True, size=total)
            except FileExistsError:
                stale = shared_memory.SharedMemory(name=name, create=False)
                stale.close()
                stale.unlink()
                self._shm = shared_memory.SharedMemory(name=name, create=True, size=total)
            self._header = np.ndarray((3,), dtype=np.int64, buffer=self._shm.buf[:_HEADER_SIZE])
            self._header[0] = 0
            self._header[1] = num_channels
            self._header[2] = capacity
        else:
            self._shm = shared_memory.SharedMemory(name=name, create=False)
            self._header = np.ndarray((3,), dtype=np.int64, buffer=self._shm.buf[:_HEADER_SIZE])

        self.num_channels = int(self._header[1])
        self.capacity = int(self._header[2])

        data_bytes = self.capacity * (1 + self.num_channels) * 8
        self._data = np.ndarray(
            (self.capacity, 1 + self.num_channels),
            dtype=np.float64,
            buffer=self._shm.buf[_HEADER_SIZE:_HEADER_SIZE + data_bytes],
        )

    @property
    def write_idx(self) -> int:
        return int(self._header[0])

    def push(self, timestamp_min: float, values) -> None:
        """Single-producer. Writes one row and bumps write_idx."""
        idx = int(self._header[0])
        slot = idx % self.capacity
        self._data[slot, 0] = timestamp_min
        for i in range(self.num_channels):
            v = values[i] if i < len(values) else None
            self._data[slot, 1 + i] = float(v) if v is not None else float("nan")
        self._header[0] = idx + 1

    def snapshot(self, last_idx: int) -> Tuple[np.ndarray, int]:
        """Multi-consumer. Returns rows produced since last_idx and the new
        index. If the producer has lapped the buffer, only the most recent
        `capacity` rows are returned."""
        current = int(self._header[0])
        if current <= last_idx:
            return np.empty((0, 1 + self.num_channels), dtype=np.float64), current
        n = min(current - last_idx, self.capacity)
        first = current - n
        out = np.empty((n, 1 + self.num_channels), dtype=np.float64)
        for i in range(n):
            slot = (first + i) % self.capacity
            out[i] = self._data[slot]
        return out, current

    def close(self) -> None:
        try:
            self._shm.close()
        except Exception:
            pass

    def unlink(self) -> None:
        try:
            self._shm.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass
