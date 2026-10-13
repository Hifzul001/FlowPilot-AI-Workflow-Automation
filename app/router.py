from __future__ import annotations

import json
import re
from typing import Any

from app.llm import GeminiService
from app.models import Workflow


class WorkflowRouter:
    """Gemini semantic router with a deterministic local fallback for offline use."""

    def __init__(self, workflows: dict[str, Workflow], llm: GeminiService | None = None):
        self.workflows = workflows
        self.llm = llm or GeminiService()
        self.last_error: str | None = None

    def route(self, request: str, supplied_inputs: dict[str, Any] | None = None) -> tuple[Workflow | None, dict[str, Any], str]:
        self.last_error = None
        supplied = dict(supplied_inputs or {})
        if self.llm.enabled:
            try:
                catalog = [{"id": w.workflow_id, "name": w.name, "trigger": w.trigger, "inputs": w.arguments} for w in self.workflows.values()]
                answer = self.llm.generate_json(
                    "You are FlowPilot's workflow router. Match the request to exactly one item in the catalog. "
                    "Return a JSON object with workflow_id and arguments. workflow_id MUST be one of these exact IDs: "
                    + json.dumps([w.workflow_id for w in self.workflows.values()])
                    + ". Use null only when no workflow matches. Extract only values stated by the user; do not invent missing values. "
                    "For an order request, extract the order ID. For a price request, extract a stated percentage as threshold_pct. "
                    "For product SEO requests, put explicitly stated attributes in the product argument. Workflow catalog: "
                    + json.dumps(catalog) + "\nUser request: " + request
                )
                if "workflow_id" not in answer:
                    raise ValueError("Gemini response did not include workflow_id")
                requested_id = str(answer.get("workflow_id", "")).strip().upper()
                wf = self.workflows.get(requested_id)
                if wf is None and requested_id:
                    compact = re.sub(r"[^A-Z0-9]", "", requested_id)
                    wf = next((item for wid, item in self.workflows.items() if re.sub(r"[^A-Z0-9]", "", wid.upper()) == compact), None)
                if wf is None and answer.get("workflow_name"):
                    name = str(answer["workflow_name"]).strip().casefold()
                    wf = next((item for item in self.workflows.values() if item.name.casefold() == name), None)
                if requested_id and wf is None:
                    raise ValueError("Gemini returned a workflow ID outside the configured catalog")
                extracted = answer.get("arguments", {}) if isinstance(answer.get("arguments", {}), dict) else {}
                return wf, {**extracted, **supplied}, "gemini"
            except Exception as exc:
                # Routing failures are recoverable; continue with local matching.
                self.last_error = self.llm.redact(f"Gemini routing failed with {self.llm.model}: {type(exc).__name__}: {exc}")
        text = request.lower()
        terms = {
            "WF001": ["restock", "inventory", "low stock", "reorder"],
            "WF002": ["price", "vendor price", "price differs", "price validation"],
            "WF003": ["vendor spreadsheet", "vendor file", "invalid rows", "process this file", "spreadsheet"],
            "WF004": ["seo content", "product description", "product content", "generate seo", "description"],
            "WF005": ["order", "tracking", "where is"],
            "WF006": ["duplicate", "duplicates", "similar products"],
            "WF007": ["campaign brief", "campaign", "new collection"],
            "WF008": ["keyword", "keywords", "classify"],
            "WF009": ["assign", "task", "developer", "employee"],
            "WF010": ["performance report", "workflows failing", "workflows are failing", "failing most", "execution logs", "failure rate"],
        }
        scores = {wid: sum(2 if term in text else 0 for term in hints) for wid, hints in terms.items()}
        # Tie breaks are intentionally absent: an ambiguous request should be clarified.
        best = max(scores.values(), default=0)
        winners = [wid for wid, score in scores.items() if score == best and score > 0]
        workflow = self.workflows[winners[0]] if len(winners) == 1 and winners[0] in self.workflows else None
        extracted: dict[str, Any] = {}
        for wid, w in self.workflows.items():
            if workflow != w:
                continue
            if "order_id" in w.arguments:
                m = re.search(r"\bORD-[A-Z0-9-]+\b", request, re.I)
                if m: extracted["order_id"] = m.group(0).upper()
                m = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", request)
                if m: extracted["email"] = m.group(0)
            if "threshold_pct" in w.arguments:
                m = re.search(r"(\d+(?:\.\d+)?)\s*%", request)
                if m: extracted["threshold_pct"] = float(m.group(1))
            if "threshold" in w.arguments:
                m = re.search(r"(?:threshold|min(?:imum)? stock(?: level)? of?)\s*(\d+(?:\.\d+)?)", text)
                if m: extracted["threshold"] = float(m.group(1))
            if wid == "WF007":
                if "new collection" in text: extracted.setdefault("products", ["new collection"])
                if "women" in text: extracted["audience"] = "women"
                if "men" in text: extracted["audience"] = "men"
                if "discount" in text or "promotion" in text: extracted["promotion"] = request
                dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", request)
                if dates: extracted["start_date"] = dates[0]
                if len(dates) > 1: extracted["end_date"] = dates[1]
            if wid == "WF009":
                if "urgent" in text or "high priority" in text: extracted["priority"] = "urgent"
                extracted["task"] = request
            if wid == "WF008":
                quoted = re.findall(r"[\"']([^\"']+)[\"']", request)
                if quoted: extracted["keywords"] = [x.strip() for x in quoted]
        method = "local_fallback_after_gemini_error" if self.last_error else "local"
        return workflow, {**extracted, **supplied}, method
