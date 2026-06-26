from pathlib import Path
import re
import pandas as pd


OPPORTUNITIES_PATH = Path("output/opportunities.csv")
SUPPLIER_PATH = Path("data/supplier_products.csv")
OUTPUT_PATH = Path("output/all_products_verification.csv")


STOP_WORDS = {
    "for", "with", "and", "the", "a", "an", "of", "to", "in", "on",
    "new", "hot", "best", "fashion", "trend", "premium", "portable",
    "comfortable", "adjustable", "creative", "stylish", "oversized",
    "men", "mens", "women", "womens", "unisex",
}


def clean_name(name: str) -> str:
    name = str(name)
    name = re.sub(r"\|.*$", "", name)
    name = re.sub(r"[-–—]", " ", name)
    name = re.sub(
        r"\b\d+(\.\d+)?\s?(inch|in|cm|mm|oz|lb|lbs|pcs|pack|x)\b",
        " ",
        name,
        flags=re.I,
    )
    name = re.sub(r"[^a-zA-Z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def make_search_terms(name: str):
    cleaned = clean_name(name)
    words = [
        word for word in cleaned.split()
        if len(word) > 2 and word.lower() not in STOP_WORDS
    ]

    search_1 = " ".join(words[:5])
    search_2 = " ".join(words[:3])
    search_3 = " ".join(words[-4:]) if len(words) >= 4 else search_2

    return search_1, search_2, search_3


def make_verification_id(row) -> str:
    name = str(row.get("product_name", "")).strip().lower()
    image = str(row.get("image_url", "")).strip().lower().split("?")[0]
    return re.sub(r"[^a-z0-9]+", "-", f"{name}-{image}")[:180]


if not OPPORTUNITIES_PATH.exists():
    raise FileNotFoundError("Missing output/opportunities.csv. Run python -m dropship_researcher.main first.")

df = pd.read_csv(OPPORTUNITIES_PATH).fillna("")

if SUPPLIER_PATH.exists():
    supplier_df = pd.read_csv(SUPPLIER_PATH).fillna("")

    supplier_cols = [
        "product_name",
        "image_url",
        "store_name",
        "p_c_ratio",
        "growth_pct",
        "order_trend_score",
        "saturation",
        "top_country",
        "zendrop_product_id",
    ]

    supplier_cols = [col for col in supplier_cols if col in supplier_df.columns]

    if "product_name" in supplier_cols:
        supplier_small = supplier_df[supplier_cols].drop_duplicates(subset=["product_name"])

        df = df.merge(
            supplier_small,
            on="product_name",
            how="left",
            suffixes=("", "_supplier"),
        )

        for col in [
            "image_url",
            "store_name",
            "p_c_ratio",
            "growth_pct",
            "order_trend_score",
            "saturation",
            "top_country",
            "zendrop_product_id",
        ]:
            supplier_col = f"{col}_supplier"

            if col not in df.columns and supplier_col in df.columns:
                df[col] = df[supplier_col]

            elif col in df.columns and supplier_col in df.columns:
                df[col] = df[col].where(
                    df[col].astype(str).str.len() > 0,
                    df[supplier_col],
                )

for col in ["image_url", "store_name", "p_c_ratio", "growth_pct"]:
    if col not in df.columns:
        df[col] = ""

df["verification_id"] = df.apply(make_verification_id, axis=1)

search_terms = df["product_name"].apply(make_search_terms)
df["zendrop_search_1"] = search_terms.apply(lambda x: x[0])
df["zendrop_search_2"] = search_terms.apply(lambda x: x[1])
df["zendrop_search_3"] = search_terms.apply(lambda x: x[2])

new_verification_cols = {
    "verification_status": "NEEDS CHECK",
    "exact_match_found": "",
    "exact_product_url": "",
    "real_product_cost": "",
    "real_shipping_cost": "",
    "real_total_cost": "",
    "realistic_sale_price": "",
    "realistic_profit": "",
    "verified_decision": "",
    "verified_at": "",
    "verification_notes": "",
}

for col, default in new_verification_cols.items():
    if col not in df.columns:
        df[col] = default

# Preserve old verification work if the file already exists.
if OUTPUT_PATH.exists():
    old = pd.read_csv(OUTPUT_PATH).fillna("")

    keep_cols = ["verification_id"] + list(new_verification_cols.keys())

    keep_cols = [col for col in keep_cols if col in old.columns]

    if "verification_id" in keep_cols:
        old_small = old[keep_cols].drop_duplicates(subset=["verification_id"])

        df = df.drop(columns=[col for col in new_verification_cols if col in df.columns])
        df = df.merge(old_small, on="verification_id", how="left")

        for col, default in new_verification_cols.items():
            if col not in df.columns:
                df[col] = default
            df[col] = df[col].fillna(default)
            df[col] = df[col].replace("", default if col == "verification_status" else "")

columns = [
    "verification_id",
    "image_url",
    "product_name",
    "store_name",
    "category",
    "product_cost",
    "p_c_ratio",
    "growth_pct",
    "estimated_sale_price",
    "estimated_profit",
    "profit_margin_pct",
    "roi_pct",
    "final_score",
    "risk_level",
    "next_action",
    "risk_notes",
    "supplier_url",
    "zendrop_search_1",
    "zendrop_search_2",
    "zendrop_search_3",
    "verification_status",
    "exact_match_found",
    "exact_product_url",
    "real_product_cost",
    "real_shipping_cost",
    "real_total_cost",
    "realistic_sale_price",
    "realistic_profit",
    "verified_decision",
    "verified_at",
    "verification_notes",
]

available = [col for col in columns if col in df.columns]

if "final_score" in df.columns:
    df = df.sort_values("final_score", ascending=False)

OUTPUT_PATH.parent.mkdir(exist_ok=True)
df[available].to_csv(OUTPUT_PATH, index=False)

print(f"Created full verification queue: {OUTPUT_PATH}")
print(f"Total products to verify: {len(df)}")
print(df[available].head(10))
