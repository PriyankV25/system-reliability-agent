"""
System Metrics Monitor
----------------------
Collects system metrics every 5 minutes, stores them in SQLite, and
visualizes the collected data in a Tkinter + Matplotlib GUI.

Run:
    pip install -r requirements.txt
    python main.py

Notes:
- Designed primarily for Windows because the supplied cache/event-log
  collectors target Windows.
- CPU/RAM/Disk/Network collection uses psutil.
- Network speed is measured over a short 1-second sampling window at each
  5-minute collection point.
- The GUI and collector run on separate threads so the UI remains responsive.
"""

from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import psutil
import tkinter as tk
from tkinter import ttk, messagebox

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

try:
    from cacheCalc import get_size, get_browser_cache_paths
except ImportError:
    get_size = None
    get_browser_cache_paths = None


APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "system_metrics.db"
COLLECTION_INTERVAL_SECONDS = 5 * 60
NETWORK_SAMPLE_SECONDS = 1.0


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class MetricsDB:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self.lock = threading.Lock()
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self):
        with self.lock, self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cpu_percent REAL NOT NULL,
                    ram_percent REAL NOT NULL,
                    ram_used_gb REAL NOT NULL,
                    ram_available_gb REAL NOT NULL,
                    cache_total_mb REAL NOT NULL,
                    event_critical INTEGER NOT NULL DEFAULT 0,
                    event_error INTEGER NOT NULL DEFAULT 0,
                    event_warning INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS cpu_cores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    core_index INTEGER NOT NULL,
                    usage_percent REAL NOT NULL,
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS disks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    mountpoint TEXT NOT NULL,
                    total_gb REAL NOT NULL,
                    used_gb REAL NOT NULL,
                    free_gb REAL NOT NULL,
                    usage_percent REAL NOT NULL,
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS network (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    interface TEXT NOT NULL,
                    download_mbps REAL NOT NULL,
                    upload_mbps REAL NOT NULL,
                    total_received_mb REAL NOT NULL,
                    total_sent_mb REAL NOT NULL,
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS cache_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    size_mb REAL NOT NULL,
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
                    ON snapshots(timestamp);
                CREATE INDEX IF NOT EXISTS idx_cpu_snapshot
                    ON cpu_cores(snapshot_id);
                CREATE INDEX IF NOT EXISTS idx_disk_snapshot
                    ON disks(snapshot_id);
                CREATE INDEX IF NOT EXISTS idx_network_snapshot
                    ON network(snapshot_id);

                CREATE TABLE IF NOT EXISTS ai_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    model TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_analysis_timestamp
                    ON ai_analysis(timestamp);
            """)

    def save_snapshot(self, data: dict[str, Any]):
        with self.lock, self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO snapshots (
                    timestamp, cpu_percent, ram_percent, ram_used_gb,
                    ram_available_gb, cache_total_mb,
                    event_critical, event_error, event_warning
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["timestamp"],
                data["cpu_percent"],
                data["ram_percent"],
                data["ram_used_gb"],
                data["ram_available_gb"],
                data["cache_total_mb"],
                data["events"]["critical"],
                data["events"]["error"],
                data["events"]["warning"],
            ))
            snapshot_id = cur.lastrowid

            conn.executemany("""
                INSERT INTO cpu_cores(snapshot_id, core_index, usage_percent)
                VALUES (?, ?, ?)
            """, [
                (snapshot_id, i, value)
                for i, value in enumerate(data["cpu_cores"])
            ])

            conn.executemany("""
                INSERT INTO disks(
                    snapshot_id, mountpoint, total_gb, used_gb, free_gb, usage_percent
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                (
                    snapshot_id,
                    d["mountpoint"],
                    d["total_gb"],
                    d["used_gb"],
                    d["free_gb"],
                    d["usage_percent"],
                )
                for d in data["disks"]
            ])

            conn.executemany("""
                INSERT INTO network(
                    snapshot_id, interface, download_mbps, upload_mbps,
                    total_received_mb, total_sent_mb
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                (
                    snapshot_id,
                    n["interface"],
                    n["download_mbps"],
                    n["upload_mbps"],
                    n["total_received_mb"],
                    n["total_sent_mb"],
                )
                for n in data["network"]
            ])

            conn.executemany("""
                INSERT INTO cache_paths(snapshot_id, path, size_mb)
                VALUES (?, ?, ?)
            """, [
                (snapshot_id, c["path"], c["size_mb"])
                for c in data["cache_paths"]
            ])

    def latest_snapshot(self):
        with self.lock, self._connect() as conn:
            row = conn.execute("""
                SELECT id, timestamp, cpu_percent, ram_percent, ram_used_gb,
                       ram_available_gb, cache_total_mb,
                       event_critical, event_error, event_warning
                FROM snapshots
                ORDER BY id DESC LIMIT 1
            """).fetchone()
            return row

    def history(self, hours=24):
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.lock, self._connect() as conn:
            rows = conn.execute("""
                SELECT timestamp, cpu_percent, ram_percent, cache_total_mb,
                       event_critical, event_error, event_warning
                FROM snapshots
                WHERE timestamp >= ?
                ORDER BY timestamp
            """, (cutoff,)).fetchall()
            return rows

    def latest_cpu_cores(self, snapshot_id):
        with self.lock, self._connect() as conn:
            return conn.execute(
                "SELECT core_index, usage_percent FROM cpu_cores "
                "WHERE snapshot_id = ? ORDER BY core_index",
                (snapshot_id,),
            ).fetchall()

    def latest_cache_paths(self, snapshot_id):
        with self.lock, self._connect() as conn:
            return conn.execute(
                "SELECT path, size_mb FROM cache_paths "
                "WHERE snapshot_id = ? ORDER BY size_mb DESC",
                (snapshot_id,),
            ).fetchall()

    def disk_history(self, hours=24):
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.lock, self._connect() as conn:
            return conn.execute("""
                SELECT d.mountpoint, s.timestamp, d.usage_percent
                FROM disks d
                JOIN snapshots s ON s.id = d.snapshot_id
                WHERE s.timestamp >= ?
                ORDER BY s.timestamp
            """, (cutoff,)).fetchall()

    def network_history(self, hours=24):
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self.lock, self._connect() as conn:
            return conn.execute("""
                SELECT n.interface, s.timestamp,
                       n.download_mbps, n.upload_mbps
                FROM network n
                JOIN snapshots s ON s.id = n.snapshot_id
                WHERE s.timestamp >= ?
                ORDER BY s.timestamp
            """, (cutoff,)).fetchall()


    def save_ai_analysis(self, analysis: dict[str, Any]):
        import json
        with self.lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO ai_analysis(timestamp,status,summary,analysis_json,model) VALUES (?,?,?,?,?)",
                (
                    analysis.get("generated_at", datetime.now().isoformat(timespec="seconds")),
                    analysis.get("status", "UNKNOWN"),
                    analysis.get("summary", ""),
                    json.dumps(analysis, ensure_ascii=False),
                    analysis.get("model", "unknown"),
                ),
            )

    def latest_ai_analysis(self):
        with self.lock, self._connect() as conn:
            return conn.execute(
                "SELECT timestamp,status,summary,analysis_json,model FROM ai_analysis ORDER BY id DESC LIMIT 1"
            ).fetchone()


# ---------------------------------------------------------------------------
# Metric collection


# ---------------------------------------------------------------------------
# Metric collection
# ---------------------------------------------------------------------------

def bytes_to_mb(value: float) -> float:
    return value / (1024 * 1024)


def bytes_to_gb(value: float) -> float:
    return value / (1024 ** 3)


def collect_cpu() -> tuple[float, list[float]]:
    # A 1-second sample makes this comparable to the original CPU monitor.
    total = psutil.cpu_percent(interval=1)
    cores = psutil.cpu_percent(interval=None, percpu=True)
    return float(total), [float(x) for x in cores]


def collect_ram() -> tuple[float, float, float]:
    memory = psutil.virtual_memory()
    return (
        float(memory.percent),
        bytes_to_gb(memory.used),
        bytes_to_gb(memory.available),
    )


def collect_disks() -> list[dict[str, Any]]:
    result = []
    seen = set()

    for partition in psutil.disk_partitions(all=False):
        mountpoint = partition.mountpoint
        if mountpoint in seen:
            continue
        seen.add(mountpoint)

        try:
            usage = psutil.disk_usage(mountpoint)
        except (PermissionError, OSError):
            continue

        result.append({
            "mountpoint": mountpoint,
            "total_gb": bytes_to_gb(usage.total),
            "used_gb": bytes_to_gb(usage.used),
            "free_gb": bytes_to_gb(usage.free),
            "usage_percent": float(usage.percent),
        })

    return result


def get_connected_interfaces() -> list[str]:
    connected = []
    interface_stats = psutil.net_if_stats()
    interface_addresses = psutil.net_if_addrs()

    for interface, stats in interface_stats.items():
        if not stats.isup:
            continue

        if interface.lower() in {"loopback", "lo"}:
            continue

        for address in interface_addresses.get(interface, []):
            if address.family == socket.AF_INET:
                connected.append(interface)
                break

    return connected


def collect_network() -> list[dict[str, Any]]:
    """
    Measure network throughput over a short sample.

    The existing NetworkCalc measured MB/s using byte differences over
    one second. This implementation keeps that behavior but stores the
    actual rate in Mbps (megabits/sec) for clearer GUI labeling.
    """
    previous = psutil.net_io_counters(pernic=True)
    time.sleep(NETWORK_SAMPLE_SECONDS)
    current = psutil.net_io_counters(pernic=True)

    result = []
    for interface in get_connected_interfaces():
        if interface not in previous or interface not in current:
            continue

        old = previous[interface]
        now = current[interface]

        download_bytes = max(0, now.bytes_recv - old.bytes_recv)
        upload_bytes = max(0, now.bytes_sent - old.bytes_sent)

        download_mbps = (download_bytes / NETWORK_SAMPLE_SECONDS) * 8 / 1_000_000
        upload_mbps = (upload_bytes / NETWORK_SAMPLE_SECONDS) * 8 / 1_000_000

        result.append({
            "interface": interface,
            "download_mbps": download_mbps,
            "upload_mbps": upload_mbps,
            "total_received_mb": bytes_to_mb(now.bytes_recv),
            "total_sent_mb": bytes_to_mb(now.bytes_sent),
        })

    return result


def collect_cache_details() -> list[dict[str, Any]]:
    """Return every Windows cache/temp path scanned and its size."""
    details = []

    def add_path(path: str):
        try:
            size = get_size(path) if get_size is not None else 0
        except Exception:
            size = 0
        details.append({
            "path": path,
            "size_mb": bytes_to_mb(size),
        })

    if os.name == "nt":
        users_path = r"C:\Users"
        if os.path.isdir(users_path):
            try:
                users = [
                    os.path.join(users_path, name)
                    for name in os.listdir(users_path)
                    if os.path.isdir(os.path.join(users_path, name))
                ]
            except OSError:
                users = []

            for user_path in users:
                add_path(os.path.join(user_path, r"AppData\Local\Temp"))

        for path in (
            r"C:\Windows\Temp",
            r"C:\Windows\System32\temp",
            r"C:\Windows\Prefetch",
        ):
            add_path(path)

        if get_browser_cache_paths is not None:
            try:
                for _, _, _, cache_path in get_browser_cache_paths():
                    add_path(cache_path)
            except Exception:
                pass

    if not details:
        details.append({
            "path": "Windows cache paths are not available on this OS",
            "size_mb": 0.0,
        })

    return details


def collect_cache() -> float:
    return sum(item["size_mb"] for item in collect_cache_details())


def collect_event_counts() -> dict[str, int]:
    """
    Count Critical/Error/Warning Windows events from the last 5 minutes.

    This stores a compact summary rather than the entire event message,
    keeping the SQLite database small. If PowerShell/Event Log is not
    available, all counts are returned as zero.
    """
    counts = {"critical": 0, "error": 0, "warning": 0}

    if os.name != "nt":
        return counts

    ps_script = r"""
$startTime = (Get-Date).AddMinutes(-5)
$logs = @("System","Application","Security")
$events = Get-WinEvent -FilterHashtable @{
    LogName=$logs
    Level=1,2,3
    StartTime=$startTime
} -ErrorAction SilentlyContinue
$events | Group-Object Level | ForEach-Object {
    "$($_.Name)|$($_.Count)"
}
"""

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        if result.returncode != 0:
            return counts

        for line in result.stdout.splitlines():
            if "|" not in line:
                continue
            level, value = line.strip().split("|", 1)
            try:
                number = int(value)
            except ValueError:
                continue

            if level == "1":
                counts["critical"] = number
            elif level == "2":
                counts["error"] = number
            elif level == "3":
                counts["warning"] = number
    except (OSError, subprocess.SubprocessError):
        pass

    return counts


def collect_all_metrics() -> dict[str, Any]:
    timestamp = datetime.now().isoformat(timespec="seconds")

    cpu_percent, cpu_cores = collect_cpu()
    ram_percent, ram_used_gb, ram_available_gb = collect_ram()

    # Disk/cache/event/network are independent enough to collect after CPU/RAM.
    disks = collect_disks()
    cache_paths = collect_cache_details()
    cache_total_mb = sum(item["size_mb"] for item in cache_paths)
    network = collect_network()
    events = collect_event_counts()

    return {
        "timestamp": timestamp,
        "cpu_percent": cpu_percent,
        "cpu_cores": cpu_cores,
        "ram_percent": ram_percent,
        "ram_used_gb": ram_used_gb,
        "ram_available_gb": ram_available_gb,
        "disks": disks,
        "cache_total_mb": cache_total_mb,
        "cache_paths": cache_paths,
        "network": network,
        "events": events,
    }


# ---------------------------------------------------------------------------
# Collector worker
# ---------------------------------------------------------------------------

class MetricsCollector(threading.Thread):
    def __init__(self, db: MetricsDB, interval=COLLECTION_INTERVAL_SECONDS):
        super().__init__(daemon=True)
        self.db = db
        self.interval = interval
        self.stop_event = threading.Event()
        self.status_callback = None

    def stop(self):
        self.stop_event.set()

    def run(self):
        while not self.stop_event.is_set():
            try:
                if self.status_callback:
                    self.status_callback("Collecting system metrics...")

                data = collect_all_metrics()
                self.db.save_snapshot(data)

                if self.status_callback:
                    self.status_callback(
                        f"Saved snapshot: {data['timestamp']}"
                    )
            except Exception as exc:
                if self.status_callback:
                    self.status_callback(f"Collection error: {exc}")

            # Wait instead of sleeping so shutdown is responsive.
            self.stop_event.wait(self.interval)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class SystemMetricsApp(tk.Tk):
    """Responsive 5:3 dashboard with compact graph and detailed CPU/cache data."""

    def __init__(self):
        super().__init__()
        self.title("System Metrics Monitor")
        self._set_responsive_window()
        self.minsize(900, 540)

        self.db = MetricsDB()
        self.collector = MetricsCollector(self.db)
        self.collector.status_callback = self.set_status_from_worker
        self.refresh_in_progress = False
        self.ai_in_progress = False
        self.ai_result = None

        self._build_style()
        self._build_home()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        try:
            from api_server import start_api_server
            start_api_server()
        except Exception as exc:
            self.status_var.set(f"FastAPI unavailable: {exc}")

        self.collector.start()
        self.after(1500, self.refresh_gui)
        self.after(1000, self.update_status)

    def _set_responsive_window(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        h = max(540, int(sh * 0.82))
        w = int(h * 5 / 3)
        if w > int(sw * 0.90):
            w = int(sw * 0.90)
            h = int(w * 3 / 5)
        w, h = min(w, sw - 30), min(h, sh - 80)
        self.geometry(f"{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2)}")

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Header.TLabel", font=("Segoe UI", 17, "bold"))
        style.configure("Metric.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("MetricTitle.TLabel", font=("Segoe UI", 9))
        style.configure("Status.TLabel", font=("Segoe UI", 9))
        style.configure("Refresh.TButton", font=("Segoe UI", 10, "bold"))

    def _build_home(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(14, 8, 14, 4))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Frame(header)
        title.grid(row=0, column=0, sticky="w")
        ttk.Label(title, text="System Metrics Monitor",
                  style="Header.TLabel").pack(anchor="w")
        self.last_update_var = tk.StringVar(value="Waiting for first snapshot...")
        ttk.Label(title, textvariable=self.last_update_var,
                  style="Status.TLabel").pack(anchor="w")

        actions = ttk.Frame(header)
        actions.grid(row=0, column=1, sticky="e")
        self.refresh_button = ttk.Button(
            actions, text="↻  Refresh metrics",
            command=self.manual_refresh, style="Refresh.TButton")
        self.refresh_button.pack(side="left", padx=(0, 8))
        self.ai_button = ttk.Button(
            actions, text="AI Reliability analysis",
            command=self.run_ai_analysis, style="Refresh.TButton")
        self.ai_button.pack(side="left", padx=(0, 8))
        self.status_var = tk.StringVar(value="Starting metric collector...")
        ttk.Label(actions, textvariable=self.status_var,
                  style="Status.TLabel").pack(side="left")

        main = ttk.Frame(self, padding=(12, 4, 12, 10))
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)

        cards = ttk.Frame(main)
        cards.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        for i in range(6):
            cards.columnconfigure(i, weight=1)

        self.cpu_var = tk.StringVar(value="--")
        self.ram_var = tk.StringVar(value="--")
        self.disk_var = tk.StringVar(value="--")
        self.network_var = tk.StringVar(value="--")
        self.cache_var = tk.StringVar(value="--")
        self.events_var = tk.StringVar(value="--")

        for i, (name, var) in enumerate([
            ("CPU", self.cpu_var), ("RAM", self.ram_var),
            ("Disk", self.disk_var), ("Network", self.network_var),
            ("Cache", self.cache_var), ("Events", self.events_var)
        ]):
            self._metric_card(cards, name, var, i)

        chart_frame = ttk.LabelFrame(
            main, text="Today's metrics — minutes", padding=3)
        chart_frame.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        # Intentionally short chart to make room for details.
        self.fig = Figure(figsize=(10, 1.45), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.tick_params(axis="both", labelsize=7)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        details = ttk.Frame(main)
        details.grid(row=2, column=0, sticky="nsew")
        details.columnconfigure(0, weight=1)
        details.columnconfigure(1, weight=1)
        details.rowconfigure(0, weight=1)

        cpu_box = ttk.LabelFrame(details, text="CPU core consumption", padding=5)
        cpu_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        cpu_box.columnconfigure(0, weight=1)
        cpu_box.rowconfigure(0, weight=1)

        self.cpu_tree = ttk.Treeview(
            cpu_box, columns=("core", "usage", "bar"),
            show="headings", height=8)
        self.cpu_tree.heading("core", text="Core")
        self.cpu_tree.heading("usage", text="Consumption")
        self.cpu_tree.heading("bar", text="Load")
        self.cpu_tree.column("core", width=75, anchor="center")
        self.cpu_tree.column("usage", width=105, anchor="center")
        self.cpu_tree.column("bar", width=190, anchor="w")
        self.cpu_tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(cpu_box, orient="vertical",
                           command=self.cpu_tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.cpu_tree.configure(yscrollcommand=sb.set)

        cache_box = ttk.LabelFrame(
            details, text="Cache details — all scanned paths", padding=5)
        cache_box.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        cache_box.columnconfigure(0, weight=1)
        cache_box.rowconfigure(0, weight=1)

        self.cache_tree = ttk.Treeview(
            cache_box, columns=("path", "size"),
            show="headings", height=8)
        self.cache_tree.heading("path", text="Cache / Temp path")
        self.cache_tree.heading("size", text="Size")
        self.cache_tree.column("path", width=430, anchor="w")
        self.cache_tree.column("size", width=100, anchor="e")
        self.cache_tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(cache_box, orient="vertical",
                           command=self.cache_tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.cache_tree.configure(yscrollcommand=sb.set)

        ai_box = ttk.LabelFrame(details, text="Local AI Reliability Assistant — Ollama / Gemma 3 4B", padding=5)
        ai_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ai_box.columnconfigure(1, weight=1)
        self.ai_status_var = tk.StringVar(value="AI analysis is local. Click the button to analyze the stored metrics.")
        ttk.Label(ai_box, textvariable=self.ai_status_var, width=24).grid(row=0, column=0, sticky="nw", padx=(0, 8))
        self.ai_text = tk.Text(ai_box, height=5, wrap="word", font=("Segoe UI", 9), state="disabled")
        self.ai_text.grid(row=0, column=1, sticky="ew")
        self._show_ai_result_from_db()

    def _metric_card(self, parent, title, variable, column):
        card = ttk.LabelFrame(parent, padding=(7, 4))
        card.grid(row=0, column=column, sticky="ew", padx=3)
        ttk.Label(card, text=title, style="MetricTitle.TLabel").pack()
        ttk.Label(card, textvariable=variable,
                  style="Metric.TLabel").pack(pady=(1, 0))

    def manual_refresh(self):
        if self.refresh_in_progress:
            return
        self.refresh_in_progress = True
        self.refresh_button.configure(state="disabled")
        self.status_var.set("Collecting latest metrics...")
        threading.Thread(target=self._manual_refresh_worker, daemon=True).start()

    def _manual_refresh_worker(self):
        try:
            data = collect_all_metrics()
            self.db.save_snapshot(data)
            self.after(0, lambda: self._refresh_finished(
                f"Updated at {data['timestamp']}"))
        except Exception as exc:
            self.after(0, lambda: self._refresh_finished(
                f"Refresh failed: {exc}"))

    def _refresh_finished(self, message):
        self.refresh_in_progress = False
        self.refresh_button.configure(state="normal")
        self.status_var.set(message)
        self.refresh_gui()

    def _set_ai_text(self, text):
        self.ai_text.configure(state="normal")
        self.ai_text.delete("1.0", "end")
        self.ai_text.insert("1.0", text)
        self.ai_text.configure(state="disabled")

    def _show_ai_result_from_db(self):
        row = self.db.latest_ai_analysis()
        if not row:
            return
        import json
        try:
            result = json.loads(row[3])
            self._render_ai_result(result)
        except Exception:
            self._set_ai_text(row[2])
            self.ai_status_var.set(f"{row[1]} • {row[4]} • {row[0]}")

    def run_ai_analysis(self):
        if self.ai_in_progress:
            return
        self.ai_in_progress = True
        self.ai_button.configure(state="disabled")
        self.ai_status_var.set("Gemma 3 4B is analyzing local SQLite metrics...")
        threading.Thread(target=self._ai_worker, daemon=True).start()

    def _ai_worker(self):
        try:
            import json
            import urllib.request
            body = json.dumps({
                "question": "Assess the current system reliability and suggest safe stabilization and maintenance steps based only on the locally stored metrics."
            }).encode("utf-8")
            request = urllib.request.Request(
                "http://127.0.0.1:8000/api/ai/analyze",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=130) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.db.save_ai_analysis(result)
            self.after(0, lambda r=result: self._ai_finished(r))
        except Exception as exc:
            result = {
                "status": "INSUFFICIENT_DATA",
                "summary": f"AI service unavailable: {exc}",
                "findings": [],
                "maintenance": ["Start Ollama and verify the local Gemma 3 4B model is installed."],
                "confidence": "LOW",
                "model": "gemma3:4b",
            }
            self.after(0, lambda r=result: self._ai_finished(r))

    def _ai_finished(self, result):
        self.ai_in_progress = False
        self.ai_button.configure(state="normal")
        self._render_ai_result(result)

    def _render_ai_result(self, result):
        status = result.get("status", "UNKNOWN")
        model = result.get("model", "gemma3:4b")
        confidence = result.get("confidence", "UNKNOWN")
        generated = result.get("generated_at", "")
        self.ai_status_var.set(f"{status} • confidence {confidence} • {model} • {generated}")
        lines = [result.get("summary", "No summary returned.")]
        findings = result.get("findings") or []
        for item in findings:
            lines.append(
                f"[{item.get('severity','?')}] {item.get('area','SYSTEM')}: "
                f"{item.get('evidence','')} Recommendation: {item.get('recommendation','')}"
            )
        maintenance = result.get("maintenance") or []
        if maintenance:
            lines.append("Maintenance:")
            lines.extend(f"• {x}" for x in maintenance)
        self._set_ai_text("\n".join(lines))

    def set_status_from_worker(self, message):
        self.after(0, lambda: self.status_var.set(message))

    def _today_history(self):
        today = datetime.now().date()
        return [r for r in self.db.history(24)
                if datetime.fromisoformat(r[0]).date() == today]

    def refresh_gui(self):
        try:
            latest = self.db.latest_snapshot()
            if latest:
                self._refresh_cards(latest)
                self._refresh_cpu_details(latest[0])
                self._refresh_cache_details(latest[0])
            self._refresh_graph(self._today_history())
        except Exception as exc:
            self.status_var.set(f"GUI refresh error: {exc}")
        finally:
            self.after(5000, self.refresh_gui)

    def _refresh_cards(self, row):
        sid, timestamp, cpu, ram, ram_used, ram_available, cache_mb, c, e, w = row
        self.cpu_var.set(f"{cpu:.1f}%")
        self.ram_var.set(f"{ram:.1f}%")
        self.disk_var.set(self._latest_disk_text(sid))
        self.network_var.set(self._latest_network_text(sid))
        self.cache_var.set(f"{cache_mb:.1f} MB")
        self.events_var.set(f"C:{c} E:{e} W:{w}")
        self.last_update_var.set(
            f"Latest snapshot: {timestamp}  •  Auto interval: 5 min")

    def _refresh_cpu_details(self, snapshot_id):
        for item in self.cpu_tree.get_children():
            self.cpu_tree.delete(item)
        for core, usage in self.db.latest_cpu_cores(snapshot_id):
            usage = float(usage)
            filled = max(0, min(20, round(usage / 5)))
            bar = "█" * filled + "░" * (20 - filled)
            self.cpu_tree.insert(
                "", "end",
                values=(f"Core {core}", f"{usage:.1f}%", bar))

    def _refresh_cache_details(self, snapshot_id):
        for item in self.cache_tree.get_children():
            self.cache_tree.delete(item)
        rows = self.db.latest_cache_paths(snapshot_id)
        total = 0.0
        for path, size in rows:
            size = float(size)
            total += size
            self.cache_tree.insert("", "end",
                                   values=(path, f"{size:.2f} MB"))
        if rows:
            self.cache_tree.insert("", "end",
                                   values=("TOTAL", f"{total:.2f} MB"))

    def _latest_disk_text(self, snapshot_id):
        with self.db.lock, self.db._connect() as conn:
            rows = conn.execute(
                "SELECT usage_percent FROM disks WHERE snapshot_id = ?",
                (snapshot_id,)).fetchall()
        if not rows:
            return "--"
        if len(rows) == 1:
            return f"{rows[0][0]:.1f}%"
        return f"{sum(r[0] for r in rows) / len(rows):.1f}% avg"

    def _latest_network_text(self, snapshot_id):
        with self.db.lock, self.db._connect() as conn:
            rows = conn.execute(
                "SELECT download_mbps, upload_mbps FROM network "
                "WHERE snapshot_id = ?", (snapshot_id,)).fetchall()
        if not rows:
            return "--"
        return f"↓{sum(r[0] for r in rows):.1f} ↑{sum(r[1] for r in rows):.1f}"

    def _refresh_graph(self, rows):
        self.ax.clear()
        if not rows:
            self.ax.text(0.5, 0.5, "No metric snapshots collected today yet",
                         ha="center", va="center", transform=self.ax.transAxes,
                         fontsize=9)
            self.ax.set_axis_off()
            self.canvas.draw_idle()
            return

        self.ax.set_axis_on()
        x = [datetime.fromisoformat(r[0]) for r in rows]
        self.ax.plot(x, [r[1] for r in rows], label="CPU %")
        self.ax.plot(x, [r[2] for r in rows], label="RAM %")
        self.ax.plot(x, [r[3] / 10 for r in rows],
                     label="Cache / 10 MB", linestyle="--")
        self.ax.plot(x, [r[4] + r[5] + r[6] for r in rows],
                     label="Events", linestyle=":")
        self.ax.set_title("Current date — minute-by-minute snapshots", fontsize=8)
        self.ax.set_xlabel("Time", fontsize=7)
        self.ax.set_ylabel("Value", fontsize=7)
        self.ax.tick_params(axis="both", labelsize=7)
        self.ax.set_ylim(bottom=0)
        self.ax.grid(True, alpha=0.25)
        self.ax.legend(loc="upper left", fontsize=6, ncol=4)

        import matplotlib.dates as mdates
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        self.fig.tight_layout(pad=0.4)
        self.canvas.draw_idle()

    def update_status(self):
        if not self.refresh_in_progress:
            latest = self.db.latest_snapshot()
            if latest:
                try:
                    last = datetime.fromisoformat(latest[1])
                    remaining = max(
                        0,
                        int(COLLECTION_INTERVAL_SECONDS -
                            (datetime.now() - last).total_seconds()))
                    minutes, seconds = divmod(remaining, 60)
                    self.status_var.set(
                        f"Next automatic collection in {minutes:02d}:{seconds:02d}")
                except Exception:
                    pass
        self.after(1000, self.update_status)

    def on_close(self):
        self.collector.stop()
        self.destroy()


if __name__ == "__main__":
    app = SystemMetricsApp()
    app.mainloop()
