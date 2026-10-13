from __future__ import annotations

import json
import time
import os
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class GeminiService:
    """Thin adapter around google-genai. No key is required for local deterministic mode."""

    MAX_503_RETRIES = 2
    INITIAL_RETRY_DELAY_SECONDS = 0.5
    MAX_RETRY_DELAY_SECONDS = 2.0

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
        self._client = None
        self.last_model_used: str | None = None
        self.request_count = 0
        self.last_retry_count = 0
        self.last_retry_delays: list[float] = []
        from google.genai import types
        # Disable SDK-level retries so the service's explicit 2-retry bound is exact.
        self.retry_options = types.HttpRetryOptions(attempts=1, http_status_codes=[503])
        self.http_options = types.HttpOptions(retry_options=self.retry_options)
        if self.api_key:
            from google import genai
            self._client = genai.Client(api_key=self.api_key, http_options=self.http_options)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def redact(self, message: object) -> str:
        text = str(message)
        return text.replace(self.api_key, "[redacted]") if self.api_key else text

    def generate_json(self, prompt: str, list_key: str | None = None) -> dict[str, Any]:
        if not self._client:
            raise RuntimeError("Gemini is not configured. Set GEMINI_API_KEY in .env.")
        self.last_retry_count = 0
        self.last_retry_delays = []
        self.last_model_used = None
        for retry_index in range(self.MAX_503_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config={"response_mime_type": "application/json", "temperature": 0.2},
                )
                break
            except Exception as exc:
                status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                response_obj = getattr(exc, "response", None)
                status_code = status_code or getattr(response_obj, "status_code", None)
                if status_code != 503 or retry_index >= self.MAX_503_RETRIES:
                    raise
                self.last_retry_count += 1
                delay = min(self.INITIAL_RETRY_DELAY_SECONDS * (2 ** retry_index), self.MAX_RETRY_DELAY_SECONDS)
                self.last_retry_delays.append(delay)
                time.sleep(delay)
        self.request_count += 1
        self.last_model_used = getattr(response, "model_version", None) or self.model
        text = response.text or ""
        if not text.strip():
            raise ValueError("Gemini returned an empty response")
        parsed = json.loads(text)
        if isinstance(parsed, list) and list_key:
            parsed = {list_key: parsed}
        if not isinstance(parsed, dict):
            raise ValueError("Gemini response was not a JSON object or supported list")
        # Keep provider/model provenance with the model-produced output.
        parsed["_llm"] = {"provider": "Gemini", "model": self.last_model_used, "retries": self.last_retry_count, "retry_delays_seconds": self.last_retry_delays.copy()}
        return parsed
