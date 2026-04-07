import asyncio
from niDaq import NiDaqAnalogInput


async def main():
    # Create instance
    sensor = NiDaqAnalogInput(name="TestAI", channel="Dev1/ai0")

    print("Connecting to NI-DAQ...")
    await sensor.connect()
    print("Connected.")

    try:
        for i in range(10):  # read 10 samples
            value = await sensor.read()
            print(f"Reading {i+1}: {value}")
            await asyncio.sleep(1)  # 1 Hz

    except Exception as e:
        print(f"Error during read: {e}")

    finally:
        print("Closing task...")
        sensor.close()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
