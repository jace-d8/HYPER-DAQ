from abc import ABC, abstractmethod


class SensorBase(ABC):
    def __init__(self, name):
        self.name = name

    @abstractmethod
    async def read(self):
        pass

    def close(self):
        pass
