# import asyncio
# from drivers.sensor_base import SensorBase
#
# class NiDaqAnalogInput(SensorBase):
#     def __init__(self, name="DAQ_AI0", channel="Dev1/ai0"):
#         super().__init__(name)
#         self.channel = channel
#         self.task = None
#
#     async def connect(self):
#         await asyncio.to_thread(self._open_task)
#
#     def _open_task(self):
#         import nidaqmx
#         self.task = nidaqmx.Task()
#         self.task.ai_channels.add_ai_voltage_chan(self.channel)
#
#     async def read(self):
#         if self.task is None:
#             raise RuntimeError(f"{self.name} not connected")
#         return await asyncio.to_thread(self.task.read)
#
#     def close(self):
#         if self.task is not None:
#             try:
#                 self.task.close()
#             finally:
#                 self.task = None