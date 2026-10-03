"""MCP server exposing read-only local system reliability tools.

Run separately with:
    python mcp_server.py
"""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from main import MetricsDB
from reliability_tools import ReliabilityTools

DB_PATH = Path(__file__).resolve().parent / "system_metrics.db"
db = MetricsDB(DB_PATH)
tools = ReliabilityTools(db)

mcp = FastMCP("local-system-reliability")


@mcp.tool()
def get_current_metrics() -> dict:
    """Get the latest locally collected CPU, RAM, disk, network, cache and event metrics."""
    return tools.get_current_metrics()


@mcp.tool()
def get_metric_history(hours: int = 24) -> dict:
    """Get recent system metric history from local SQLite."""
    return tools.get_metric_history(hours)


@mcp.tool()
def get_disk_metrics() -> dict:
    """Get latest disk utilization for all mounted disks."""
    return tools.get_disk_metrics()


@mcp.tool()
def get_network_metrics() -> dict:
    """Get latest network interface metrics."""
    return tools.get_network_metrics()


@mcp.tool()
def get_cache_details() -> dict:
    """Get all cache/temp paths scanned by the monitoring application."""
    return tools.get_cache_details()


@mcp.tool()
def get_events(hours: int = 24) -> dict:
    """Get aggregated event counts from local history."""
    return tools.get_events(hours)


@mcp.tool()
def analyze_trends(hours: int = 24) -> dict:
    """Calculate reliability-relevant CPU, RAM, cache and event trends."""
    return tools.analyze_trends(hours)


if __name__ == "__main__":
    mcp.run(transport="stdio")
