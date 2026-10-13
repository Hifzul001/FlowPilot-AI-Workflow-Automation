# Final Test and Requirement Coverage Report

Generated: 2026-10-13 15:48 UTC

## Exact recruiter requests

Requests and evaluation focus were read directly from the preserved `data/assessment.xlsx` `Test_Questions` sheet. They were executed through automatic routing and the shared workflow engine in deterministic local mode. Each listed tool is taken from an actual `tool_call` trace event.

| ID | Exact request | Recruiter check | Result | Selected workflow | Trace tool calls |
|---|---|---|---|---|---|
| WF001 | Which products need restocking? | Tests workflow selection and threshold logic | complete | WF001 | inventory_restock |
| WF002 | Find products where vendor price differs by more than 10%. | Tests comparison and decision logic | complete | WF002 | price_validation |
| WF003 | Process this vendor spreadsheet and show invalid rows. | Tests file ingestion and validation | needs_input | WF003 | none (input validation) |
| WF004 | Generate SEO content for this product. | Tests LLM workflow and missing-data handling | needs_input | WF004 | none (input validation) |
| WF005 | Where is order ORD-1001? | Tests lookup and missing-order handling | complete | WF005 | order_lookup |
| WF006 | Find likely duplicate products in the catalog. | Tests similarity and confidence | complete | WF006 | duplicate_detection |
| WF007 | Create a campaign brief for the new collection. | Tests structured content generation | needs_input | WF007 | none (input validation) |
| WF008 | Classify these keywords and map them to pages. | Tests classification and mapping | needs_input | WF008 | none (input validation) |
| WF009 | Assign this urgent task to the best available developer. | Tests ranking and decision logic | complete | WF009 | task_assignment |
| WF010 | Which workflows are failing most often? | Tests aggregation and reporting | complete | WF010 | performance_report |

## Missing-input and completed execution coverage

| ID | Case | Result | Observed output | Trace tool calls |
|---|---|---|---|---|
| WF003 | Missing upload | needs_input | ['upload'] | none (input validation) |
| WF003 | Valid vendor CSV upload | complete | cleaned=1; invalid=2 | vendor_file_process |
| WF004 | Missing product attributes | needs_input | ['product'] | none (input validation) |
| WF004 | Complete product attributes | complete | fields=product_description,short_description,seo_title,meta_description; provider=Local fallback | product_content |
| WF005 | Missing order identifier | needs_input | ['order_id or email'] | none (input validation) |
| WF005 | Valid order ID ORD-1001 | complete | order_status=Shipped | order_lookup |
| WF007 | Missing campaign goal and dates | needs_input | ['goal', 'start_date', 'end_date'] | none (input validation) |
| WF007 | Complete campaign inputs | complete | has_objective=True; provider=Local fallback | campaign_brief |
| WF008 | Missing keyword list | needs_input | ['keywords'] | none (input validation) |
| WF008 | Complete keyword list | complete | classified=2; provider=Local fallback | keyword_classification |

## Trace and provider checks

- Every completed execution above includes one or more `tool_call` entries naming the shared registry tool actually invoked; missing-required-input cases stop before tool execution.
- Coverage report runs intentionally use deterministic local mode so results are reproducible and do not consume API quota. The Streamlit UI reports Gemini versus local fallback for each run.
- Live Gemini API verification and retry behavior are recorded separately in the final section below.

## Automated and live checks

- Full automated suite: **23 passed** (`python -m pytest -q`, 9.05 seconds; Python 3.13.2). Includes the Excel-based WF011 extensibility test, simulated transient/persistent 503 retry bounds, non-503 no-retry behavior, and failure provenance.
- Streamlit launch: **passed**. Started with `python -m streamlit run app.py --server.headless true --server.port 8502`; `http://localhost:8502` returned HTTP **200**.
- Live Gemini connection: **passed**. A real `google-genai` request to configured model `gemini-3.1-flash-lite` returned `{"connection_test":"ok"}`. The response identified the same model, with 0 retries. No credential was printed.
- Retry behavior: mocked tests verify a 503 sequence makes at most 3 total attempts (initial plus 2 retries) and waits 0.5s then 1.0s; a successful response records the retry metadata. Persistent 503 failures are raised and surfaced as errors.
- Git secret/output check: `.gitignore` contains rules for `.env`, `.env.*` (while allowing `.env.example`), common credential files, logs, execution logs, report/output/artifact folders, and generated sample-output names. An automated test verifies required patterns. This workspace has no `.git` repository, so `git check-ignore` could not be run against a Git index; nothing was published.

## Tested limitations and remaining issues

- Business services use fictional CSV fixtures and user-uploaded files; no live inventory, order, employee, vendor, or execution-log system is connected.
- Gemini availability depends on network access and the configured key/model. HTTP 503 is retried at most twice with exponential backoff; persistent API errors remain visible and are not presented as successful model output.
- Exact recruiter prompts for WF003, WF004, WF007, and WF008 omit required data by design; they return `needs_input`. Completed cases are shown above with the minimum valid inputs supplied.
