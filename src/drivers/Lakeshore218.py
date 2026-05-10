import threading
import serial
from src.drivers.sensor_base import SensorBase


class SerialTemperatureSensor(SensorBase):
    def __init__(self, name="218_temp", port="/dev/tty.usbserial-FTDZA5QJ"):
        super().__init__(name)
        self.port = port
        self.poll_hz = 2
        self.ser = None
        self._lock = threading.Lock()

    def connect(self):
        self.ser = serial.Serial(
            self.port,
            baudrate=9600,
            bytesize=serial.SEVENBITS,
            parity=serial.PARITY_ODD,
            stopbits=serial.STOPBITS_ONE,
            timeout=1,
        )

    def _query(self, cmd):
        self.ser.write((cmd + '\r\n').encode('ascii'))
        return self.ser.readline().decode('ascii', errors='ignore').strip()

    def read(self):
        with self._lock:
            return float(self._query("KRDG? 1"))

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
