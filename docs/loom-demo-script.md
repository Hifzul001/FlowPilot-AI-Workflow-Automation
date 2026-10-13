# Loom demonstration script (about 3 minutes)

1. **Open the app (15 sec).** Start with `streamlit run app.py`. Point out that ten workflows and the recruiter scenarios are loaded from the executable Excel configuration. Mention that the original workbook is retained unchanged.
2. **Run a data workflow (35 sec).** Select the exact request "Which products need restocking?" and run it. Show the products table and expand the trace to show route, validation, tool call, and result.
3. **Show file processing (35 sec).** Use "Process this vendor spreadsheet and show invalid rows." Upload `data/samples/vendor_upload_example.csv`. Show the cleaned rows, invalid rows, and CSV downloads.
4. **Show missing-input behavior (30 sec).** Run "Generate SEO content for this product." with no product object or with only a name/category. Explain that missing product attributes are listed and no product facts are invented. Optionally paste the complete example JSON from README and rerun.
5. **Show a business decision/report (30 sec).** Run "Where is order ORD-1001?" or "Which workflows are failing most often?" and point out the simulated source data and result.
6. **Show extensibility and tests (35 sec).** Point to `data/workflows_config.xlsx` and its `Arguments_JSON`/`Executable_Steps_JSON` columns. Run `python -m pytest -q`; show the WF011 Excel-extension test.
7. **Close (10 sec).** Note that adding `GEMINI_API_KEY` enables real Gemini routing and generation, while the no-key mode is deterministic for local review.

Keep the demo on synthetic records and do not display a real API key. The end-to-end API call segment should only be recorded if a valid Gemini key is already configured in the local `.env`.
