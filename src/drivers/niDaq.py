# import nidaqmx
#
# from nidaqmx.constants import (
#     TerminalConfiguration,   # RSE, NRSE, Differential wiring modes
#     ThermocoupleType,       # K, J, T, etc
#     TemperatureUnits,       # °C, °F, etc
#     RTDType,                # PT100 variants
#     ResistanceConfiguration,# 2-wire, 3-wire, 4-wire
#     ExcitationSource,       # internal vs external current excitation
#     AcquisitionType,        # finite vs continuous sampling
# )
#
# from dataclasses import dataclass
#
#
# # configuration container.
# @dataclass
# class NiDaqChannelConfig:
#     name: str                      # Sensor name e.g. "TS1"
#     physical_channel: str          # Port name e.g. "Dev1/ai0"
#
#     measurement_type: str = "voltage"
#     # decides which DAQmx function to call
#     # "voltage", "thermocouple", "rtd"
#
#     min_val: float = -10.0         # expected signal range
#     max_val: float = 10.0
#
#     terminal_config: str = "DEFAULT"
#     # wiring mode: RSE, NRSE, DIFF
#
#     units: str = "volts"           # mainly for temp channels
#
#     sample_hz: float | None = None
#     # if set, enables hardware timed sampling
#     # if None, uses on-demand reads
#
#     # Thermocouple specific settings
#     thermocouple_type: str = "K"
#     cjc_source: str = "BUILT_IN"
#
#     # RTD specific settings
#     rtd_type: str = "PT_3851"
#     resistance_config: str = "3_WIRE"
#     current_excit_source: str = "INTERNAL"
#     current_excit_val: float = 0.001
#     r_0: float = 100.0
#
# class NiDaqAnalogInput:
#     def __init__(self, config: NiDaqChannelConfig):
#         self.config = config
#         self.name = config.name     # important for CSV + controller
#         self.task = None            # will hold DAQmx Task object
#         self.failed = False         # controller uses this flag
#
#     # Convert string → NI enum
#     def _terminal_config(self):
#         return {
#             "DEFAULT": TerminalConfiguration.DEFAULT,
#             "RSE": TerminalConfiguration.RSE,
#             "NRSE": TerminalConfiguration.NRSE,
#             "DIFF": TerminalConfiguration.DIFF,
#         }.get(self.config.terminal_config.upper(), TerminalConfiguration.DEFAULT)
#
#     # Convert thermocouple string → enum
#     def _tc_type(self):
#         return getattr(ThermocoupleType, self.config.thermocouple_type.upper())
#
#     # Currently hardcoded to Celsius
#     def _temp_units(self):
#         return getattr(TemperatureUnits, "DEG_C")
#
#     # RTD type mapping
#     def _rtd_type(self):
#         return getattr(RTDType, self.config.rtd_type.upper())
#
#     # Convert "3_WIRE" → enum
#     def _res_config(self):
#         mapping = {
#             "2_WIRE": ResistanceConfiguration.TWO_WIRE,
#             "3_WIRE": ResistanceConfiguration.THREE_WIRE,
#             "4_WIRE": ResistanceConfiguration.FOUR_WIRE,
#         }
#         return mapping[self.config.resistance_config.upper()]
#
#     # Internal vs external excitation current
#     def _excitation_source(self):
#         return getattr(ExcitationSource, self.config.current_excit_source.upper())
#
#     # This runs once during initialization
#     async def connect(self):
#         # Create a DAQmx task
#         self.task = nidaqmx.Task()
#
#         # Decide what type of measurement to create
#         mtype = self.config.measurement_type.lower()
#
#         # VOLTAGE INPUT
#         if mtype == "voltage":
#             self.task.ai_channels.add_ai_voltage_chan(
#                 physical_channel=self.config.physical_channel,
#                 min_val=self.config.min_val,
#                 max_val=self.config.max_val,
#                 terminal_config=self._terminal_config(),
#             )
#
#         # THERMOCOUPLE INPUT
#         elif mtype == "thermocouple":
#             self.task.ai_channels.add_ai_thrmcpl_chan(
#                 physical_channel=self.config.physical_channel,
#                 min_val=self.config.min_val,
#                 max_val=self.config.max_val,
#                 units=self._temp_units(),
#                 thermocouple_type=self._tc_type(),
#             )
#
#         # Resistance Temp detector INPUT
#         elif mtype == "rtd":
#             self.task.ai_channels.add_ai_rtd_chan(
#                 physical_channel=self.config.physical_channel,
#                 min_val=self.config.min_val,
#                 max_val=self.config.max_val,
#                 units=self._temp_units(),
#                 rtd_type=self._rtd_type(),
#                 resistance_config=self._res_config(),
#                 current_excit_source=self._excitation_source(),
#                 current_excit_val=self.config.current_excit_val,
#                 r_0=self.config.r_0,
#             )
#
#         else:
#             raise ValueError(f"Unsupported measurement type: {mtype}")
#
#         # OPTIONAL: hardware timing
#         # If you set sample_hz, DAQ runs its own clock
#         if self.config.sample_hz:
#             self.task.timing.cfg_samp_clk_timing(
#                 rate=self.config.sample_hz,
#                 sample_mode=AcquisitionType.CONTINUOUS,
#             )
#
#     # Called repeatedly by controller loop
#     async def read(self):
#         if self.task is None:
#             raise RuntimeError("DAQ task not initialized")
#
#         # This reads one sample (or latest sample if buffered)
#         value = self.task.read()
#
#         # Ensure consistent float output
#         return float(value)
#
#     # Cleanup when program exits
#     def close(self):
#         if self.task:
#             try:
#                 self.task.close()   # releases hardware resources
#             finally:
#                 self.task = None