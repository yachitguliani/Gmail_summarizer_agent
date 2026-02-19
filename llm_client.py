import json
import requests
from typing import Any, Dict, List, Optional


class OllamaClient:
    """
    Minimal client for Ollama's local REST API.
    Uses POST /api/chat on http://localhost:11434.
    :contentReference[oaicite:3]{index=3}
    """

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat_json(
        self,
        system: str,
        user: str,
        timeout: int = 120,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """
        Asks the model to return STRICT JSON only.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": temperature,
            },
            # Ollama supports structured JSON output via `format: "json"` for generate,
            # and for chat many models will comply with strict JSON instructions.
            # We'll enforce by parsing + fallback repair.
        }

        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()

        content = (data.get("message") or {}).get("content") or ""
        return self._parse_json_strict(content)

    def _parse_json_strict(self, s: str) -> Dict[str, Any]:
        """
        Robust JSON extraction:
        - If model returns extra text, extract the first {...} block.
        """
        s = s.strip()
        # Fast path
        try:
            return json.loads(s)
        except Exception:
            pass

        # Extract first JSON object substring
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = s[start : end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        # If still failing, raise helpful error
        raise ValueError(f"Model did not return valid JSON. Raw output:\n{s[:2000]}")
    