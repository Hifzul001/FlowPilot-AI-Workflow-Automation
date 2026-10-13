# FlowPilot AI architecture

## Components

```text
Natural-language request + optional arguments/file
                 |
                 v
        WorkflowRouter ---- GeminiService (optional)
                 | workflow ID + extracted arguments
                 v
       WorkflowEngine <---- WorkflowLoader (Excel)
          | validate required/type constraints
          | evaluate optional step conditions
          v
       ToolRegistry ---- reusable Python functions
          |                 |
          |                 +-- synthetic CSV datasets
          |                 +-- uploaded vendor CSV/XLSX
          |                 +-- Gemini generation/classification
          v
 ExecutionResult (status, output, missing inputs, trace)
                 |
                 v
     Streamlit UI + JSON/CSV downloads
```

## Configuration and source of truth

`data/assessment.xlsx` remains untouched and captures the recruiter-provided workflow rows and scenarios. `scripts/build_config.py` copies those source fields into `data/workflows_config.xlsx` and adds two executable columns:

- `Arguments_JSON`: simple input schema, defaults, and required flags.
- `Executable_Steps_JSON`: ordered tool calls, argument references, optional conditions, and context save names.

`WorkflowLoader` validates the required column names, parses JSON definitions, and creates `Workflow` Pydantic models. `Test_Questions` is copied for UI display and for the tests to read the exact recruiter request strings.

## Runtime lifecycle

1. The router selects a workflow. With `GEMINI_API_KEY`, it asks Gemini for a workflow ID and extracted arguments using the workbook-derived catalog. Otherwise, deterministic keyword routing handles the included requests.
2. User-supplied JSON/file arguments override extracted arguments. The engine validates configured required inputs and types before calling tools. WF005 also accepts either an order ID or email.
3. Each step resolves argument/context placeholders, checks its optional condition, logs the call, and invokes the shared registry.
4. Tool results are stored in execution context. Business-level missing inputs become `needs_input`; unmatched orders become `not_found`; unsuitable staffing becomes `escalate`; raised tool exceptions become traced `failed` results.
5. The app displays the result and execution trace and offers JSON output plus CSV downloads where table output is available.

Trace events include route selection, validation, condition skips/errors, tool calls, results, tool errors, and workflow completion. Upload contents are omitted from the trace arguments; the report output itself is user-visible and downloadable.

## Reusable tool registry

Each registry tool is a normal Python function. The workflows share CSV reading, numeric calculation, validation, similarity, ranking, and report-building functions. The Excel step config selects and composes those tools. The business data is synthetic and local; no business API integration is claimed.

Gemini is isolated behind `GeminiService` and the `google-genai` package. The service is only constructed with an API key if one exists. Local mode keeps the app and test suite usable without credentials or network access. In connected mode, Gemini performs natural-language argument extraction/routing and creates structured product copy, campaign briefs, and keyword classifications.

## Extension

The engine does not dispatch on a fixed list of workflow IDs. It loads every configured row and invokes the `tool` names in that row. An additional workflow can therefore reuse an existing tool by adding a row to `workflows_config.xlsx`. Add a Python implementation only when the new workflow needs a capability that no existing registry tool supplies.

## Deliberate limits

- Gemini calls require a user-provided key and network availability. They are not needed by the deterministic test suite.
- The bundled business records are fictional. Replace or connect data sources before using it for operational decisions.
- Offline routing uses a small synonym dictionary. The UI provides explicit workflow selection when a phrasing is ambiguous or new.
- The report threshold for slow workflows is 15 seconds, an app-level threshold for this sample implementation because the recruiter workbook did not specify a value.
