from __future__ import annotations

import json
from datetime import datetime

from ollama_client import OllamaClient, OllamaError
from reliability_tools import ReliabilityTools

SYSTEM_PROMPT = """You are a local system reliability assistant.
Analyze only the supplied local monitoring data. Do not invent measurements.
Your job is to identify reliability risks, explain evidence, and recommend safe, practical maintenance steps.
You are advisory only: never claim that you executed an action. Do not recommend destructive actions unless explicitly justified and clearly ask for human approval.
Prefer concise, prioritized recommendations.
Return valid JSON with this schema:
{
  "status": "HEALTHY|ATTENTION|HIGH_RISK|INSUFFICIENT_DATA",
  "summary": "short assessment",
  "findings": [{"area":"CPU/RAM/DISK/NETWORK/CACHE/EVENTS", "severity":"LOW|MEDIUM|HIGH", "evidence":"...", "recommendation":"..."}],
  "maintenance": ["..."],
  "confidence": "LOW|MEDIUM|HIGH"
}
"""


class ReliabilityEngine:
    def __init__(self, db):
        self.tools = ReliabilityTools(db)
        self.ollama = OllamaClient()

    def analyze(self, question: str | None = None) -> dict:
        current = self.tools.get_current_metrics()
        trends = self.tools.analyze_trends(24)
        history = self.tools.get_metric_history(24)
        prompt = {
            "current_metrics": current,
            "trend_analysis": trends,
            "metric_history": history,
            "operator_question": question or "Assess the current system reliability and suggest stabilization and maintenance steps.",
            "analysis_time": datetime.now().isoformat(timespec="seconds"),
        }
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ]
        try:
            # Gemma 3 4B on Ollama may reject the native `tools` request.
            # The application therefore performs the read-only tool calls in Python first
            # and sends their local SQLite results to the model as ordinary JSON context.
            response = self.ollama.chat(messages)
            message = response.get("message", {})
            content = message.get("content", "").strip()
            if not content:
                raise OllamaError("Gemma returned an empty response.")
            result = self._parse_json(content)
            result["model"] = self.ollama.model
            result["generated_at"] = datetime.now().isoformat(timespec="seconds")
            result["source"] = "local SQLite + Ollama"
            return result
        except Exception as exc:
            return {
                "status": "INSUFFICIENT_DATA",
                "summary": f"AI analysis is unavailable: {exc}",
                "findings": [],
                "maintenance": ["Start Ollama and make sure the configured Gemma 3 4B model is installed."],
                "confidence": "LOW",
                "model": self.ollama.model,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "source": "local",
                "error": str(exc),
            }

    @staticmethod
    def _parse_json(content: str) -> dict:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        # Keep non-JSON model output usable rather than failing the dashboard.
        return {
            "status": "ATTENTION",
            "summary": content[:4000],
            "findings": [],
            "maintenance": [],
            "confidence": "LOW",
        }
