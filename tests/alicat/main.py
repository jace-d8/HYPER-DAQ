# import asyncio
# from typing import Any, Dict, Optional, Union
#
# from alicat import FlowController
#
#
# class AlicatController:
#     """
#     Port examples:
#         "/dev/ttyUSB0"
#         "COM3"
#
#     Unit examples:
#         "A"
#         "B"
#     """
#
#     def __init__(self, port: str, unit: str = "A") -> None:
#         self.port = port
#         self.unit = unit
#         self._fc: Optional[FlowController] = None
#
#     async def connect(self) -> None:
#         if self._fc is not None:
#             return
#
#         # Some docs/examples still show `address=...`, while newer notes say
#         # this was renamed to `unit=...`. Try unit first, then fall back.
#         try:
#             self._fc = FlowController(self.port, unit=self.unit)
#         except TypeError:
#             self._fc = FlowController(self.port, address=self.unit)
#
#         # Open underlying connection if the object supports async enter.
#         if hasattr(self._fc, "__aenter__"):
#             await self._fc.__aenter__()
#
#     async def close(self) -> None:
#         if self._fc is None:
#             return
#
#         try:
#             if hasattr(self._fc, "__aexit__"):
#                 await self._fc.__aexit__(None, None, None)
#             elif hasattr(self._fc, "close"):
#                 await self._fc.close()
#         finally:
#             self._fc = None
#
#     async def __aenter__(self) -> "AlicatController":
#         await self.connect()
#         return self
#
#     async def __aexit__(self, exc_type, exc, tb) -> None:
#         await self.close()
#
#     def _require_connection(self) -> FlowController:
#         if self._fc is None:
#             raise RuntimeError("Alicat is not connected. Call connect() first.")
#         return self._fc
#
#     async def read(self) -> Dict[str, Any]:
#         """
#         Read current controller state.
#
#         Expected fields commonly include:
#         setpoint, control_point, gas, mass_flow, pressure,
#         temperature, total_flow, volumetric_flow
#         """
#         fc = self._require_connection()
#         return await fc.get()
#
#     async def set_flow_rate(self, value: Union[int, float]) -> Dict[str, Any]:
#         fc = self._require_connection()
#         await fc.set_flow_rate(float(value))
#         return await fc.get()
#
#     async def set_pressure(self, value: Union[int, float]) -> Dict[str, Any]:
#         fc = self._require_connection()
#         await fc.set_pressure(float(value))
#         return await fc.get()
#
#     async def set_gas(self, gas: Union[str, int]) -> Dict[str, Any]:
#         fc = self._require_connection()
#         await fc.set_gas(gas)
#         return await fc.get()
#
#     async def get_pid(self) -> Dict[str, Any]:
#         fc = self._require_connection()
#         return await fc.get_pid()
#
#     async def set_pid(
#         self,
#         p: Union[int, float],
#         i: Union[int, float],
#         d: Union[int, float],
#         loop_type: str = "PD2I",
#     ) -> Dict[str, Any]:
#         fc = self._require_connection()
#         await fc.set_pid(p=p, i=i, d=d, loop_type=loop_type)
#         return await fc.get_pid()
#
#     async def lock(self) -> None:
#         fc = self._require_connection()
#         await fc.lock()
#
#     async def unlock(self) -> None:
#         fc = self._require_connection()
#         await fc.unlock()
#
#     async def hold(self) -> None:
#         fc = self._require_connection()
#         await fc.hold()
#
#     async def cancel_hold(self) -> None:
#         fc = self._require_connection()
#         await fc.cancel_hold()
#
#     async def tare_pressure(self) -> None:
#         fc = self._require_connection()
#         await fc.tare_pressure()
#
#     async def tare_volumetric(self) -> None:
#         fc = self._require_connection()
#         await fc.tare_volumetric()
#
#     async def reset_totalizer(self) -> None:
#         fc = self._require_connection()
#         await fc.reset_totalizer()
#
#     async def create_mix(
#         self,
#         mix_no: int,
#         name: str,
#         gases: Dict[str, Union[int, float]],
#     ) -> None:
#         fc = self._require_connection()
#         await fc.create_mix(mix_no=mix_no, name=name, gases=gases)
#
#     async def delete_mix(self, mix_no: int) -> None:
#         fc = self._require_connection()
#         await fc.delete_mix(mix_no)
#
#
# async def main() -> None:
#     async with AlicatController(port="/dev/ttyUSB0", unit="A") as alicat:
#         state = await alicat.read()
#         print("Initial state:", state)
#
#         await alicat.set_flow_rate(1.0)
#         print("After flow set:", await alicat.read())
#
#         await alicat.set_gas("N2")
#         print("After gas change:", await alicat.read())
#
#         pid = await alicat.get_pid()
#         print("PID:", pid)
#
#
# if __name__ == "__main__":
#     asyncio.run(main())


import asyncio
from AlicatTest import Alicat

async def main():
    alicat = Alicat(port="/dev/cu.usbserial-FT2NAE3B", unit="A")

    print(await alicat.read())

    # await alicat.set_flow_rate(1.0)
    #await alicat.set_gas("N2")

    #print(await alicat.read())


asyncio.run(main())