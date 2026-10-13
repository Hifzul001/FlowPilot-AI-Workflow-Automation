from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from app.config import WORKFLOW_CONFIG
from app.engine import WorkflowEngine
from app.llm import GeminiService
from app.loader import WorkflowLoader
from app.tools import ToolRegistry

SOURCE_BOOK = ROOT / "data" / "assessment.xlsx"
SAMPLE_VENDOR = ROOT / "data" / "samples" / "vendor_upload_example.csv"


class OfflineGemini(GeminiService):
    """Force deterministic fallback during workbook-coverage verification."""
    @property
    def enabled(self) -> bool:
        return False


def execute(engine, request, inputs=None):
    result = engine.run(request, inputs or {})
    calls = [e for e in result.trace if e.event == "tool_call"]
    return result, [e.data.get("tool") for e in calls]


def main() -> None:
    book = openpyxl.load_workbook(SOURCE_BOOK, data_only=True, read_only=True)
    questions = [row for row in book["Test_Questions"].iter_rows(min_row=2, values_only=True) if row[0]]
    book.close()
    workflows = WorkflowLoader(WORKFLOW_CONFIG).load()
    llm = OfflineGemini(api_key=None)
    engine = WorkflowEngine(workflows, ToolRegistry(llm))

    exact_rows = []
    by_id = {}
    for workflow_id, request, criterion in questions:
        result, calls = execute(engine, str(request))
        by_id[workflow_id] = (str(request), result, calls)
        exact_rows.append((workflow_id, str(request), str(criterion), result.status, result.workflow_id, calls))

    supplemental = []
    request = by_id["WF003"][0]
    missing, calls_missing = execute(engine, request)
    complete, calls_complete = execute(engine, request, {"upload": SAMPLE_VENDOR})
    supplemental.append(("WF003", "Missing upload", missing.status, missing.missing_inputs, calls_missing))
    supplemental.append(("WF003", "Valid vendor CSV upload", complete.status, f"cleaned={complete.output.get('cleaned_count')}; invalid={complete.output.get('invalid_count')}", calls_complete))

    request = by_id["WF004"][0]
    missing, calls_missing = execute(engine, request)
    product = {"name": "Canvas Tote", "category": "Bags", "attributes": ["inner pocket", "reinforced handles"], "material": "Canvas", "color": "Natural", "target_audience": "commuters"}
    complete, calls_complete = execute(engine, request, {"product": product})
    supplemental.append(("WF004", "Missing product attributes", missing.status, missing.missing_inputs, calls_missing))
    supplemental.append(("WF004", "Complete product attributes", complete.status, f"fields={','.join(k for k in ('product_description','short_description','seo_title','meta_description') if complete.output and k in complete.output)}; provider={complete.llm_usage[-1]['provider'] if complete.llm_usage else 'not reported'}", calls_complete))

    request = "Where is the order?"
    missing, calls_missing = execute(engine, request)
    valid, calls_valid = execute(engine, by_id["WF005"][0])
    supplemental.append(("WF005", "Missing order identifier", missing.status, missing.missing_inputs, calls_missing))
    supplemental.append(("WF005", "Valid order ID ORD-1001", valid.status, f"order_status={valid.output.get('order_status')}", calls_valid))

    request = by_id["WF007"][0]
    missing, calls_missing = execute(engine, request)
    campaign = {"goal": "launch the autumn collection", "products": ["Canvas Tote", "Linen Shirt"], "audience": "commuters", "promotion": "10% launch offer", "start_date": "2026-11-01", "end_date": "2026-11-14"}
    complete, calls_complete = execute(engine, request, campaign)
    supplemental.append(("WF007", "Missing campaign goal and dates", missing.status, missing.missing_inputs, calls_missing))
    supplemental.append(("WF007", "Complete campaign inputs", complete.status, f"has_objective={bool(complete.output and complete.output.get('objective'))}; provider={complete.llm_usage[-1]['provider'] if complete.llm_usage else 'not reported'}", calls_complete))

    request = by_id["WF008"][0]
    missing, calls_missing = execute(engine, request)
    complete, calls_complete = execute(engine, request, {"keywords": ["buy canvas tote", "best canvas tote", "buy canvas tote"], "category": "Bags"})
    supplemental.append(("WF008", "Missing keyword list", missing.status, missing.missing_inputs, calls_missing))
    supplemental.append(("WF008", "Complete keyword list", complete.status, f"classified={complete.output.get('count')}; provider={complete.llm_usage[-1]['provider'] if complete.llm_usage else 'not reported'}", calls_complete))

    lines = [
        "# Final Test and Requirement Coverage Report", "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", "",
        "## Exact recruiter requests", "",
        "Requests and evaluation focus were read directly from the preserved `data/assessment.xlsx` `Test_Questions` sheet. They were executed through automatic routing and the shared workflow engine in deterministic local mode. Each listed tool is taken from an actual `tool_call` trace event.", "",
        "| ID | Exact request | Recruiter check | Result | Selected workflow | Trace tool calls |", "|---|---|---|---|---|---|",
    ]
    for wid, req, criterion, status, selected, calls in exact_rows:
        lines.append(f"| {wid} | {req.replace('|', '\\|')} | {criterion.replace('|', '\\|')} | {status} | {selected or 'none'} | {', '.join(calls) if calls else 'none (input validation)'} |")
    lines += ["", "## Missing-input and completed execution coverage", "", "| ID | Case | Result | Observed output | Trace tool calls |", "|---|---|---|---|---|"]
    for wid, case, status, observed, calls in supplemental:
        lines.append(f"| {wid} | {case} | {status} | {str(observed).replace('|', '\\|')} | {', '.join(calls) if calls else 'none (input validation)'} |")
    lines += ["", "## Trace and provider checks", "", "- Every completed execution above includes one or more `tool_call` entries naming the shared registry tool actually invoked; missing-required-input cases stop before tool execution.", "- Coverage report runs intentionally use deterministic local mode so results are reproducible and do not consume API quota. The Streamlit UI reports Gemini versus local fallback for each run.", "- Live Gemini API verification and retry behavior are recorded separately in the final section below.", "", "## Automated and live checks", "", "Final Pytest and Streamlit launch results are added after the verification run.", "", "## Tested limitations and remaining issues", "", "- Business services use fictional CSV fixtures and user-uploaded files; no live inventory, order, employee, vendor, or execution-log system is connected.", "- Gemini availability depends on network access and the configured key/model. HTTP 503 is retried at most twice with exponential backoff; persistent API errors remain visible and are not presented as successful model output.", "- Exact recruiter prompts for WF003, WF004, WF007, and WF008 omit required data by design; they return `needs_input`. Completed cases are shown above with the minimum valid inputs supplied.", ""]
    path = ROOT / "docs" / "final-test-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)} with {len(exact_rows)} exact cases and {len(supplemental)} supplemental cases.")

if __name__ == "__main__":
    main()
