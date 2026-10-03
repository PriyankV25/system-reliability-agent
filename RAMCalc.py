import psutil
import time

while True:
    memory = psutil.virtual_memory()

    print(
        f"\rRAM Usage: {memory.percent:5.1f}% | "
        f"Used: {memory.used / (1024**3):6.2f} GB | "
        f"Available: {memory.available / (1024**3):6.2f} GB",
        end="",
        flush=True
    )

    time.sleep(1)