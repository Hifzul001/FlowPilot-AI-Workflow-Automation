from __future__ import annotations

import json

import openpyxl

from app.config import WORKFLOW_CONFIG
from app.engine import WorkflowEngine
from app.loader import WorkflowLoader
from app.router import WorkflowRouter
from app.llm import GeminiService
from app.tools import ToolRegistry


def test_validation_type_error_and_alternative_identifier(engine):
    wrong = engine.run("Which products need restocking?", {"threshold": "many"})
    assert wrong.status == "failed"
    assert "must be type number" in wrong.error
    absent = engine.run("Where is the order?")
    assert absent.status == "needs_input"
    assert absent.missing_inputs == ["order_id or email"]


def test_api_error_is_traced_and_recoverable(engine, workflows):
    def failing(**_): raise TimeoutError("simulated service timeout")
    engine.registry.register("test_failure", failing)
    wf = workflows["WF001"].model_copy(update={"workflow_id": "WF011_TEST", "executable_steps": [{"id": "api", "tool": "test_failure", "args": {}}]})
    engine.workflows["WF011_TEST"] = wf
    result = engine.run("", workflow_id="WF011_TEST")
    assert result.status == "failed"
    assert "simulated service timeout" in result.error
    assert any(event.event == "tool_error" and event.data["recoverable"] for event in result.trace)


def test_conditional_steps_skip_when_condition_false(workflows):
    wf = workflows["WF001"].model_copy(update={"executable_steps": [
        {"id": "conditional", "tool": "inventory_restock", "args": {}, "when": {"path": "{{arguments.run_it}}", "operator": "equals", "value": True}, "save_as": "result"}
    ], "arguments": {"run_it": {"type": "number", "required": False}}})
    result = WorkflowEngine({"WF001": wf}, ToolRegistry()).run("", {"run_it": 0}, workflow_id="WF001")
    assert result.status == "complete"
    assert any(event.event == "step_skipped" for event in result.trace)
    assert result.output is None


def test_11th_workflow_can_be_added_by_excel_row(tmp_path):
    source = openpyxl.load_workbook(WORKFLOW_CONFIG)
    sheet = source["Workflows"]
    sheet.append([
        "WF011", "Inventory Summary", "User asks for a catalog inventory summary", "Inventory CSV", "Read inventory → calculate summary", "Count current SKUs", "CSV reader; calculator", "SKU count and low stock rows",
        json.dumps({}), json.dumps([{"id": "summary", "tool": "inventory_restock", "args": {}, "save_as": "result"}]),
    ])
    path = tmp_path / "extended.xlsx"
    source.save(path)
    extended = WorkflowLoader(path).load()
    assert "WF011" in extended
    result = WorkflowEngine(extended).run("", workflow_id="WF011")
    assert result.status == "complete"
    assert result.output["count"] == 2


def test_trace_captures_route_tool_and_result(engine):
    result = engine.run("Find products where vendor price differs by more than 10%.")
    events = [event.event for event in result.trace]
    assert events[0] == "routing"
    assert "tool_call" in events
    assert "step_result" in events
    assert events[-1] == "workflow_complete"


def test_gemini_failures_are_reported_and_not_counted_as_successful_llm(workflows):
    class BrokenGemini(GeminiService):
        def __init__(self):
            super().__init__(api_key=None, model="gemini-test")
        @property
        def enabled(self):
            return True
        def generate_json(self, prompt, list_key=None):
            raise ConnectionError("simulated Gemini 503")

    llm = BrokenGemini()
    engine = WorkflowEngine(workflows, ToolRegistry(llm), WorkflowRouter(workflows, llm))
    result = engine.run("Generate SEO content for this product.", {"product": {"name": "Cup", "category": "Drinkware", "attributes": ["lid"], "material": "steel", "color": "blue", "target_audience": "commuters"}})
    assert result.status == "failed"
    assert result.llm_usage == [{"stage": "workflow_selection_and_extraction", "provider": "Local fallback after Gemini error", "model": "keyword router", "retries": 0}]
    assert [item["stage"] for item in result.llm_errors] == ["workflow_selection_and_extraction", "product_content"]
    assert "simulated Gemini 503" in result.llm_errors[-1]["error"]
