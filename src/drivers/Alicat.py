import asyncio

from drivers.sensor_base import SensorBase
from alicat import FlowController

# flow controller or flow monitor
class Alicat(SensorBase):
    def __init__(self, name):
        super().__init__(name)
        self.flowcontroller = FlowController()
        # # force connection test
        # try:
        #     loop = asyncio.get_event_loop()
        #     if loop.is_running():
        #         # schedule test in running loop and wait
        #         future = asyncio.run_coroutine_threadsafe(
        #             self.flowcontroller.get(), loop
        #         )
        #         future.result(timeout=2)
        #     else:
        #         loop.run_until_complete(self.flowcontroller.get())
        # except Exception as e:
        #     raise RuntimeError(f"Alicat connection failed {e}")

    async def read(self):
        return await self.flowcontroller.get()