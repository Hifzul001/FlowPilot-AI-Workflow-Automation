# FlowPilot AI

FlowPilot AI is an Excel-driven business workflow automation platform powered by Python, Streamlit, and Google Gemini. It uses natural-language understanding to identify business workflows, extract required inputs, invoke registered tools, execute conditional logic, and return structured results with transparent execution traces.
The system supports 10 business workflows through a shared execution engine and reusable tool registry. It uses simulated operational datasets where external business APIs are unavailable.

## Run locally

Requires Python 3.11 or newer. Python 3.13.2 was used for the verified run.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Optional: edit .env and set GEMINI_API_KEY to enable Gemini calls
streamlit run app.py
```

Open the local URL printed by Streamlit (normally `http://localhost:8501`). For local deterministic mode, leave `GEMINI_API_KEY` empty. Requests route locally, and LLM-backed content/classification tools use a labeled fallback. With a key configured, `google-genai` calls the selected Gemini model for natural-language routing, product copy, campaign brief generation, and keyword classification. Transient Gemini HTTP 503 errors receive at most two retries with exponential backoff (0.5 and 1 second); the application labels the actual provider and surfaces API failures in the result and trace.

Run automated checks:

```powershell
python -m pytest -q
```

Regenerate the executable workbook after changing the original assessment workflow/test rows or the step mappings:

```powershell
python scripts/build_config.py
```

Regenerate the bundled synthetic datasets:

```powershell
python scripts/build_samples.py
```

## What is included

- A reusable Excel loader with Pydantic workflow/result models.
- A generic, declarative step engine with argument validation, conditional steps, trace events, and handled tool errors.
- One shared tool registry used by all configured workflows.
- Ten recruiter workflows, configured from the workbook rather than ten separate chatbots.
- Gemini integration through the official `google-genai` SDK, plus deterministic offline behavior for local evaluation.
- A Streamlit interface with workflow selection, JSON arguments, CSV/XLSX upload, results, trace details, and JSON/CSV report downloads.
- Synthetic sample datasets in `data/samples/`.

All simulated business data is fictional. No order, inventory, employee, vendor, or workflow-log API is contacted. Workflow results reflect only the sample files or user uploads.

## Recruiter workflow status

All ten exact recruiter requests are tested for routing. Tool scenarios requiring provided data run with the scenario fixture; requests with required information omitted return `needs_input` by design.

| ID | Workflow | Exact request behavior |
|---|---|---|
| WF001 | Inventory Restock Check | Complete. Reads inventory and returns products below their configured minimum stock. |
| WF002 | Product Price Validation | Complete. Matches SKU, calculates percent differences, and flags values strictly above 10%. |
| WF003 | Vendor File Processing | Needs upload if omitted; complete with cleaned rows and invalid-row report when a file is supplied. |
| WF004 | Product Description Generator | Requests missing product attributes; generates the four copy fields when all required attributes are supplied. |
| WF005 | Customer Order Status | Complete for ORD-1001; returns a request for another identifier when no order matches. |
| WF006 | Duplicate Product Detection | Complete. Reports exact SKU matches as definite and high name/attribute similarity as possible. |
| WF007 | Marketing Campaign Brief | Requests the campaign goal and dates when absent; generates the structured brief when supplied. |
| WF008 | SEO Keyword Classification | Requests a keyword list when absent; classifies, deduplicates, prioritizes, and maps supplied terms. |
| WF009 | Employee Task Assignment | Complete for the exact request; ranks the simulated available employee list. |
| WF010 | Workflow Performance Report | Complete. Aggregates simulated logs and reports failure rates, errors, slow steps, and recommendations. |

WF004/7/8 use a deterministic local fallback without a Gemini key. Tests do not make billable API calls; Gemini behavior is enabled at runtime through `.env`.

## Sample requests and results

Requests are copied verbatim from `Test_Questions` and can be loaded from the app:

- "Which products need restocking?" returns Canvas Tote and Linen Shirt from the bundled stock file.
- "Find products where vendor price differs by more than 10%." returns the matching SKUs and exception flags.
- "Process this vendor spreadsheet and show invalid rows." accepts a CSV/XLSX upload. `data/samples/vendor_upload_example.csv` has one clean and two invalid records.
- "Generate SEO content for this product." requires a JSON product object with name, category, attributes, material, color, and target audience.
- "Where is order ORD-1001?" returns its simulated status and tracking number.
- "Find likely duplicate products in the catalog." returns one definite and one possible duplicate group from `product_catalog.csv`.
- "Create a campaign brief for the new collection." requires goal, start date, and end date in the optional JSON input.
- "Classify these keywords and map them to pages." needs a keyword list, supplied as JSON or an uploaded list.
- "Assign this urgent task to the best available developer." ranks simulated employees.
- "Which workflows are failing most often?" aggregates `execution_logs.csv`.

Example product-content JSON:

```json
{
  "product": {
    "name": "Canvas Tote",
    "category": "Bags",
    "attributes": ["inner pocket", "reinforced handles"],
    "material": "Canvas",
    "color": "Natural",
    "target_audience": "commuters"
  }
}
```

## Add an 11th workflow using Excel

1. Open `data/workflows_config.xlsx` and add a row to `Workflows`.
2. Fill the original metadata columns: workflow ID, name, trigger, inputs, steps, decision logic, tools, and expected output.
3. Fill `Arguments_JSON` with argument names, types (`string`, `number`, `list`, `object`, `file`), `required`, and optional `default` values.
4. Fill `Executable_Steps_JSON` with ordered step objects. Use a registered tool name and argument placeholders such as `{{keywords}}`. Supported conditions use `when` with a `path`, `operator` (`equals`, `not_equals`, `exists`, `truthy`, `greater_than`), and `value`. A result can be stored with `save_as`.
5. Restart Streamlit. The loader picks up the new workflow without adding a new chatbot or changing engine code. You can select it by ID even if local keyword routing has no synonym rule yet. For automatic routing in offline mode, add terms to the local router; with Gemini configured, the workflow catalog is passed into the Gemini router.
6. Reuse an existing tool, or register a new reusable Python tool in `app/tools.py` and add it to `ToolRegistry`.

`tests/test_engine_features.py` demonstrates adding WF011 to a temporary configuration workbook and executing it using an existing tool.

## Files

- `data/assessment.xlsx`: recruiter source, unchanged.
- `data/workflows_config.xlsx`: executable workflow configuration plus copied test requests.
- `data/samples/`: fictional data used for local operation and tests.
- `app/`: loader, router, engine, Gemini adapter, models, and reusable tools.
- `tests/`: exact recruiter scenarios and validation, conditions, tool errors, traces, and extensibility.
- `docs/architecture.md`: architecture and execution lifecycle.
- `docs/loom-demo-script.md`: short recording walkthrough.
- `docs/final-test-report.md`: final requirement coverage and verification results.
