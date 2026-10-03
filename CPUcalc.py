# import psutil

# while True:
#     # Total CPU utilization
#     total_cpu = psutil.cpu_percent(interval=1)

#     # Per-core CPU utilization
#     core_usage = psutil.cpu_percent(interval=None, percpu=True)

#     print(
#         f"\rTotal CPU: {total_cpu:5.1f}% | "
#         + " | ".join(
#             f"Core {i + 1}: {usage:5.1f}%"
#             for i, usage in enumerate(core_usage)
#         ),
#         end="",
#         flush=True
#     )



import psutil
import time
import os


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


while True:
    # Get total CPU utilization
    total_cpu = psutil.cpu_percent(interval=1)

    # Get utilization for each CPU core
    core_usage = psutil.cpu_percent(interval=None, percpu=True)

    clear_screen()

    print("=" * 50)
    print("           CPU UTILIZATION MONITOR")
    print("=" * 50)

    print(f"\nTotal CPU Utilization: {total_cpu:5.1f}%\n")

    # Display cores in pairs
    for i in range(0, len(core_usage), 2):
        left = f"Core {i + 1}: {core_usage[i]:5.1f}%"

        if i + 1 < len(core_usage):
            right = f"Core {i + 2}: {core_usage[i + 1]:5.1f}%"
            print(f"{left:<25}{right}")
        else:
            print(left)

    print("\n" + "=" * 50)
    print("Refreshing every 1 second... Press Ctrl+C to stop.")