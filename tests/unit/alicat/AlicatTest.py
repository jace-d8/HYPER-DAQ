import asyncio
from alicat import FlowController

class Alicat:
    def __init__(self, port, unit="A"):
        self.port = port
        self.unit = unit

    async def read(self):
        async with FlowController(self.port, unit=self.unit) as fc:
            return await fc.get()

    async def set_flow_rate(self, value):
        async with FlowController(self.port, unit=self.unit) as fc:
            await fc.set_flow_rate(value)

    async def set_pressure(self, value):
        async with FlowController(self.port, unit=self.unit) as fc:
            await fc.set_pressure(value)

    async def set_gas(self, gas):
        async with FlowController(self.port, unit=self.unit) as fc:
            await fc.set_gas(gas)


# class Alicat:
#     def __init__(self, port, unit="A"):
#         self.fc = FlowController(port, unit=unit)
#
#     async def read(self):
#         return await self.fc.get()
#
#     async def set_flow_rate(self, value):
#         await self.fc.set_flow_rate(value)
#
#     async def set_pressure(self, value):
#         await self.fc.set_pressure(value)
#
#     async def set_gas(self, gas):
#         await self.fc.set_gas(gas)