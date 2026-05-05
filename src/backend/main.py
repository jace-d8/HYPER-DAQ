import asyncio
import logging
from datetime import datetime
from pathlib import Path

from controller import SensorControllerAsync
from csv_buffer import CsvBuffer
from src.frontend.config import BUFFER_MAX_ROWS, SAMPLE_HZ

DATA_DIR = Path(__file__).parent.parent.parent / "data"

log_filename = f"run_{datetime.now():%Y-%m-%d_%H-%M-%S}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


async def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    csv_buffer = CsvBuffer(
        data_csv="sensor_data.csv",
        buffer_csv="sensor_buffer.csv",
        max_rows=BUFFER_MAX_ROWS,
        data_dir=DATA_DIR,
        logging_state_file=DATA_DIR / "logging_state.json",
    )

    controller = SensorControllerAsync(
        csv_buffer=csv_buffer,
        sample_hz=SAMPLE_HZ,
    )

    try:
        await controller.run()
    finally:
        await controller.close()
        csv_buffer.close()


if __name__ == "__main__":
    asyncio.run(main())
