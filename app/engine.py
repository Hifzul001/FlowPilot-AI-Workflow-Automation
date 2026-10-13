from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.models import ExecutionResult, TraceEvent, Workflow
from app.router import WorkflowRouter
from app.tools import ToolRegistry


def _type_check(value: Any, type_name: str) -> bool:
    type_map = {"string": str, "number": (int, float), "list": list, "object": dict, "file": object}
    expected = type_map.get(type_name)
    return expected is None or isinstance(value, expected) if expected is not object else value is not None


class WorkflowEngine:
    def __init__(self, workflows: dict[str, Workflow], registry: ToolRegistry | None = None, router: WorkflowRouter | None = None):
        self.workflows = workflows
        self.registry = registry or ToolRegistry()
        self.router = router or WorkflowRouter(workflows, self.registry.llm)

    def run(self, request: str, inputs: dict[str, Any] | None = None, workflow_id: str | None = None) -> ExecutionResult:
        trace: list[TraceEvent] = []
        def log(event: str, message: str, **data):
            trace.append(TraceEvent(timestamp=datetime.now(timezone.utc).isoformat(), event=event, message=message, data=data))
        supplied = dict(inputs or {})
        self.registry.llm.last_retry_count = 0
        self.registry.llm.last_retry_delays = []
        self.registry.llm.last_model_used = None
        if workflow_id:
            wf = self.workflows.get(workflow_id)
            args, method = supplied, "manual"
        else:
            wf, args, method = self.router.route(request, supplied)
        route_retries = self.router.llm.last_retry_count
        log("routing", "Workflow selected" if wf else "No unambiguous workflow matched", workflow_id=wf.workflow_id if wf else None, method=method, retry_count=route_retries)
        llm_usage: list[dict[str, Any]] = []
        llm_errors: list[dict[str, str]] = []
        if method == "manual":
            llm_usage.append({"stage": "workflow_selection_and_extraction", "provider": "Manual selection", "model": "user-selected workflow"})
        elif method == "gemini":
            llm_usage.append({"stage": "workflow_selection_and_extraction", "provider": "Gemini", "model": self.router.llm.last_model_used or self.router.llm.model, "retries": route_retries, "retry_delays_seconds": self.router.llm.last_retry_delays.copy()})
        elif method == "local_fallback_after_gemini_error":
            llm_errors.append({"stage": "workflow_selection_and_extraction", "model": self.router.llm.model, "retries": str(route_retries), "retry_delays_seconds": str(self.router.llm.last_retry_delays), "error": self.router.last_error or "Gemini routing failed"})
            llm_usage.append({"stage": "workflow_selection_and_extraction", "provider": "Local fallback after Gemini error", "model": "keyword router", "retries": route_retries})
        elif not self.router.llm.enabled:
            llm_usage.append({"stage": "workflow_selection_and_extraction", "provider": "Local fallback", "model": "keyword router"})
        if not wf:
            return ExecutionResult(status="needs_input", output={"message": "Which workflow should I run? Try one of the listed workflow requests."}, trace=trace, llm_usage=llm_usage, llm_errors=llm_errors)

        args = dict(args)
        missing: list[str] = []
        for name, rule in wf.arguments.items():
            if name not in args and "default" in rule:
                args[name] = rule["default"]
            if rule.get("required") and args.get(name) in (None, "", []):
                missing.append(name)
            elif args.get(name) is not None and not _type_check(args[name], rule.get("type", "")):
                return ExecutionResult(workflow_id=wf.workflow_id, workflow_name=wf.name, status="failed", error=f"Input '{name}' must be type {rule.get('type')}.", arguments=args, trace=trace, llm_usage=llm_usage, llm_errors=llm_errors)
        # Identifier is an either/or requirement in WF005.
        if wf.workflow_id == "WF005" and not (args.get("order_id") or args.get("email")):
            missing.append("order_id or email")
        if missing:
            log("validation", "Required information is missing", missing_inputs=missing)
            return ExecutionResult(workflow_id=wf.workflow_id, workflow_name=wf.name, status="needs_input", missing_inputs=missing, output={"message": f"Please provide: {', '.join(missing)}."}, arguments=args, trace=trace, llm_usage=llm_usage, llm_errors=llm_errors)
        log("validation", "Inputs validated", argument_names=sorted(args))

        context: dict[str, Any] = {"arguments": args, **args}
        for position, step in enumerate(wf.executable_steps, 1):
            step_id = step.get("id", f"step_{position}")
            condition = step.get("when")
            if condition:
                try:
                    should_run = self._condition(condition, context)
                except Exception as exc:
                    log("condition_error", f"Condition for {step_id} failed", step_id=step_id, error=str(exc))
                    return ExecutionResult(workflow_id=wf.workflow_id, workflow_name=wf.name, status="failed", error=f"Condition for {step_id}: {exc}", trace=trace, arguments=args, llm_usage=llm_usage, llm_errors=llm_errors)
                if not should_run:
                    log("step_skipped", f"Skipped {step_id} because its condition was false", step_id=step_id)
                    continue
            tool = step.get("tool")
            if not tool:
                return ExecutionResult(workflow_id=wf.workflow_id, workflow_name=wf.name, status="failed", error=f"Step {step_id} has no tool configured", trace=trace, arguments=args, llm_usage=llm_usage, llm_errors=llm_errors)
            kwargs = {key: self._resolve(value, context) for key, value in step.get("args", {}).items()}
            log("tool_call", f"Calling {tool}", step_id=step_id, tool=tool, arguments=self._safe_args(kwargs))
            try:
                result = self.registry.call(tool, **kwargs)
                context[step.get("save_as", step_id)] = result
                log("step_result", f"Completed {step_id}", step_id=step_id, result=self._safe_result(result), retry_count=self.registry.llm.last_retry_count)
            except Exception as exc:
                safe_error = self.registry.llm.redact(exc)
                log("tool_error", f"Tool {tool} failed", step_id=step_id, tool=tool, error=safe_error, recoverable=True, retry_count=self.registry.llm.last_retry_count)
                if tool in {"product_content", "campaign_brief", "keyword_classification"} and self.registry.llm.enabled:
                    llm_errors.append({"stage": tool, "model": self.registry.llm.model, "retries": str(self.registry.llm.last_retry_count), "retry_delays_seconds": str(self.registry.llm.last_retry_delays), "error": f"{type(exc).__name__}: {safe_error}"})
                return ExecutionResult(workflow_id=wf.workflow_id, workflow_name=wf.name, status="failed", error=f"{tool}: {safe_error}", trace=trace, arguments=args, llm_usage=llm_usage, llm_errors=llm_errors)
        output = context.get("result")
        if isinstance(output, dict) and isinstance(output.get("_llm"), dict):
            meta = output["_llm"]
            llm_usage.append({"stage": "content_generation_or_classification", "provider": meta.get("provider", "Gemini"), "model": meta.get("model", "unknown"), "retries": meta.get("retries", 0), "retry_delays_seconds": meta.get("retry_delays_seconds", [])})
        elif not self.registry.llm.enabled and wf.workflow_id in {"WF004", "WF007", "WF008"} and output is not None:
            llm_usage.append({"stage": "content_generation_or_classification", "provider": "Local fallback", "model": "deterministic template/classifier"})
        if isinstance(output, dict) and output.get("status") == "needs_input":
            missing = output.get("missing_inputs", output.get("missing_attributes", []))
            log("validation", "Tool identified missing business information", missing_inputs=missing)
            return ExecutionResult(workflow_id=wf.workflow_id, workflow_name=wf.name, status="needs_input", output=output, missing_inputs=missing, arguments=args, trace=trace, llm_usage=llm_usage, llm_errors=llm_errors)
        status = "complete"
        if isinstance(output, dict) and output.get("status") == "not_found": status = "not_found"
        if isinstance(output, dict) and output.get("status") == "escalate": status = "escalate"
        log("workflow_complete", "Workflow execution finished", status=status)
        return ExecutionResult(workflow_id=wf.workflow_id, workflow_name=wf.name, status=status, output=output, arguments=args, trace=trace, llm_usage=llm_usage, llm_errors=llm_errors)

    @staticmethod
    def _resolve(value: Any, context: dict[str, Any]) -> Any:
        if not isinstance(value, str) or not (value.startswith("{{") and value.endswith("}}")):
            return value
        path = value[2:-2].strip().split(".")
        current: Any = context
        for part in path:
            if isinstance(current, dict): current = current.get(part)
            else: return None
        return current

    @staticmethod
    def _condition(condition: dict[str, Any], context: dict[str, Any]) -> bool:
        left = WorkflowEngine._resolve(condition.get("path"), context)
        op, right = condition.get("operator"), condition.get("value")
        if op == "equals": return left == right
        if op == "not_equals": return left != right
        if op == "exists": return left is not None
        if op == "truthy": return bool(left)
        if op == "greater_than": return left is not None and left > right
        raise ValueError(f"Unsupported condition operator: {op}")

    @staticmethod
    def _safe_args(args):
        return {k: (f"<file:{getattr(v, 'name', 'upload')}>" if hasattr(v, "getvalue") else v) for k, v in args.items()}

    @staticmethod
    def _safe_result(result):
        # Traces should remain readable; large tabular tool output remains in the result panel.
        if isinstance(result, dict): return {k: v for k, v in result.items() if k not in {"cleaned_rows", "products", "results", "groups"}}
        return str(result)[:500]
