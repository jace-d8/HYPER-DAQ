import asyncio
import serial
from src.drivers.sensor_base import SensorBase


class SerialTemperatureSensor(SensorBase):

    def __init__(self, name="218_temp", port="/dev/tty.usbserial-FTDZA5QJ"):
        super().__init__(name)

        self.ser = serial.Serial(
            port,
            baudrate=9600,
            bytesize=serial.SEVENBITS,
            parity=serial.PARITY_ODD,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        )
        self._lock = asyncio.Lock() # only send query at once

    # blocking function (runs in thread)
    def _query(self, cmd):
        self.ser.write((cmd + '\r\n').encode('ascii'))
        return self.ser.readline().decode('ascii', errors='ignore').strip()
    # read bytes until newline (/n)
    # convert bytes into str
    # ignore errors (testing)
    # remove newline

    async def read(self):
        async with self._lock:
            value = await asyncio.to_thread(self._query, "KRDG? 1")
        return float(value)

    async def disconnect(self):
        if self.ser and self.ser.is_open:
            await asyncio.to_thread(self.ser.close)