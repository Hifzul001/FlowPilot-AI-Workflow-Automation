from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Workflow(BaseModel):
    workflow_id: str
    name: str
    trigger: str
    inputs: str
    steps: str
    decision_logic: str
    tools_required: str
    expected_output: str
    arguments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    executable_steps: list[dict[str, Any]] = Field(default_factory=list)


class TraceEvent(BaseModel):
    timestamp: str
    event: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    workflow_id: str | None = None
    workflow_name: str | None = None
    status: str
    output: Any = None
    missing_inputs: list[str] = Field(default_factory=list)
    error: str | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    arguments: dict[str, Any] = Field(default_factory=dict)
    llm_usage: list[dict[str, Any]] = Field(default_factory=list)
    llm_errors: list[dict[str, str]] = Field(default_factory=list)
