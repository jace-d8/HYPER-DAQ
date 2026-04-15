import asyncio
import nidaqmx
from nidaqmx.constants import AcquisitionType, TerminalConfiguration


class NiDaqAnalogInput:
    def __init__(self, config):
        self.config = config
        self.name = config.name
        self.task = None
        self.failed = False

    async def connect(self):
        try:
            self.task = nidaqmx.Task(new_task_name=self.name)

            self.task.ai_channels.add_ai_voltage_chan(
                physical_channel=self.config.physical_channel,
                min_val=self.config.min_val,
                max_val=self.config.max_val,
                terminal_config=getattr(
                    TerminalConfiguration,
                    self.config.terminal_config.upper(),
                    TerminalConfiguration.RSE,
                ),
            )

            sample_hz = getattr(self.config, "sample_hz", None)
            samples_per_read = getattr(self.config, "samples_per_read", 1)

            if sample_hz is not None:
                self.task.timing.cfg_samp_clk_timing(
                    rate=sample_hz,
                    sample_mode=AcquisitionType.CONTINUOUS,
                    samps_per_chan=max(samples_per_read * 10, 100),
                )

        except Exception:
            await self.close()
            raise

    async def read(self):
        if self.task is None:
            raise RuntimeError(f"{self.name} task is not initialized")

        try:
            samples_per_read = getattr(self.config, "samples_per_read", 1)
            reduction = getattr(self.config, "reduction", "mean")

            data = await asyncio.to_thread(
                self.task.read,
                number_of_samples_per_channel=samples_per_read,
            )

            if isinstance(data, list):
                if not data:
                    raise RuntimeError(f"{self.name} returned no samples")

                if reduction == "mean":
                    return sum(data) / len(data)

                if reduction == "first":
                    return data[0]

                if reduction == "last":
                    return data[-1]

                return sum(data) / len(data)

            return float(data)

        except Exception:
            self.failed = True
            raise

    async def close(self):
        if self.task is not None:
            try:
                await asyncio.to_thread(self.task.close)
            finally:
                self.task = None
