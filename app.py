from __future__ import annotations

import json
from typing import Any

import streamlit as st

from app.config import DATA_DIR, WORKFLOW_CONFIG
from app.engine import WorkflowEngine
from app.loader import WorkflowLoader
from app.llm import GeminiService
from app.tools import ToolRegistry


st.set_page_config(page_title="FlowPilot AI", page_icon="⚙️", layout="wide")

st.markdown(
    """
    <style>
    section.main > div.block-container {
        max-width: 1540px;
        padding-top: 1.4rem;
        padding-bottom: 3rem;
    }
    @media (max-width: 760px) {
        section.main > div.block-container {
            padding: 1rem 0.8rem 2rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_config():
    return WorkflowLoader(WORKFLOW_CONFIG).load()


@st.cache_data
def load_recruiter_questions() -> list[tuple[str, str]]:
    import openpyxl

    workbook = openpyxl.load_workbook(WORKFLOW_CONFIG, data_only=True, read_only=True)
    try:
        return [
            (str(row[0]), str(row[1]))
            for row in workbook["Test_Questions"].iter_rows(min_row=2, values_only=True)
            if row and row[0] and row[1]
        ]
    finally:
        workbook.close()


def populate_request(request: str) -> None:
    """Load a workbook scenario into the existing request control."""
    st.session_state["request"] = request


def status_style(status: str) -> tuple[str, str]:
    return {
        "complete": ("Completed", "green"),
        "needs_input": ("Needs input", "orange"),
        "failed": ("Failed", "red"),
        "not_found": ("Not found", "orange"),
        "escalate": ("Escalation", "orange"),
    }.get(status, (status.replace("_", " ").title() or "Unknown", "blue"))


def number_or_zero(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def render_table(rows: Any, *, key: str) -> None:
    if isinstance(rows, list) and rows:
        st.dataframe(rows, width="stretch", hide_index=True, key=key)
    elif isinstance(rows, list):
        st.caption("No rows returned.")


def render_workflow_output(workflow_id: str | None, output: Any) -> None:
    """Present useful summaries while keeping the complete backend output accessible."""
    if not isinstance(output, dict):
        if output is not None:
            st.write(output)
        return

    if workflow_id == "WF001":
        products = output.get("products", [])
        units = sum(number_or_zero(row.get("suggested_reorder_quantity")) for row in products if isinstance(row, dict))
        first, second = st.columns(2)
        first.metric("Products to restock", output.get("count", len(products)))
        second.metric("Units to reorder", int(units) if units.is_integer() else units)
        render_table(products, key="wf001-products")

    elif workflow_id == "WF002":
        first, second, third = st.columns(3)
        first.metric("Products checked", output.get("matched_count", 0))
        second.metric("Pricing exceptions", output.get("exception_count", 0))
        third.metric("Threshold", f"{output.get('threshold_pct', 0)}%")
        render_table(output.get("products", []), key="wf002-products")

    elif workflow_id == "WF003":
        cleaned = output.get("cleaned_rows", [])
        invalid = output.get("invalid_rows", [])
        first, second, third = st.columns(3)
        first.metric("Rows processed", len(cleaned) + len(invalid))
        second.metric("Valid rows", output.get("cleaned_count", len(cleaned)))
        third.metric("Invalid rows", output.get("invalid_count", len(invalid)))
        if cleaned:
            st.markdown("**Cleaned records**")
            render_table(cleaned, key="wf003-cleaned")
        if invalid:
            st.markdown("**Rows needing correction**")
            render_table(invalid, key="wf003-invalid")

    elif workflow_id == "WF004":
        fields = (
            ("Product description", "product_description"),
            ("Short description", "short_description"),
            ("SEO title", "seo_title"),
            ("Meta description", "meta_description"),
        )
        displayed = False
        for label, key in fields:
            if output.get(key):
                st.markdown(f"**{label}**")
                st.write(output[key])
                displayed = True
        if not displayed and output.get("message"):
            st.info(output["message"])

    elif workflow_id == "WF005":
        if output.get("status") == "found":
            first, second, third = st.columns(3)
            first.metric("Order", str(output.get("order_id", "—")))
            second.metric("Status", str(output.get("order_status", "—")))
            third.metric("Tracking", str(output.get("tracking_number", "—")))
        elif output.get("message"):
            st.info(output["message"])

    elif workflow_id == "WF006":
        groups = output.get("groups", [])
        definite = sum(group.get("confidence") == "definite" for group in groups if isinstance(group, dict))
        possible = sum(group.get("confidence") == "possible" for group in groups if isinstance(group, dict))
        first, second, third = st.columns(3)
        first.metric("Duplicate groups", output.get("duplicate_group_count", len(groups)))
        second.metric("Definite", definite)
        third.metric("Possible", possible)
        for index, group in enumerate(groups):
            title = f"{str(group.get('confidence', 'Group')).title()} match · {len(group.get('products', []))} products"
            with st.expander(title, key=f"wf006-group-{index}"):
                if group.get("matching_fields"):
                    st.caption("Matching evidence: " + ", ".join(map(str, group["matching_fields"])))
                render_table(group.get("products", []), key=f"wf006-products-{index}")

    elif workflow_id == "WF007":
        if output.get("objective"):
            st.markdown("**Objective**")
            st.write(output["objective"])
        if output.get("audience"):
            st.markdown("**Audience**")
            st.write(output["audience"])
        if output.get("messaging"):
            st.markdown("**Messaging**")
            st.write(output["messaging"])
        channels = output.get("channels")
        if channels:
            st.markdown("**Recommended channels**")
            st.write(" · ".join(map(str, channels)) if isinstance(channels, list) else channels)
        if output.get("timeline"):
            st.markdown("**Timeline**")
            st.json(output["timeline"])
        if output.get("checklist"):
            st.markdown("**Checklist**")
            for item in output["checklist"]:
                st.markdown(f"- {item}")
        if output.get("message"):
            st.info(output["message"])

    elif workflow_id == "WF008":
        if output.get("count") is not None:
            st.metric("Keywords classified", output["count"])
        render_table(output.get("results", []), key="wf008-results")
        if output.get("message"):
            st.info(output["message"])

    elif workflow_id == "WF009":
        if output.get("recommended_employee"):
            first, second = st.columns(2)
            first.metric("Recommended employee", output["recommended_employee"])
            if output.get("capacity_pct") is not None:
                second.metric("Current workload", f"{output['capacity_pct']}%")
            if output.get("matched_skills"):
                st.caption("Matched skills: " + ", ".join(map(str, output["matched_skills"])))
            if output.get("reasoning"):
                st.write(output["reasoning"])
        if output.get("message"):
            st.warning(output["message"])
        render_table(output.get("ranked_candidates", []), key="wf009-candidates")

    elif workflow_id == "WF010":
        workflows_report = output.get("workflows", [])
        if output.get("workflow_count") is not None:
            st.metric("Workflows analyzed", output["workflow_count"])
        render_table(workflows_report, key="wf010-workflows")
        if output.get("slow_steps"):
            st.markdown("**Slowest measured steps**")
            render_table(output["slow_steps"], key="wf010-slow-steps")
        if output.get("recommendations"):
            st.markdown("**Recommendations**")
            for item in output["recommendations"]:
                st.markdown(f"- {item}")

    else:
        # Future Excel-defined workflows still get a generic structured view.
        for key in ("products", "results", "workflows", "cleaned_rows", "invalid_rows"):
            if isinstance(output.get(key), list):
                st.markdown(f"**{key.replace('_', ' ').title()}**")
                render_table(output[key], key=f"generic-{key}")
        if output.get("message"):
            st.info(output["message"])

    with st.expander("Complete structured output", expanded=False):
        st.json(output)


def render_downloads(result: dict[str, Any]) -> None:
    import pandas as pd

    output = result.get("output")
    workflow_id = result.get("workflow_id") or "flowpilot"
    json_report = json.dumps(result, indent=2, default=str, ensure_ascii=False)
    st.download_button(
        "Download JSON report",
        json_report,
        file_name=f"{workflow_id}-report.json",
        mime="application/json",
        width="stretch",
        key="download-json-report",
    )
    if not isinstance(output, dict):
        return
    if output.get("cleaned_rows") is not None:
        left, right = st.columns(2)
        with left:
            st.download_button(
                "Download cleaned vendor CSV",
                pd.DataFrame(output.get("cleaned_rows", [])).to_csv(index=False),
                file_name="vendor-cleaned.csv",
                mime="text/csv",
                width="stretch",
                key="download-vendor-cleaned",
            )
        with right:
            st.download_button(
                "Download invalid rows CSV",
                pd.DataFrame(output.get("invalid_rows", [])).to_csv(index=False),
                file_name="vendor-invalid-rows.csv",
                mime="text/csv",
                width="stretch",
                key="download-vendor-invalid",
            )
    if isinstance(output.get("results"), list):
        st.download_button(
            "Download results CSV",
            pd.DataFrame(output["results"]).to_csv(index=False),
            file_name=f"{workflow_id}-results.csv",
            mime="text/csv",
            width="stretch",
            key="download-results-csv",
        )


def render_execution_trace(result: dict[str, Any]) -> None:
    events = result.get("trace") or []
    event_labels = {
        "routing": "Workflow routing",
        "validation": "Input validation",
        "tool_call": "Tool call",
        "step_result": "Step result",
        "tool_error": "Tool error",
        "condition_error": "Condition error",
        "step_skipped": "Conditional step skipped",
        "workflow_complete": "Workflow complete",
    }
    if not events:
        st.caption("No execution events are recorded for this result.")
        return

    actual_stages = []
    for event in events:
        event_type = event.get("event", "event")
        label = event_labels.get(event_type, event_type.replace("_", " ").title())
        tool = (event.get("data") or {}).get("tool")
        actual_stages.append(f"{label} · {tool}" if event_type == "tool_call" and tool else label)
    st.caption("  →  ".join(actual_stages))

    for index, event in enumerate(events, start=1):
        event_type = event.get("event", "event")
        label = event_labels.get(event_type, event_type.replace("_", " ").title())
        message = event.get("message", "")
        with st.expander(f"{index:02d} · {label} · {message}", expanded=False):
            if event.get("timestamp"):
                st.caption(event["timestamp"])
            st.json(event.get("data", {}))

    with st.expander("Raw execution trace JSON", expanded=False):
        st.json(events)


workflows = load_config()
llm = GeminiService()
engine = WorkflowEngine(workflows, ToolRegistry(llm))
questions = load_recruiter_questions()
workflow_by_id = workflows

with st.sidebar:
    st.markdown("### Workflow catalog")
    st.caption(f"{len(workflows)} configured · Excel-driven")
    catalog_filter = st.text_input("Find a workflow", placeholder="Search IDs or names", key="catalog_filter")
    with st.expander("Browse workflows", expanded=False):
        for workflow in workflows.values():
            searchable = f"{workflow.workflow_id} {workflow.name}".casefold()
            if catalog_filter.casefold() not in searchable:
                continue
            st.markdown(f"**{workflow.workflow_id}** · {workflow.name}")
    st.divider()
    if llm.enabled:
        st.caption(f"Gemini key loaded · {llm.model}")
    else:
        st.caption("Gemini key not configured · local fallback available")
    st.caption("Each run reports the provider actually used.")

st.title("FlowPilot AI")
st.caption("Intelligent Business Workflow Automation")
st.caption(f"{len(workflows)} workflows  ·  Excel-configured  ·  Gemini integration")

request_column, quick_start_column = st.columns([1, 1], gap="medium")
with request_column:
    with st.container(border=True):
        st.subheader("1. Request")
        st.caption("Describe what you need the agent to do")
        request = st.text_area(
            "Natural-language request",
            placeholder="Which products need restocking?",
            height=100,
            key="request",
            label_visibility="collapsed",
        )
        with st.expander("Attach an optional CSV/XLSX file"):
            upload = st.file_uploader(
                "Vendor or workflow file",
                type=["csv", "xlsx"],
                key="workflow_upload",
                help="The file is passed to the selected workflow as uploaded.",
            )
        go = st.button("Run workflow", type="primary", width="stretch", key="run_workflow")

with quick_start_column:
    with st.container(border=True):
        st.subheader("2. Quick start")
        st.caption("Recruiter test scenarios")
        question_labels = {
            workflow_id: next((wf.name for wf in workflows.values() if wf.workflow_id == workflow_id), workflow_id)
            for workflow_id, _ in questions
        }
        labels = [f"{workflow_id} · {question_labels[workflow_id]}" for workflow_id, _ in questions]
        request_by_label = {label: request_text for label, (_, request_text) in zip(labels, questions)}
        picked = st.selectbox(
            "Select an assessment request",
            ["Choose a scenario"] + labels,
            key="scenario_selection",
            label_visibility="collapsed",
        )
        scenario_request = request_by_label.get(picked)
        if scenario_request:
            st.code(scenario_request, language=None)
        else:
            st.caption("Choose a workbook scenario to preview its exact request.")
        st.button(
            "Use recruiter request",
            width="stretch",
            disabled=not scenario_request,
            on_click=populate_request,
            args=(scenario_request,) if scenario_request else (),
            key="load_recruiter_request",
        )
        with st.expander("Advanced options", expanded=False):
            route_options = {"Automatic routing": None}
            route_options.update({f"{wf.workflow_id} · {wf.name}": wf.workflow_id for wf in workflows.values()})
            route_label = st.selectbox("Route to", list(route_options), key="workflow_override")
            extra_text = st.text_area(
                "Optional workflow inputs (JSON)",
                value="{}",
                height=105,
                key="extra_text",
                help="Provide structured values such as a product object, keyword list, campaign goal, or dates.",
            )

if go:
    try:
        extras = json.loads(st.session_state.get("extra_text", "{}") or "{}")
        if not isinstance(extras, dict):
            raise ValueError("Optional inputs must be a JSON object.")
        if upload is not None:
            extras["upload"] = upload
        selected_route = st.session_state.get("workflow_override", "Automatic routing")
        manual_workflow_id = None
        if selected_route != "Automatic routing":
            manual_workflow_id = selected_route.split(" · ", 1)[0]
        with st.spinner("Routing the request and executing configured workflow steps…"):
            result = engine.run(request, extras, workflow_id=manual_workflow_id)
        st.session_state["last_result"] = result.model_dump(mode="json")
    except Exception as exc:
        st.error(f"Could not run workflow: {exc}")

result = st.session_state.get("last_result")

with st.container(border=True):
    st.subheader("3. Workflow result")
    if not result:
        st.caption("Run a request to see the selected workflow, live results, and downloads.")
    else:
        workflow_id = result.get("workflow_id")
        workflow_name = result.get("workflow_name")
        status_label, status_color = status_style(result.get("status", "unknown"))
        title_left, title_right = st.columns([5, 1])
        with title_left:
            display_title = " · ".join(part for part in (workflow_id, workflow_name) if part) or "Workflow result"
            st.markdown(f"#### {display_title}")
        with title_right:
            st.markdown(f"**Status:** :{status_color}[{status_label}]")

        llm_usage = result.get("llm_usage") or []
        llm_errors = result.get("llm_errors") or []
        route_usage = next((item for item in llm_usage if item.get("stage") == "workflow_selection_and_extraction"), None)
        route_provider = (route_usage or {}).get("provider", "")
        tool_names = [
            event.get("data", {}).get("tool")
            for event in result.get("trace", [])
            if event.get("event") == "tool_call" and event.get("data", {}).get("tool")
        ]
        details = []
        if route_provider == "Gemini":
            details.append("Routed by Gemini")
        elif route_provider.startswith("Local fallback"):
            details.append("Local fallback routing")
        elif route_provider == "Manual selection":
            details.append("Manually selected workflow")
        if tool_names:
            details.append("Tool called: " + ", ".join(tool_names))
        if details:
            st.caption("  ·  ".join(details))

        for usage in llm_usage:
            stage = usage.get("stage", "LLM execution").replace("_", " ").title()
            provider = usage.get("provider", "Unknown provider")
            model = usage.get("model")
            retry_count = usage.get("retries", 0)
            delays = usage.get("retry_delays_seconds") or []
            retry_text = f" · {retry_count} retries" if retry_count else ""
            if delays:
                retry_text += " (backoff " + ", ".join(f"{delay:g}s" for delay in delays) + ")"
            model_text = f" · {model}" if model else ""
            st.caption(f"{stage}: **{provider}**{model_text}{retry_text}")

        route_failed = any(item.get("stage") == "workflow_selection_and_extraction" for item in llm_errors)
        if route_failed and route_provider.startswith("Local fallback"):
            st.warning("Gemini routing was unavailable; this request continued with local fallback.")
        generation_failed = any(item.get("stage") != "workflow_selection_and_extraction" for item in llm_errors)
        if generation_failed:
            st.error("A Gemini-backed content or classification step failed. Its output is not reported as a successful model result.")
        if llm_errors:
            with st.expander("Gemini/API technical details", expanded=False):
                st.json(llm_errors)

        if result.get("missing_inputs"):
            st.warning("Missing information: " + ", ".join(result["missing_inputs"]))
        if result.get("error"):
            st.error(result["error"])

        output = result.get("output")
        render_workflow_output(workflow_id, output)
        st.divider()
        render_downloads(result)

with st.container(border=True):
    st.subheader("4. Execution trace")
    if result:
        render_execution_trace(result)
    else:
        st.caption("Actual routing, validation, tool calls, and results will appear here after a run.")

definition_tab, data_tab = st.tabs(["Workflow definitions", "Sample data"])
with definition_tab:
    st.caption("Definitions are loaded from `data/workflows_config.xlsx`; the original recruiter workbook remains at `data/assessment.xlsx`.")
    for workflow in workflows.values():
        with st.expander(f"{workflow.workflow_id} · {workflow.name}"):
            st.markdown(f"**Trigger:** {workflow.trigger}")
            st.markdown(f"**Inputs:** {workflow.inputs}")
            st.markdown(f"**Steps:** {workflow.steps}")
            st.markdown(f"**Decision logic:** {workflow.decision_logic}")
            st.markdown(f"**Tools:** {workflow.tools_required}")
            st.markdown(f"**Expected output:** {workflow.expected_output}")
            st.json({"arguments": workflow.arguments, "executable_steps": workflow.executable_steps})

with data_tab:
    st.caption("Fictional sample data for local execution. No external business system is contacted.")
    for path in sorted(DATA_DIR.glob("*.csv")):
        with st.expander(path.name):
            import pandas as pd

            st.dataframe(pd.read_csv(path), width="stretch", hide_index=True)
