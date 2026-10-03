import os
import psutil
import socket
import subprocess
import time
from abc import ABC, abstractmethod


class current(ABC):
    @staticmethod
    @abstractmethod
    def clear_screen():
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def bytes_to_mb(value):
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def get_connected_interfaces():
        raise NotImplementedError

    @abstractmethod
    def run(self):
        raise NotImplementedError


class NetworkMonitor(current):
    @staticmethod
    def clear_screen():
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "cls"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.run(
                ["clear"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    @staticmethod
    def bytes_to_mb(value):
        return value / (1024 * 1024)

    @staticmethod
    def get_connected_interfaces():
        """
        Return network interfaces that are currently up
        and have an IPv4 address.
        """
        connected = []

        interface_stats = psutil.net_if_stats()
        interface_addresses = psutil.net_if_addrs()

        for interface, stats in interface_stats.items():
            if not stats.isup:
                continue

            if interface.lower() in ["loopback", "lo"]:
                continue

            addresses = interface_addresses.get(interface, [])
            for address in addresses:
                if address.family == socket.AF_INET:
                    connected.append(interface)
                    break

        return connected

    def run(self):
        previous = psutil.net_io_counters(pernic=True)

        while True:
            time.sleep(1)

            current_stats = psutil.net_io_counters(pernic=True)
            self.clear_screen()

            print("=" * 75, flush=True)
            print("                    NETWORK MONITOR", flush=True)
            print("=" * 75, flush=True)

            connected_interfaces = self.get_connected_interfaces()

            if not connected_interfaces:
                print("\nNo active network connection detected.", flush=True)
            else:
                print("\nConnected Network(s):", flush=True)

                for interface in connected_interfaces:
                    print(f"  [CONNECTED] {interface}", flush=True)

                print("\n" + "-" * 75, flush=True)

                total_download = 0.0
                total_upload = 0.0

                for interface in connected_interfaces:
                    if interface not in current_stats or interface not in previous:
                        continue

                    stats = current_stats[interface]
                    old_stats = previous[interface]

                    download_bytes = stats.bytes_recv - old_stats.bytes_recv
                    upload_bytes = stats.bytes_sent - old_stats.bytes_sent

                    download_speed = self.bytes_to_mb(download_bytes)
                    upload_speed = self.bytes_to_mb(upload_bytes)

                    total_download += download_speed
                    total_upload += upload_speed

                    print(f"\nInterface: {interface}  [CONNECTED]", flush=True)
                    print(f"  Download Speed : {download_speed:8.2f} MB/s", flush=True)
                    print(f"  Upload Speed   : {upload_speed:8.2f} MB/s", flush=True)
                    print(
                        f"  Total Received : {self.bytes_to_mb(stats.bytes_recv):8.2f} MB",
                        flush=True,
                    )
                    print(
                        f"  Total Sent     : {self.bytes_to_mb(stats.bytes_sent):8.2f} MB",
                        flush=True,
                    )

                print("\n" + "-" * 75, flush=True)
                print(f"Total Download : {total_download:8.2f} MB/s", flush=True)
                print(f"Total Upload   : {total_upload:8.2f} MB/s", flush=True)

            print("\n" + "=" * 75, flush=True)
            print("Refreshing every 1 second... Press Ctrl+C to stop.", flush=True)

            previous = current_stats


if __name__ == "__main__":
    NetworkMonitor().run()