from __future__ import annotations

import threading

from fastapi import FastAPI
from pydantic import BaseModel

from ai_config import load_config
from main import MetricsDB
from reliability_engine import ReliabilityEngine
from reliability_tools import ReliabilityTools

APP_DIR = __import__("pathlib").Path(__file__).resolve().parent
DB_PATH = APP_DIR / "system_metrics.db"
db = MetricsDB(DB_PATH)
tools = ReliabilityTools(db)
engine = ReliabilityEngine(db)

app = FastAPI(title="Local System Reliability Assistant", version="1.0.0")


class AnalyzeRequest(BaseModel):
    question: str | None = None


@app.get("/health")
def health():
    ollama = engine.ollama.health()
    return {"api": "ok", "ollama": ollama}


@app.get("/api/system/current")
def current():
    return tools.get_current_metrics()


@app.get("/api/system/history")
def history(hours: int = 24):
    return tools.get_metric_history(hours)


@app.get("/api/system/trends")
def trends(hours: int = 24):
    return tools.analyze_trends(hours)


@app.get("/api/system/cache")
def cache():
    return tools.get_cache_details()


@app.post("/api/ai/analyze")
def analyze(request: AnalyzeRequest):
    result = engine.analyze(request.question)
    if result.get("error"):
        # The endpoint remains HTTP 200 so the GUI can show the actionable error.
        return result
    return result


_server_started = False
_server_lock = threading.Lock()


def start_api_server():
    """Start FastAPI/Uvicorn in a daemon thread for the desktop application."""
    global _server_started
    with _server_lock:
        if _server_started:
            return
        _server_started = True

    import uvicorn
    config = load_config()["api"]
    thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": app,
            "host": config["host"],
            "port": int(config["port"]),
            "log_level": "warning",
        },
        daemon=True,
        name="FastAPI-Local-Reliability",
    )
    thread.start()
