from __future__ import annotations

import difflib
import io
import json
import re
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from app.config import DATA_DIR
from app.llm import GeminiService


def _read_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Simulated dataset not found: {path.name}")
    return pd.read_csv(path)


def _frame_from_upload(upload: Any) -> pd.DataFrame:
    if upload is None:
        raise ValueError("Upload a vendor CSV or XLSX file to continue.")
    if isinstance(upload, pd.DataFrame):
        return upload.copy()
    if isinstance(upload, (str, Path)):
        path = Path(upload)
        if not path.exists(): raise FileNotFoundError(f"Uploaded file not found: {path}")
        return pd.read_excel(path) if path.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(path)
    name = getattr(upload, "name", "upload.csv")
    data = upload.getvalue() if hasattr(upload, "getvalue") else upload
    if not isinstance(data, bytes): raise ValueError("Upload must be CSV or XLSX bytes.")
    return pd.read_excel(io.BytesIO(data)) if str(name).lower().endswith((".xlsx", ".xls")) else pd.read_csv(io.BytesIO(data))


def inventory_restock(threshold: float | None = None, **_: Any) -> dict[str, Any]:
    df = _read_csv("inventory.csv")
    if threshold is None:
        low = df[df.current_stock < df.minimum_stock].copy()
        low["threshold"] = low.minimum_stock
    else:
        low = df[df.current_stock < threshold].copy()
        low["threshold"] = threshold
    low["suggested_reorder_quantity"] = (low.minimum_stock - low.current_stock).clip(lower=0)
    rows = low[["sku", "product_name", "current_stock", "threshold", "suggested_reorder_quantity"]].to_dict("records")
    return {"threshold": threshold, "count": len(rows), "products": rows}


def price_validation(threshold_pct: float = 10, **_: Any) -> dict[str, Any]:
    products = _read_csv("products.csv")
    vendors = _read_csv("vendor_prices.csv")
    merged = products.merge(vendors, on="sku", how="inner", suffixes=("_internal", "_vendor"))
    merged["difference_pct"] = ((merged.internal_price - merged.vendor_price).abs() / merged.vendor_price.replace(0, pd.NA) * 100).fillna(0)
    merged["exception"] = merged.difference_pct > threshold_pct
    selected = merged[["sku", "product_name", "internal_price", "vendor_price", "difference_pct", "exception"]]
    return {"matched_count": len(selected), "exception_count": int(selected.exception.sum()), "threshold_pct": threshold_pct, "products": selected.round({"difference_pct": 2}).to_dict("records")}


def vendor_file_process(upload: Any = None, **_: Any) -> dict[str, Any]:
    frame = _frame_from_upload(upload)
    original_columns = [str(c) for c in frame.columns]
    frame.columns = [re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_") for c in frame.columns]
    aliases = {"product": "product_name", "name": "product_name", "productname": "product_name", "item_name": "product_name", "stock_keeping_unit": "sku", "product_sku": "sku"}
    frame = frame.rename(columns={c: aliases[c] for c in frame.columns if c in aliases})
    missing_columns = [field for field in ("sku", "product_name") if field not in frame.columns]
    if missing_columns:
        raise ValueError(f"Required columns missing: {', '.join(missing_columns)}. Found columns: {', '.join(frame.columns)}")
    frame["sku"] = frame.sku.fillna("").astype(str).str.strip()
    frame["product_name"] = frame.product_name.fillna("").astype(str).str.strip()
    invalid = frame.sku.eq("") | frame.product_name.eq("")
    invalid_rows = frame.loc[invalid].copy()
    invalid_rows["row_number"] = invalid_rows.index + 2
    clean = frame.loc[~invalid].copy()
    return {"source_columns": original_columns, "normalized_columns": list(frame.columns), "cleaned_rows": clean.to_dict("records"), "cleaned_count": len(clean), "invalid_count": int(invalid.sum()), "invalid_rows": invalid_rows.to_dict("records")}


def product_content(product: dict[str, Any] | None = None, llm: GeminiService | None = None, **_: Any) -> dict[str, Any]:
    product = product or {}
    required = ("name", "category", "attributes", "material", "color", "target_audience")
    missing = [key for key in required if product.get(key) in (None, "", [])]
    if missing:
        return {"status": "needs_input", "missing_attributes": missing, "message": "Provide the missing product attributes. No product facts were invented."}
    if llm and llm.enabled:
        generated = llm.generate_json("Create ecommerce copy using only these attributes. JSON keys: product_description, short_description, seo_title, meta_description. Attributes: " + json.dumps(product))
        required_keys = ("product_description", "short_description", "seo_title", "meta_description")
        absent = [key for key in required_keys if not generated.get(key)]
        if absent: raise ValueError(f"Gemini product copy is missing fields: {', '.join(absent)}")
        return generated
    name = product["name"]
    attrs = ", ".join(map(str, product["attributes"])) if isinstance(product["attributes"], list) else str(product["attributes"])
    description = f"The {name} is a {product['color']} {product['material']} {product['category']} for {product['target_audience']}. Features include {attrs}."
    return {"status": "complete", "mode": "local_fallback", "product_description": description, "short_description": f"{product['color']} {product['material']} {product['category']} featuring {attrs}.", "seo_title": f"{name} | {product['category']}", "meta_description": f"Shop {name}, a {product['color']} {product['material']} {product['category']} for {product['target_audience']}."}


def order_lookup(order_id: str | None = None, email: str | None = None, **_: Any) -> dict[str, Any]:
    if not order_id and not email: return {"status": "needs_input", "message": "Provide an order ID or customer email."}
    df = _read_csv("orders.csv")
    matches = df[(df.order_id.str.upper() == str(order_id).upper())] if order_id else df[df.customer_email.str.lower() == str(email).lower()]
    if matches.empty: return {"status": "not_found", "message": "No order found. Please provide another order ID or customer email."}
    order = matches.iloc[0].to_dict()
    return {"status": "found", **order}


def duplicate_detection(**_: Any) -> dict[str, Any]:
    df = _read_csv("product_catalog.csv").fillna("")
    norm = lambda value: re.sub(r"[^a-z0-9]", "", str(value).lower())
    groups: list[dict[str, Any]] = []
    consumed: set[str] = set()
    rows = df.to_dict("records")
    for i, a in enumerate(rows):
        if a["sku"] in consumed: continue
        group = [a]
        for b in rows[i + 1:]:
            if a["sku"] == b["sku"]:
                group.append(b)
            else:
                similarity = difflib.SequenceMatcher(None, norm(a["product_name"]), norm(b["product_name"])).ratio()
                same_attrs = all(a.get(k) == b.get(k) for k in ("category", "color", "material"))
                if similarity >= 0.80 and same_attrs: group.append(b)
        if len(group) > 1:
            exact = len({x["sku"] for x in group}) < len(group)
            for x in group: consumed.add(x["sku"])
            groups.append({"products": group, "confidence": "definite" if exact else "possible", "matching_fields": ["sku"] if exact else ["product_name", "category", "color", "material"]})
    return {"duplicate_group_count": len(groups), "groups": groups}


def campaign_brief(goal: str | None = None, products: list[str] | None = None, audience: str | None = None, promotion: str | None = None, start_date: str | None = None, end_date: str | None = None, llm: GeminiService | None = None, **_: Any) -> dict[str, Any]:
    missing = [key for key, val in (("goal", goal), ("start_date", start_date), ("end_date", end_date)) if not val]
    if missing: return {"status": "needs_input", "missing_inputs": missing, "message": "Campaign goal and dates are required before creating the brief."}
    products = products or ["Collection products"]
    if llm and llm.enabled:
        generated = llm.generate_json("Create a concise campaign brief as JSON with objective, audience, messaging, channels, timeline, checklist. Use only: " + json.dumps({"goal": goal, "products": products, "audience": audience, "promotion": promotion, "start_date": start_date, "end_date": end_date}))
        required_keys = ("objective", "audience", "messaging", "channels", "timeline", "checklist")
        absent = [key for key in required_keys if not generated.get(key)]
        if absent: raise ValueError(f"Gemini campaign brief is missing fields: {', '.join(absent)}")
        return generated
    return {"status": "complete", "mode": "local_fallback", "objective": goal, "audience": audience or "To be confirmed", "products": products, "promotion": promotion or "None specified", "messaging": f"Introduce {', '.join(products)} with messaging focused on {goal}.", "channels": ["Email", "Organic social", "Website"], "timeline": {"start": start_date, "end": end_date}, "checklist": ["Approve creative", "Confirm product availability", "Schedule campaign", "Review results"]}


def keyword_classification(keywords: list[str] | None = None, category: str = "General", llm: GeminiService | None = None, **_: Any) -> dict[str, Any]:
    if not keywords: return {"status": "needs_input", "message": "Upload a keyword list or provide keywords to classify."}
    deduped = list(dict.fromkeys(str(k).strip() for k in keywords if str(k).strip()))
    if llm and llm.enabled:
        generated = llm.generate_json("Classify every keyword as informational, commercial, transactional, or navigational. Return a JSON object with a results list; each item includes keyword, intent, category, priority, recommended_target_page. Keywords: " + json.dumps(deduped) + f"\nProduct category: {category}", list_key="results")
        rows = generated.get("results")
        if not isinstance(rows, list): raise ValueError("Gemini keyword response did not include a results list")
        intents = {"informational", "commercial", "transactional", "navigational"}
        received = [str(row.get("keyword", "")).casefold() for row in rows if isinstance(row, dict)]
        missing = [keyword for keyword in deduped if keyword.casefold() not in received]
        invalid = [row.get("keyword", "") for row in rows if not isinstance(row, dict) or str(row.get("intent", "")).casefold() not in intents]
        if missing or invalid:
            raise ValueError(f"Gemini keyword output failed validation; missing={missing}, invalid={invalid}")
        return generated
    rows = []
    for keyword in deduped:
        text = keyword.lower()
        if any(t in text for t in ("buy", "price", "discount", "shop", "for sale")): intent = "transactional"
        elif any(t in text for t in ("best", "review", "vs", "top")): intent = "commercial"
        elif any(t in text for t in ("what", "how", "guide", "ideas")): intent = "informational"
        else: intent = "navigational"
        rows.append({"keyword": keyword, "intent": intent, "category": category, "priority": "high" if intent == "transactional" else "medium", "recommended_target_page": f"/{category.lower().replace(' ', '-')}/{intent}"})
    return {"status": "complete", "mode": "local_fallback", "count": len(rows), "results": rows}


def task_assignment(task: str | None = None, priority: str = "normal", deadline: str | None = None, **_: Any) -> dict[str, Any]:
    if not task: return {"status": "needs_input", "message": "Describe the task so I can match its skills and effort to an employee."}
    people = _read_csv("employees.csv").fillna("")
    tokens = set(re.findall(r"[a-z]+", task.lower()))
    scored = []
    for person in people.to_dict("records"):
        skills = set(str(person["skills"]).lower().split(";"))
        score = len(tokens & skills) + max(0, int(person["capacity_pct"]) < 80)
        if int(person["capacity_pct"]) >= 100: score = 0
        scored.append((score, person))
    scored.sort(key=lambda row: (row[0], -int(row[1]["capacity_pct"])), reverse=True)
    score, best = scored[0]
    if score <= 0: return {"status": "escalate", "message": "No available employee has a suitable skill match. Escalate to the manager.", "ranked_candidates": [{"name": p["name"], "score": s, "capacity_pct": p["capacity_pct"]} for s, p in scored]}
    return {"status": "complete", "recommended_employee": best["name"], "matched_skills": sorted(tokens & set(best["skills"].lower().split(";"))), "capacity_pct": int(best["capacity_pct"]), "reasoning": f"Best available skills and capacity match (current workload {best['capacity_pct']}%).", "priority": priority, "deadline": deadline, "task_summary": task}


def performance_report(**_: Any) -> dict[str, Any]:
    df = _read_csv("execution_logs.csv")
    rows = []
    for name, group in df.groupby("workflow_id"):
        success = int(group.status.eq("success").sum())
        total = len(group)
        fail_rate = (total - success) / total * 100 if total else 0
        avg = float(group.duration_seconds.mean()) if total else 0
        errs = group.loc[group.status.ne("success"), "error"].dropna().value_counts()
        rows.append({"workflow_id": name, "runs": total, "failure_rate_pct": round(fail_rate, 1), "avg_duration_seconds": round(avg, 2), "frequent_errors": errs.head(2).index.tolist(), "flagged": fail_rate > 10 or avg > 15})
    slow_steps = df.groupby("slow_step").duration_seconds.mean().sort_values(ascending=False)
    return {"workflow_count": len(rows), "workflows": rows, "slow_steps": [{"step": str(k), "avg_seconds": round(float(v), 2)} for k, v in slow_steps.head(3).items()], "recommendations": ["Review workflows flagged for failure rates above 10% or average duration above 15 seconds.", "Investigate recurring errors and optimize the slowest measured steps."]}


class ToolRegistry:
    def __init__(self, llm: GeminiService | None = None):
        self.llm = llm or GeminiService()
        self._tools: dict[str, Callable[..., Any]] = {
            "inventory_restock": inventory_restock,
            "price_validation": price_validation,
            "vendor_file_process": vendor_file_process,
            "product_content": lambda **kw: product_content(llm=self.llm, **kw),
            "order_lookup": order_lookup,
            "duplicate_detection": duplicate_detection,
            "campaign_brief": lambda **kw: campaign_brief(llm=self.llm, **kw),
            "keyword_classification": lambda **kw: keyword_classification(llm=self.llm, **kw),
            "task_assignment": task_assignment,
            "performance_report": performance_report,
        }

    def register(self, name: str, function: Callable[..., Any]) -> None:
        if name in self._tools: raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = function

    def call(self, name: str, **kwargs: Any) -> Any:
        try: function = self._tools[name]
        except KeyError as e: raise KeyError(f"Unknown tool: {name}") from e
        return function(**kwargs)

    @property
    def names(self) -> list[str]: return sorted(self._tools)
