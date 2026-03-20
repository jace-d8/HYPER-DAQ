import asyncio
from datetime import datetime
import logging
from controller import SensorController
from controllerSep import SensorControllerAsync

log_filename = f"run_{datetime.now():%Y-%m-%d_%H:%M:%S}.log"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


async def main():
    # controller = SensorController(sample_hz=2)
    controller = SensorControllerAsync(sample_hz=6)
    await controller.run()


if __name__ == "__main__":
    asyncio.run(main())

# gui -> controller -> driver files
# analysis goes where


# main
#    drivers
#    controller
#    gui window
#    thread
#    run gui loop



