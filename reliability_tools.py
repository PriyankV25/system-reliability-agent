from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class ReliabilityTools:
    """Read-only tools backed by the existing local SQLite metrics database."""

    def __init__(self, db):
        self.db = db

    def get_current_metrics(self) -> dict[str, Any]:
        row = self.db.latest_snapshot()
        if not row:
            return {"available": False, "message": "No metrics have been collected yet."}
        sid, timestamp, cpu, ram, ram_used, ram_available, cache_mb, critical, error, warning = row
        disks = self._disks(sid)
        network = self._network(sid)
        cores = [
            {"core": int(c), "usage_percent": round(float(u), 2)}
            for c, u in self.db.latest_cpu_cores(sid)
        ]
        caches = [
            {"path": p, "size_mb": round(float(s), 2)}
            for p, s in self.db.latest_cache_paths(sid)
        ]
        return {
            "available": True,
            "timestamp": timestamp,
            "cpu_percent": round(float(cpu), 2),
            "ram_percent": round(float(ram), 2),
            "ram_used_gb": round(float(ram_used), 2),
            "ram_available_gb": round(float(ram_available), 2),
            "cache_total_mb": round(float(cache_mb), 2),
            "events": {"critical": int(critical), "error": int(error), "warning": int(warning)},
            "cpu_cores": cores,
            "disks": disks,
            "network": network,
        }

    def get_metric_history(self, hours: int = 24) -> dict[str, Any]:
        hours = max(1, min(int(hours), 168))
        rows = self.db.history(hours)
        return {
            "hours": hours,
            "snapshots": [
                {
                    "timestamp": r[0], "cpu_percent": round(float(r[1]), 2),
                    "ram_percent": round(float(r[2]), 2), "cache_total_mb": round(float(r[3]), 2),
                    "critical": int(r[4]), "error": int(r[5]), "warning": int(r[6]),
                }
                for r in rows
            ],
        }

    def get_disk_metrics(self) -> dict[str, Any]:
        row = self.db.latest_snapshot()
        return {"disks": self._disks(row[0]) if row else []}

    def get_network_metrics(self) -> dict[str, Any]:
        row = self.db.latest_snapshot()
        return {"network": self._network(row[0]) if row else []}

    def get_cache_details(self) -> dict[str, Any]:
        row = self.db.latest_snapshot()
        if not row:
            return {"paths": [], "total_mb": 0}
        paths = [{"path": p, "size_mb": round(float(s), 2)}
                 for p, s in self.db.latest_cache_paths(row[0])]
        return {"paths": paths, "total_mb": round(sum(p["size_mb"] for p in paths), 2)}

    def get_events(self, hours: int = 24) -> dict[str, Any]:
        history = self.get_metric_history(hours)
        totals = {"critical": 0, "error": 0, "warning": 0}
        for s in history["snapshots"]:
            for key in totals:
                totals[key] += s[key]
        return {"hours": hours, "totals": totals}

    def analyze_trends(self, hours: int = 24) -> dict[str, Any]:
        snapshots = self.get_metric_history(hours)["snapshots"]
        if not snapshots:
            return {"available": False, "message": "No history available."}

        def avg(key):
            return sum(s[key] for s in snapshots) / len(snapshots)

        def maxv(key):
            return max(s[key] for s in snapshots)

        first = snapshots[0]
        last = snapshots[-1]
        cpu_delta = last["cpu_percent"] - first["cpu_percent"]
        ram_delta = last["ram_percent"] - first["ram_percent"]
        cache_delta = last["cache_total_mb"] - first["cache_total_mb"]
        return {
            "available": True,
            "samples": len(snapshots),
            "cpu": {"average": round(avg("cpu_percent"), 2), "maximum": round(maxv("cpu_percent"), 2), "delta_first_to_last": round(cpu_delta, 2)},
            "ram": {"average": round(avg("ram_percent"), 2), "maximum": round(maxv("ram_percent"), 2), "delta_first_to_last": round(ram_delta, 2)},
            "cache": {"average_mb": round(avg("cache_total_mb"), 2), "maximum_mb": round(maxv("cache_total_mb"), 2), "delta_first_to_last_mb": round(cache_delta, 2)},
            "event_totals": self.get_events(hours)["totals"],
        }

    def _disks(self, snapshot_id):
        with self.db.lock, self.db._connect() as conn:
            rows = conn.execute(
                "SELECT mountpoint,total_gb,used_gb,free_gb,usage_percent FROM disks WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchall()
        return [
            {"mountpoint": r[0], "total_gb": round(float(r[1]), 2), "used_gb": round(float(r[2]), 2),
             "free_gb": round(float(r[3]), 2), "usage_percent": round(float(r[4]), 2)}
            for r in rows
        ]

    def _network(self, snapshot_id):
        with self.db.lock, self.db._connect() as conn:
            rows = conn.execute(
                "SELECT interface,download_mbps,upload_mbps,total_received_mb,total_sent_mb FROM network WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchall()
        return [
            {"interface": r[0], "download_mbps": round(float(r[1]), 2), "upload_mbps": round(float(r[2]), 2),
             "total_received_mb": round(float(r[3]), 2), "total_sent_mb": round(float(r[4]), 2)}
            for r in rows
        ]


def tool_definitions() -> list[dict]:
    return [
        {"type": "function", "function": {"name": "get_current_metrics", "description": "Read the latest locally collected system metrics.", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "get_metric_history", "description": "Read recent metric history from local SQLite.", "parameters": {"type": "object", "properties": {"hours": {"type": "integer", "minimum": 1, "maximum": 168}}}}},
        {"type": "function", "function": {"name": "get_disk_metrics", "description": "Read latest disk utilization for all mounted disks.", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "get_network_metrics", "description": "Read latest network interface metrics.", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "get_cache_details", "description": "Read all locally scanned cache/temp paths and sizes.", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "get_events", "description": "Read aggregated event counts from local history.", "parameters": {"type": "object", "properties": {"hours": {"type": "integer", "minimum": 1, "maximum": 168}}}}},
        {"type": "function", "function": {"name": "analyze_trends", "description": "Calculate CPU, RAM, cache and event trends from local history.", "parameters": {"type": "object", "properties": {"hours": {"type": "integer", "minimum": 1, "maximum": 168}}}}},
    ]
