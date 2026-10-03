# ChallengeOne — Local System Metrics + AI Reliability Assistant

This version keeps the working v3 monitoring dashboard and adds a fully local AI reliability layer.

## Architecture

```text
Tkinter Dashboard
      |
      +---- local SQLite (system_metrics.db)
      |
      +---- FastAPI (127.0.0.1:8000)
                 |
                 +---- reliability tools -> SQLite
                 |
                 +---- Ollama -> Gemma 3 4B (local)

MCP server (stdio) exposes the same read-only reliability tools.
```

No system metrics are sent to a cloud AI service by this application. Ollama is configured for localhost.

## Features retained from v3

- CPU and per-logical-core utilization
- RAM utilization
- Disk utilization
- Network throughput
- Windows cache/temp/Prefetch/browser cache details
- Windows Critical/Error/Warning event counts
- SQLite persistence
- 5-minute automatic collection
- Manual `Refresh metrics`
- 5:3 responsive Tkinter dashboard
- Compact current-day time graph
- Detailed CPU core table
- Detailed cache path table

## New AI features

- Local Ollama + Gemma 3 4B integration (tool-compatible: SQLite/tool calls are executed by Python and supplied as JSON context)
- FastAPI local service on `127.0.0.1:8000`
- Read-only reliability tool functions
- MCP server exposing the reliability tools over stdio
- AI reliability analysis panel in the dashboard
- AI analysis stored in SQLite `ai_analysis`
- Trend calculations before model inference
- Safe advisory mode: the model does not execute OS remediation commands

## Prerequisites

1. Python 3.10+ recommended.
2. Install Ollama locally.
3. Pull the local model:

```bash
ollama pull gemma3:4b
```

Ollama normally listens on:

`http://127.0.0.1:11434`

4. Install Python dependencies:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

The `mcp` package is included in `requirements.txt` because the MCP server uses the official Python MCP SDK. If your environment is offline, install the dependency from your local package mirror before starting the MCP server.

## Run the desktop application

```bash
python main.py
```

Or on Windows:

```text
run_app.bat
```

The desktop application starts FastAPI automatically as a background daemon thread.

## FastAPI endpoints

- `GET /health` — API and Ollama health
- `GET /api/system/current` — latest local metrics
- `GET /api/system/history?hours=24` — historical metrics
- `GET /api/system/trends?hours=24` — calculated reliability trends
- `GET /api/system/cache` — latest cache path details
- `POST /api/ai/analyze` — run local Gemma reliability analysis

To run the API separately:

```bash
python -m uvicorn api_server:app --host 127.0.0.1 --port 8000
```

## MCP server

The MCP server is a separate local stdio process:

```bash
python mcp_server.py
```

It exposes read-only tools:

- `get_current_metrics`
- `get_metric_history`
- `get_disk_metrics`
- `get_network_metrics`
- `get_cache_details`
- `get_events`
- `analyze_trends`

The MCP server does not expose destructive system actions.

## Configuration

Edit `config.json`:

```json
{
  "ollama": {
    "base_url": "http://127.0.0.1:11434",
    "model": "gemma3:4b",
    "timeout_seconds": 120
  },
  "api": {
    "host": "127.0.0.1",
    "port": 8000
  },
  "reliability": {
    "history_hours": 24,
    "analysis_cooldown_seconds": 300
  }
}
```

## Reliability flow

```text
System metrics
   -> SQLite
   -> read-only reliability tools
   -> trend/anomaly context
   -> local Gemma 3 4B via Ollama
   -> structured reliability assessment
   -> dashboard + SQLite history
```

The AI is advisory. Reliability read tools are executed locally by Python before inference, so Gemma 3 4B does not need native Ollama tool-calling support. The same read-only tools are also exposed through the local MCP server. A later version can add explicit user-approved remediation tools such as service restart or cache cleanup, but those are intentionally not enabled here.
