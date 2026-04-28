import asyncio
import logging
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from controller import SensorControllerAsync
from csv_buffer import CsvBuffer


log_filename = f"run_{datetime.now():%Y-%m-%d_%H-%M-%S}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class LoggingRequest(BaseModel):
    enabled: bool


app = FastAPI()

csv_buffer = CsvBuffer(
    data_csv="sensor_data.csv",
    buffer_csv="sensor_buffer.csv",
    max_rows=5000,
)

controller = SensorControllerAsync(
    csv_buffer=csv_buffer,
    sample_hz=10,
)


@app.post("/logging")
async def set_logging_state(request: LoggingRequest):
    controller.set_logging_enabled(request.enabled)
    return {"enabled": request.enabled}


async def run_controller():
    try:
        await controller.run()
    finally:
        await controller.shutdown()


@app.on_event("startup")
async def startup():
    asyncio.create_task(run_controller())


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)