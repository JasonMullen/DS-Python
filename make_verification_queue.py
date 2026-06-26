from pathlib import Path
import pandas as pd

INPUT_PATH = Path("output/opportunities.csv")
OUTPUT_PATH = Path("output/top_products_to_verify.csv")

df = pd.read_csv(INPUT_PATH).fillna("")

# Remove obvious weak products
if "risk_level" in df.columns:
    df = df[df["risk_level"].astype(str).str.upper() != "HIGH"]

if "estimated_profit" in df.columns:
    df = df[df["estimated_profit"] > 10]

if "profit_margin_pct" in df.columns:
    df = df[df["profit_margin_pct"] > 25]

# Sort by best opportunity
sort_columns = []
ascending = []

if "final_score" in df.columns:
    sort_columns.append("final_score")
    ascending.append(False)

if "estimated_profit" in df.columns:
    sort_columns.append("estimated_profit")
    ascending.append(False)

if "roi_pct" in df.columns:
    sort_columns.append("roi_pct")
    ascending.append(False)

if sort_columns:
    df = df.sort_values(sort_columns, ascending=ascending)

# Keep top 50 for manual verification
top = df.head(50).copy()

top["verification_status"] = "NEEDS CHECK"
top["exact_match_found"] = ""
top["real_product_cost"] = ""
top["real_shipping_cost"] = ""
top["real_total_cost"] = ""
top["realistic_sale_price"] = ""
top["realistic_profit"] = ""
top["notes"] = ""

columns = [
    "image_url",
    "product_name",
    "category",
    "product_cost",
    "estimated_sale_price",
    "estimated_profit",
    "profit_margin_pct",
    "roi_pct",
    "p_c_ratio",
    "growth_pct",
    "final_score",
    "risk_level",
    "next_action",
    "risk_notes",
    "supplier_url",
    "verification_status",
    "exact_match_found",
    "real_product_cost",
    "real_shipping_cost",
    "real_total_cost",
    "realistic_sale_price",
    "realistic_profit",
    "notes",
]

available = [col for col in columns if col in top.columns]

OUTPUT_PATH.parent.mkdir(exist_ok=True)
top[available].to_csv(OUTPUT_PATH, index=False)

print(f"Created verification queue: {OUTPUT_PATH}")
print(f"Products to verify: {len(top)}")
print(top[available].head(10))
