from lakeshore import Model336
from src.drivers.sensor_base import SensorBase


class TemperatureSensor(SensorBase):
    def __init__(self, name="336_1", channels=None):
        super().__init__(name)
        if not channels:
            raise ValueError("TemperatureSensor requires a non-empty channels dict")
        self.channels = channels
        self.poll_hz = 10
        self.instrument = None

    def connect(self):
        self.instrument = Model336()

    def read(self):
        return {
            sensor_name: self.instrument.get_kelvin_reading(channel)
            for sensor_name, channel in self.channels.items()
        }
