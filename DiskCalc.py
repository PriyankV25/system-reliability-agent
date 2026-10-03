import psutil
import os
import time


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


while True:
    clear_screen()

    print("=" * 65)
    print("                 DISK UTILIZATION MONITOR")
    print("=" * 65)

    partitions = psutil.disk_partitions()

    for partition in partitions:
        try:
            usage = psutil.disk_usage(partition.mountpoint)

            total = usage.total / (1024 ** 3)
            used = usage.used / (1024 ** 3)
            free = usage.free / (1024 ** 3)
            percent = usage.percent

            print(f"\nDrive: {partition.mountpoint}")
            print(f"  Total Space : {total:8.2f} GB")
            print(f"  Used Space  : {used:8.2f} GB")
            print(f"  Free Space  : {free:8.2f} GB")
            print(f"  Utilization : {percent:8.1f}%")

        except (PermissionError, OSError):
            continue

    print("\n" + "=" * 65)
    print("Refreshing every 1 second... Press Ctrl+C to stop.")

    time.sleep(1)