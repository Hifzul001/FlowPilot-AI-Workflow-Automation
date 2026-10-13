from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "samples"
OUT.mkdir(parents=True, exist_ok=True)

pd.DataFrame([
    {"sku":"SKU-100","product_name":"Canvas Tote","current_stock":3,"minimum_stock":12},
    {"sku":"SKU-101","product_name":"Ceramic Mug","current_stock":8,"minimum_stock":8},
    {"sku":"SKU-102","product_name":"Linen Shirt","current_stock":0,"minimum_stock":6},
    {"sku":"SKU-103","product_name":"Desk Lamp","current_stock":18,"minimum_stock":5},
]).to_csv(OUT / "inventory.csv", index=False)

products = [
    {"sku":"SKU-100","product_name":"Canvas Tote","category":"Bags","internal_price":24.0,"color":"Natural","material":"Canvas"},
    {"sku":"SKU-101","product_name":"Ceramic Mug","category":"Home","internal_price":18.0,"color":"Blue","material":"Ceramic"},
    {"sku":"SKU-102","product_name":"Linen Shirt","category":"Apparel","internal_price":54.0,"color":"White","material":"Linen"},
    {"sku":"SKU-103","product_name":"Desk Lamp","category":"Home","internal_price":42.0,"color":"Black","material":"Metal"},
    {"sku":"SKU-104","product_name":"Canvas Tote Bag","category":"Bags","internal_price":25.0,"color":"Natural","material":"Canvas"},
]
pd.DataFrame(products).to_csv(OUT / "products.csv", index=False)
pd.DataFrame([
    {"sku":"CAT-200","product_name":"Canvas Tote","category":"Bags","color":"Natural","material":"Canvas"},
    {"sku":"CAT-201","product_name":"Table Lamp","category":"Home","color":"Black","material":"Metal"},
    {"sku":"CAT-201","product_name":"Table Lamp","category":"Home","color":"Black","material":"Metal"},
    {"sku":"CAT-202","product_name":"Canvas Tote Bag","category":"Bags","color":"Natural","material":"Canvas"},
]).to_csv(OUT / "product_catalog.csv", index=False)
pd.DataFrame([
    {"sku":"SKU-100","vendor_price":20.0},
    {"sku":"SKU-101","vendor_price":16.0},
    {"sku":"SKU-102","vendor_price":50.0},
    {"sku":"SKU-103","vendor_price":40.0},
    {"sku":"SKU-104","vendor_price":24.0},
]).to_csv(OUT / "vendor_prices.csv", index=False)

pd.DataFrame([
    {"order_id":"ORD-1001","customer_email":"maya@example.com","order_status":"Shipped","items":"Canvas Tote x1; Ceramic Mug x2","shipment_status":"In transit","tracking_number":"TRK-449210","updated_at":"2026-10-12"},
    {"order_id":"ORD-1002","customer_email":"lee@example.com","order_status":"Processing","items":"Linen Shirt x1","shipment_status":"Label created","tracking_number":"TRK-449211","updated_at":"2026-10-13"},
]).to_csv(OUT / "orders.csv", index=False)

pd.DataFrame([
    {"name":"Asha Patel","skills":"python;backend;api;developer","capacity_pct":62},
    {"name":"Noah Kim","skills":"react;frontend;javascript;developer","capacity_pct":48},
    {"name":"Mina Chen","skills":"python;data;automation;developer","capacity_pct":92},
    {"name":"Eli Brooks","skills":"design;qa;testing","capacity_pct":40},
]).to_csv(OUT / "employees.csv", index=False)

pd.DataFrame([
    {"workflow_id":"WF001","status":"success","duration_seconds":2.1,"error":"","slow_step":"inventory comparison"},
    {"workflow_id":"WF001","status":"success","duration_seconds":2.5,"error":"","slow_step":"inventory comparison"},
    {"workflow_id":"WF002","status":"failure","duration_seconds":18.0,"error":"Vendor SKU missing","slow_step":"vendor join"},
    {"workflow_id":"WF002","status":"failure","duration_seconds":22.0,"error":"Vendor SKU missing","slow_step":"vendor join"},
    {"workflow_id":"WF002","status":"success","duration_seconds":14.0,"error":"","slow_step":"vendor join"},
    {"workflow_id":"WF003","status":"success","duration_seconds":6.2,"error":"","slow_step":"file normalization"},
    {"workflow_id":"WF004","status":"success","duration_seconds":8.5,"error":"","slow_step":"copy generation"},
    {"workflow_id":"WF004","status":"success","duration_seconds":7.0,"error":"","slow_step":"copy generation"},
    {"workflow_id":"WF004","status":"failure","duration_seconds":9.0,"error":"LLM timeout","slow_step":"copy generation"},
    {"workflow_id":"WF005","status":"success","duration_seconds":1.3,"error":"","slow_step":"order lookup"},
    {"workflow_id":"WF006","status":"success","duration_seconds":4.0,"error":"","slow_step":"similarity scan"},
    {"workflow_id":"WF007","status":"failure","duration_seconds":21.0,"error":"Missing campaign dates","slow_step":"brief generation"},
    {"workflow_id":"WF008","status":"success","duration_seconds":5.0,"error":"","slow_step":"intent classification"},
    {"workflow_id":"WF009","status":"success","duration_seconds":3.2,"error":"","slow_step":"candidate ranking"},
    {"workflow_id":"WF010","status":"success","duration_seconds":4.7,"error":"","slow_step":"aggregation"},
]).to_csv(OUT / "execution_logs.csv", index=False)

# Example upload used by the demo and recruiter scenario tests.
pd.DataFrame([
    {"Product SKU":"V-200","Product Name":"Wool Scarf","Price":29.0},
    {"Product SKU":"","Product Name":"Missing SKU Item","Price":8.0},
    {"Product SKU":"V-202","Product Name":"","Price":12.0},
]).to_csv(OUT / "vendor_upload_example.csv", index=False)

(OUT / "keywords_example.json").write_text(json.dumps(["buy canvas tote", "best canvas tote", "how to clean canvas", "Acme canvas totes"], indent=2), encoding="utf-8")
print(f"Sample datasets created in {OUT}")
