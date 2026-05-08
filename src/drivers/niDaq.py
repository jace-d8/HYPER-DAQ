# import asyncio
# from dataclasses import dataclass, field
#
# import nidaqmx
# import numpy as np
# from nidaqmx.constants import (
#     AcquisitionType,
#     CurrentShuntResistorLocation,
#     CurrentUnits,
#     ExcitationSource,
#     READ_ALL_AVAILABLE,
#     ResistanceConfiguration,
#     RTDType,
#     TemperatureUnits,
#     TerminalConfiguration,
#     ThermocoupleType,
# )
#
# from src.drivers.sensor_base import SensorBase
#
#
# @dataclass
# class NiDaqChannelConfig:
#     name: str
#     physical_channel: str
#
#     measurement_type: str = "voltage"
#     min_val: float = -10.0
#     max_val: float = 10.0
#
#     terminal_config: str = "DEFAULT"
#
#     thermocouple_type: str = "K"
#
#     rtd_type: str = "PT_3851"
#     resistance_config: str = "3_WIRE"
#     current_excit_source: str = "INTERNAL"
#     current_excit_val: float = 0.001
#     r_0: float = 100.0
#
#     shunt_resistor_loc: str = "LET_DRIVER_CHOOSE"
#     ext_shunt_resistor_val: float = 249.0
#
#
# def _terminal_config(cfg: NiDaqChannelConfig):
#     return {
#         "DEFAULT": TerminalConfiguration.DEFAULT,
#         "RSE":     TerminalConfiguration.RSE,
#         "NRSE":    TerminalConfiguration.NRSE,
#         "DIFF":    TerminalConfiguration.DIFF,
#     }.get(cfg.terminal_config.upper(), TerminalConfiguration.DEFAULT)
#
#
# def _add_channel(task: nidaqmx.Task, cfg: NiDaqChannelConfig):
#     mtype = cfg.measurement_type.lower()
#
#     if mtype == "voltage":
#         task.ai_channels.add_ai_voltage_chan(
#             physical_channel=cfg.physical_channel,
#             min_val=cfg.min_val,
#             max_val=cfg.max_val,
#             terminal_config=_terminal_config(cfg),
#         )
#
#     elif mtype == "current":
#         task.ai_channels.add_ai_current_chan(
#             physical_channel=cfg.physical_channel,
#             name_to_assign_to_channel=cfg.name,
#             terminal_config=_terminal_config(cfg),
#             min_val=cfg.min_val,
#             max_val=cfg.max_val,
#             units=CurrentUnits.AMPS,
#             shunt_resistor_loc={
#                 "LET_DRIVER_CHOOSE": CurrentShuntResistorLocation.LET_DRIVER_CHOOSE,
#                 "INTERNAL":          CurrentShuntResistorLocation.INTERNAL,
#                 "EXTERNAL":          CurrentShuntResistorLocation.EXTERNAL,
#             }[cfg.shunt_resistor_loc.upper()],
#             ext_shunt_resistor_val=cfg.ext_shunt_resistor_val,
#         )
#
#     elif mtype == "thermocouple":
#         task.ai_channels.add_ai_thrmcpl_chan(
#             physical_channel=cfg.physical_channel,
#             min_val=cfg.min_val,
#             max_val=cfg.max_val,
#             units=TemperatureUnits.DEG_C,
#             thermocouple_type=getattr(ThermocoupleType, cfg.thermocouple_type.upper()),
#         )
#
#     elif mtype == "rtd":
#         task.ai_channels.add_ai_rtd_chan(
#             physical_channel=cfg.physical_channel,
#             min_val=cfg.min_val,
#             max_val=cfg.max_val,
#             units=TemperatureUnits.DEG_C,
#             rtd_type=getattr(RTDType, cfg.rtd_type.upper()),
#             resistance_config={
#                 "2_WIRE": ResistanceConfiguration.TWO_WIRE,
#                 "3_WIRE": ResistanceConfiguration.THREE_WIRE,
#                 "4_WIRE": ResistanceConfiguration.FOUR_WIRE,
#             }[cfg.resistance_config.upper()],
#             current_excit_source=getattr(ExcitationSource, cfg.current_excit_source.upper()),
#             current_excit_val=cfg.current_excit_val,
#             r_0=cfg.r_0,
#         )
#
#     else:
#         raise ValueError(f"Unsupported measurement type: {mtype}")
#
#
# class NiDaqTask(SensorBase):
#     """
#     All NI-DAQ analog-input channels on one device share a single task and
#     hardware clock.  Returns a dict {channel_name: float} from read().
#
#     Usage in controller:
#         NiDaqTask(
#             name="NI_AI",
#             channels=[
#                 NiDaqChannelConfig("PT1", "Dev1/ai0", measurement_type="voltage"),
#                 NiDaqChannelConfig("PT2", "Dev1/ai1", measurement_type="voltage"),
#             ],
#             sample_hz=15,
#         )
#     """
#
#     def __init__(self, name: str, channels: list[NiDaqChannelConfig], sample_hz: float = 15):
#         super().__init__(name)
#         self.channels = channels
#         self.sample_hz = sample_hz
#         self._task: nidaqmx.Task | None = None
#         self.failed = False
#
#     def _setup(self):
#         """Synchronous setup — runs inside asyncio.to_thread so it won't block the loop."""
#         self._task = nidaqmx.Task()
#         for cfg in self.channels:
#             _add_channel(self._task, cfg)
#         self._task.timing.cfg_samp_clk_timing(
#             rate=self.sample_hz,
#             sample_mode=AcquisitionType.CONTINUOUS,
#             samps_per_chan=int(self.sample_hz * 10),  # 10-second ring buffer
#         )
#         self._task.start()
#
#     async def connect(self):
#         await asyncio.to_thread(self._setup)
#
#     def _read_sync(self) -> dict[str, float]:
#         """
#         Drain all accumulated samples and return the mean per channel.
#         If the buffer is momentarily empty, wait up to one sample period
#         and try once more before giving up gracefully.
#         """
#         raw = self._task.read(number_of_samples_per_channel=READ_ALL_AVAILABLE, timeout=0.0)
#         arr = np.asarray(raw, dtype=float)
#         if arr.ndim == 1:
#             arr = arr.reshape(1, -1)  # single channel comes back as 1-D
#
#         if arr.shape[1] == 0:
#             # buffer was empty — wait one sample period and retry once
#             import time
#             time.sleep(1.0 / self.sample_hz)
#             raw = self._task.read(number_of_samples_per_channel=READ_ALL_AVAILABLE, timeout=0.0)
#             arr = np.asarray(raw, dtype=float)
#             if arr.ndim == 1:
#                 arr = arr.reshape(1, -1)
#
#         if arr.shape[1] == 0:
#             return {}  # still nothing — caller treats as a no-op, not a failure
#
#         return {cfg.name: float(arr[i].mean()) for i, cfg in enumerate(self.channels)}
#
#     async def read(self) -> dict[str, float]:
#         if self._task is None:
#             raise RuntimeError("NiDaqTask not connected")
#         return await asyncio.to_thread(self._read_sync)
#
#     def close(self):
#         if self._task:
#             try:
#                 self._task.close()
#             finally:
#                 self._task = None
