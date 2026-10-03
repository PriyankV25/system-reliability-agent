from __future__ import annotations

import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"

DEFAULT_CONFIG = {
    "ollama": {
        "base_url": "http://127.0.0.1:11434",
        "model": "gemma3:4b",
        "timeout_seconds": 120,
    },
    "api": {"host": "127.0.0.1", "port": 8000},
    "reliability": {"history_hours": 24, "analysis_cooldown_seconds": 300},
}


def load_config() -> dict:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, json.JSONDecodeError):
        loaded = {}

    config = json.loads(json.dumps(DEFAULT_CONFIG))
    for section, values in loaded.items():
        if isinstance(values, dict) and section in config:
            config[section].update(values)
    return config
