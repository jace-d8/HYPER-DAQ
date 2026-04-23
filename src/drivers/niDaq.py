# import asyncio
# from dataclasses import dataclass
# from datetime import datetime, timedelta
#
# import nidaqmx
# import numpy as np
# from nidaqmx.constants import (
#     AcquisitionType,
#     CurrentShuntResistorLocation,
#     CurrentUnits,
#     ExcitationSource,
#     ResistanceConfiguration,
#     RTDType,
#     TemperatureUnits,
#     TerminalConfiguration,
#     ThermocoupleType,
# )
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
#     units: str = "volts"
#
#     sample_hz: float | None = None
#     samples_per_read: int = 50
#     reduction: str = "mean"
#
#     thermocouple_type: str = "K"
#     cjc_source: str = "BUILT_IN"
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
# class NiDaqAnalogInput:
#     def __init__(self, config: NiDaqChannelConfig):
#         self.config = config
#         self.name = config.name
#         self.task = None
#         self.failed = False
#
#     def _terminal_config(self):
#         return {
#             "DEFAULT": TerminalConfiguration.DEFAULT,
#             "RSE": TerminalConfiguration.RSE,
#             "NRSE": TerminalConfiguration.NRSE,
#             "DIFF": TerminalConfiguration.DIFF,
#         }.get(self.config.terminal_config.upper(), TerminalConfiguration.DEFAULT)
#
#     def _tc_type(self):
#         return getattr(ThermocoupleType, self.config.thermocouple_type.upper())
#
#     def _temp_units(self):
#         return TemperatureUnits.DEG_C
#
#     def _rtd_type(self):
#         return getattr(RTDType, self.config.rtd_type.upper())
#
#     def _res_config(self):
#         return {
#             "2_WIRE": ResistanceConfiguration.TWO_WIRE,
#             "3_WIRE": ResistanceConfiguration.THREE_WIRE,
#             "4_WIRE": ResistanceConfiguration.FOUR_WIRE,
#         }[self.config.resistance_config.upper()]
#
#     def _excitation_source(self):
#         return getattr(ExcitationSource, self.config.current_excit_source.upper())
#
#     def _current_units(self):
#         return CurrentUnits.AMPS
#
#     def _shunt_resistor_loc(self):
#         return {
#             "LET_DRIVER_CHOOSE": CurrentShuntResistorLocation.LET_DRIVER_CHOOSE,
#             "INTERNAL": CurrentShuntResistorLocation.INTERNAL,
#             "EXTERNAL": CurrentShuntResistorLocation.EXTERNAL,
#         }[self.config.shunt_resistor_loc.upper()]
#
#     async def connect(self):
#         try:
#             self.task = nidaqmx.Task()
#             mtype = self.config.measurement_type.lower()
#
#             if mtype == "voltage":
#                 self.task.ai_channels.add_ai_voltage_chan(
#                     physical_channel=self.config.physical_channel,
#                     min_val=self.config.min_val,
#                     max_val=self.config.max_val,
#                     terminal_config=self._terminal_config(),
#                 )
#
#             elif mtype == "current":
#                 self.task.ai_channels.add_ai_current_chan(
#                     physical_channel=self.config.physical_channel,
#                     name_to_assign_to_channel=self.config.name,
#                     terminal_config=self._terminal_config(),
#                     min_val=self.config.min_val,
#                     max_val=self.config.max_val,
#                     units=self._current_units(),
#                     shunt_resistor_loc=self._shunt_resistor_loc(),
#                     ext_shunt_resistor_val=self.config.ext_shunt_resistor_val,
#                 )
#
#             elif mtype == "thermocouple":
#                 self.task.ai_channels.add_ai_thrmcpl_chan(
#                     physical_channel=self.config.physical_channel,
#                     min_val=self.config.min_val,
#                     max_val=self.config.max_val,
#                     units=self._temp_units(),
#                     thermocouple_type=self._tc_type(),
#                 )
#
#             elif mtype == "rtd":
#                 self.task.ai_channels.add_ai_rtd_chan(
#                     physical_channel=self.config.physical_channel,
#                     min_val=self.config.min_val,
#                     max_val=self.config.max_val,
#                     units=self._temp_units(),
#                     rtd_type=self._rtd_type(),
#                     resistance_config=self._res_config(),
#                     current_excit_source=self._excitation_source(),
#                     current_excit_val=self.config.current_excit_val,
#                     r_0=self.config.r_0,
#                 )
#
#             else:
#                 raise ValueError(f"Unsupported measurement type: {mtype}")
#
#             if self.config.sample_hz:
#                 self.task.timing.cfg_samp_clk_timing(
#                     rate=self.config.sample_hz,
#                     sample_mode=AcquisitionType.CONTINUOUS,
#                     samps_per_chan=max(self.config.samples_per_read * 10, 100),
#                 )
#
#         except Exception:
#             self.failed = True
#             self.close()
#             raise
#
#     async def read(self):
#         if self.task is None:
#             self.failed = True
#             raise RuntimeError("DAQ task not initialized")
#
#         if not self.config.sample_hz:
#             self.failed = True
#             raise RuntimeError("sample_hz must be set for timestamped batch reads")
#
#         try:
#             samples = await asyncio.to_thread(
#                 self.task.read,
#                 number_of_samples_per_channel=self.config.samples_per_read,
#             )
#         except Exception:
#             self.failed = True
#             raise
#
#         values = np.asarray(samples, dtype=float).reshape(-1)
#
#         if values.size == 0:
#             self.failed = True
#             raise RuntimeError("DAQ returned no samples")
#
#         t_end = datetime.now()
#         dt_seconds = 1.0 / float(self.config.sample_hz)
#         n = int(values.size)
#
#         timestamps = [
#             (t_end - timedelta(seconds=(n - 1 - i) * dt_seconds)).isoformat(timespec="milliseconds")
#             for i in range(n)
#         ]
#
#         return {
#             "sensor": self.name,
#             "kind": "timeseries",
#             "sample_hz": float(self.config.sample_hz),
#             "timestamps": timestamps,
#             "values": values.tolist(),
#         }
#
#     def close(self):
#         if self.task is not None:
#             try:
#                 self.task.close()
#             finally:
#                 self.task = None