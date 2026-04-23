import asyncio
import logging
from datetime import datetime

from controller import SensorControllerAsync
from csv_buffer import CsvBuffer

log_filename = f"run_{datetime.now():%Y-%m-%d_%H-%M-%S}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


async def main():
    csv_buffer = CsvBuffer(
        data_csv="sensor_data.csv",
        buffer_csv="sensor_buffer.csv",
        max_rows=5000,
    )

    controller = SensorControllerAsync(
        csv_buffer=csv_buffer,
        sample_hz=10,
    )

    try:
        await controller.run()
    finally:
        await controller.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass