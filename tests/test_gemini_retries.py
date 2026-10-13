from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm import GeminiService


class SimulatedAPIError(RuntimeError):
    def __init__(self, code: int):
        super().__init__(f"simulated HTTP {code}")
        self.code = code


class ScriptedModels:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def generate_content(self, **_kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def service_with(models):
    service = GeminiService(api_key="test-only-placeholder", model="gemini-test")
    service._client = SimpleNamespace(models=models)
    return service


def test_503_retries_twice_with_exponential_delays_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr("app.llm.time.sleep", sleeps.append)
    models = ScriptedModels([
        SimulatedAPIError(503),
        SimulatedAPIError(503),
        SimpleNamespace(text='{"answer":"ok"}', model_version="gemini-test-v1"),
    ])
    service = service_with(models)
    result = service.generate_json("test")
    assert models.calls == 3  # initial attempt plus the maximum two retries
    assert sleeps == [0.5, 1.0]
    assert result["answer"] == "ok"
    assert result["_llm"] == {"provider": "Gemini", "model": "gemini-test-v1", "retries": 2, "retry_delays_seconds": [0.5, 1.0]}
    assert service.retry_options.attempts == 1  # SDK retries are disabled; app owns the bound


def test_503_retry_bound_is_respected_when_service_stays_unavailable(monkeypatch):
    sleeps = []
    monkeypatch.setattr("app.llm.time.sleep", sleeps.append)
    models = ScriptedModels([SimulatedAPIError(503) for _ in range(4)])
    service = service_with(models)
    with pytest.raises(SimulatedAPIError):
        service.generate_json("test")
    assert models.calls == 3
    assert sleeps == [0.5, 1.0]
    assert service.last_retry_count == 2
    assert service.last_retry_delays == [0.5, 1.0]


def test_non_503_failure_is_not_retried(monkeypatch):
    sleeps = []
    monkeypatch.setattr("app.llm.time.sleep", sleeps.append)
    models = ScriptedModels([SimulatedAPIError(400), SimpleNamespace(text='{"answer":"should not run"}')])
    service = service_with(models)
    with pytest.raises(SimulatedAPIError):
        service.generate_json("test")
    assert models.calls == 1
    assert sleeps == []


def test_secret_and_generated_output_paths_are_ignored():
    rules = set(__import__("pathlib").Path(".gitignore").read_text(encoding="utf-8").splitlines())
    required = {".env", ".env.*", "!.env.example", "*.log", "*.jsonl", "logs/", "execution_logs/", "reports/", "outputs/", "artifacts/", "*.report.json", "execution-*.json", "workflow-run*.json", ".streamlit/secrets.toml", "*.pem", "*.key"}
    assert required <= rules
    assert __import__("pathlib").Path(".env").exists()
