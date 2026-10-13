from __future__ import annotations

import openpyxl
import pandas as pd

from app.config import WORKFLOW_CONFIG


def scenarios():
    workbook = openpyxl.load_workbook(WORKFLOW_CONFIG, data_only=True, read_only=True)
    return [(row[0], row[1]) for row in workbook["Test_Questions"].iter_rows(min_row=2, values_only=True) if row[0]]


def test_all_exact_recruiter_scenarios_are_routable(engine):
    for expected_id, request in scenarios():
        wf, _, method = engine.router.route(request)
        assert wf is not None, request
        assert wf.workflow_id == expected_id
        assert method == "local"


def test_wf001_exact_request_executes_inventory_tool(engine):
    result = engine.run("Which products need restocking?")
    assert result.status == "complete"
    assert result.workflow_id == "WF001"
    assert {p["sku"] for p in result.output["products"]} == {"SKU-100", "SKU-102"}
    assert [e.event for e in result.trace].count("tool_call") == 1


def test_wf002_exact_request_checks_over_ten_percent(engine):
    result = engine.run("Find products where vendor price differs by more than 10%.")
    assert result.workflow_id == "WF002"
    assert result.status == "complete"
    assert result.output["exception_count"] == 2
    assert all(row["difference_pct"] > 10 for row in result.output["products"] if row["exception"])


def test_wf003_exact_request_handles_upload_and_invalid_rows(engine, sample_dir):
    request = "Process this vendor spreadsheet and show invalid rows."
    missing = engine.run(request)
    assert missing.status == "needs_input"
    result = engine.run(request, {"upload": sample_dir / "vendor_upload_example.csv"})
    assert result.status == "complete"
    assert result.output["cleaned_count"] == 1
    assert result.output["invalid_count"] == 2
    assert len(result.output["invalid_rows"]) == 2


def test_wf003_reads_xlsx_upload(engine, tmp_path):
    path = tmp_path / "vendor.xlsx"
    pd.DataFrame([{"Product SKU": "X-1", "Product Name": "Test Item"}, {"Product SKU": "", "Product Name": "Invalid"}]).to_excel(path, index=False)
    result = engine.run("Process this vendor spreadsheet and show invalid rows.", {"upload": path})
    assert result.status == "complete"
    assert result.output["cleaned_count"] == 1
    assert result.output["invalid_count"] == 1


def test_wf004_exact_request_marks_missing_attributes(engine):
    request = "Generate SEO content for this product."
    result = engine.run(request, {"product": {"name": "Canvas Tote", "category": "Bags", "material": "Canvas"}})
    assert result.workflow_id == "WF004"
    assert result.status == "needs_input"
    assert set(result.missing_inputs) == {"attributes", "color", "target_audience"}
    assert "invented" in result.output["message"]


def test_wf004_generates_copy_when_complete(engine):
    result = engine.run("Generate SEO content for this product.", {"product": {"name": "Canvas Tote", "category": "Bags", "attributes": ["inner pocket"], "material": "Canvas", "color": "Natural", "target_audience": "commuters"}})
    assert result.status == "complete"
    assert result.output["seo_title"] == "Canvas Tote | Bags"
    assert result.output["mode"] == "local_fallback"


def test_wf005_order_lookup_and_missing_order(engine):
    result = engine.run("Where is order ORD-1001?")
    assert result.workflow_id == "WF005"
    assert result.output["order_status"] == "Shipped"
    assert result.output["tracking_number"] == "TRK-449210"
    missing = engine.run("Where is order ORD-9999?")
    assert missing.status == "not_found"
    assert "another order ID" in missing.output["message"]


def test_wf006_duplicate_detection(engine):
    result = engine.run("Find likely duplicate products in the catalog.")
    assert result.workflow_id == "WF006"
    assert result.status == "complete"
    assert any(group["confidence"] == "definite" for group in result.output["groups"])
    assert any(group["confidence"] == "possible" for group in result.output["groups"])


def test_wf007_exact_request_requires_goal_and_dates_then_builds_brief(engine):
    request = "Create a campaign brief for the new collection."
    missing = engine.run(request)
    assert missing.workflow_id == "WF007"
    assert missing.status == "needs_input"
    assert set(missing.missing_inputs) == {"goal", "start_date", "end_date"}
    result = engine.run(request, {"goal": "launch the autumn collection", "products": ["Canvas Tote", "Linen Shirt"], "audience": "commuters", "start_date": "2026-11-01", "end_date": "2026-11-14"})
    assert result.status == "complete"
    assert result.output["timeline"]["start"] == "2026-11-01"
    assert result.output["checklist"]


def test_wf008_exact_request_classifies_deduplicated_keywords(engine):
    request = "Classify these keywords and map them to pages."
    missing = engine.run(request)
    assert missing.workflow_id == "WF008"
    assert missing.status == "needs_input"
    result = engine.run(request, {"keywords": ["buy canvas tote", "best canvas tote", "buy canvas tote"], "category": "Bags"})
    assert result.status == "complete"
    assert result.output["count"] == 2
    assert {r["intent"] for r in result.output["results"]} == {"transactional", "commercial"}


def test_wf009_exact_request_ranks_available_developer(engine):
    result = engine.run("Assign this urgent task to the best available developer.")
    assert result.workflow_id == "WF009"
    assert result.status == "complete"
    assert result.output["recommended_employee"] == "Noah Kim"
    assert result.output["priority"] == "urgent"


def test_wf010_exact_request_aggregates_failures(engine):
    result = engine.run("Which workflows are failing most often?")
    assert result.workflow_id == "WF010"
    assert result.status == "complete"
    by_id = {row["workflow_id"]: row for row in result.output["workflows"]}
    assert by_id["WF002"]["failure_rate_pct"] == 66.7
    assert "Vendor SKU missing" in by_id["WF002"]["frequent_errors"]
    assert result.output["slow_steps"]
