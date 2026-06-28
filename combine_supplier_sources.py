from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


DATA_DIR = Path("data")

ZENDROP_PATH = DATA_DIR / "zendrop_smart_capture.csv"
DHGATE_PATH = DATA_DIR / "dhgate_manual_capture.csv"
SHEIN_PATH = DATA_DIR / "shein_manual_capture.csv"

OUTPUT_MULTI = DATA_DIR / "supplier_products_multi_source.csv"
OUTPUT_MAIN = DATA_DIR / "supplier_products.csv"
BACKUP_MAIN = DATA_DIR / "supplier_products_before_multi_source.csv"


STANDARD_COLUMNS = [
    "source_site",
    "marketplace_source",
    "product_name",
    "keyword",
    "category",
    "product_cost",
    "shipping_cost",
    "estimated_sale_price",
    "supplier_url",
    "image_url",
    "store_name",
    "price_min",
    "price_max",
    "p_c_ratio",
    "growth_pct",
    "order_trend_score",
    "saturation",
    "top_country",
    "rating",
    "reviews_count",
    "sold_count",
    "shipping_text",
    "first_seen_at",
    "last_seen_at",
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def image_filename(url: Any) -> str:
    url = clean_text(url).split("?")[0].strip("/")
    if not url:
        return ""
    return url.split("/")[-1].lower()


def clean_number(value: Any) -> float:
    text = clean_text(value)
    text = text.replace("$", "").replace("%", "").replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return round(float(match.group(1)), 2) if match else 0.0


def smart_price(cost: float, multiplier: float) -> float:
    if cost <= 0:
        return 0.0

    raw = cost * multiplier
    return round(math.ceil(raw) - 0.01, 2)


def guess_keyword(product_name: str, category: str = "") -> str:
    if category:
        return category

    words = [
        word for word in normalize(product_name).split()
        if len(word) > 2
    ]

    return " ".join(words[:4]) if words else "product"


def load_source(path: Path, source_site: str, multiplier: float) -> pd.DataFrame:
    if not path.exists():
        print(f"Missing: {path}")
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = pd.read_csv(path).fillna("").astype("object")

    for col in STANDARD_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df["source_site"] = df["source_site"].where(
        df["source_site"].astype(str).str.len() > 0,
        source_site,
    )

    df["marketplace_source"] = df["marketplace_source"].where(
        df["marketplace_source"].astype(str).str.len() > 0,
        source_site.upper(),
    )

    df["product_cost"] = df["product_cost"].apply(clean_number)

    if "price_min" in df.columns:
        df["price_min"] = df["price_min"].apply(clean_number)
    else:
        df["price_min"] = df["product_cost"]

    if "price_max" in df.columns:
        df["price_max"] = df["price_max"].apply(clean_number)
    else:
        df["price_max"] = df["product_cost"]

    df["shipping_cost"] = df["shipping_cost"].apply(clean_number)

    df["estimated_sale_price"] = df.apply(
        lambda row: clean_number(row["estimated_sale_price"])
        if clean_number(row["estimated_sale_price"]) > 0
        else smart_price(clean_number(row["product_cost"]), multiplier),
        axis=1,
    )

    df["keyword"] = df.apply(
        lambda row: row["keyword"]
        if clean_text(row["keyword"])
        else guess_keyword(row["product_name"], row["category"]),
        axis=1,
    )

    df["category"] = df.apply(
        lambda row: row["category"]
        if clean_text(row["category"])
        else row["keyword"],
        axis=1,
    )

    df["first_seen_at"] = df["first_seen_at"].where(
        df["first_seen_at"].astype(str).str.len() > 0,
        now_text(),
    )

    df["last_seen_at"] = df["last_seen_at"].where(
        df["last_seen_at"].astype(str).str.len() > 0,
        now_text(),
    )

    return df[STANDARD_COLUMNS].copy()


def main():
    sources = [
        load_source(ZENDROP_PATH, "zendrop", 2.8),
        load_source(DHGATE_PATH, "dhgate", 2.6),
        load_source(SHEIN_PATH, "shein", 2.0),
    ]

    combined = pd.concat(sources, ignore_index=True).fillna("").astype("object")

    combined = combined[combined["product_name"].astype(str).str.len() > 3].copy()

    combined["dedupe_key"] = (
        combined["source_site"].astype(str).str.lower()
        + "|"
        + combined["product_name"].astype(str).map(normalize)
        + "|"
        + combined["image_url"].astype(str).map(image_filename)
    )

    combined = combined.drop_duplicates(subset=["dedupe_key"], keep="last")
    combined = combined.drop(columns=["dedupe_key"])

    combined = combined.sort_values(
        by=["source_site", "product_name"],
        ascending=[True, True],
    )

    OUTPUT_MULTI.parent.mkdir(parents=True, exist_ok=True)

    combined.to_csv(OUTPUT_MULTI, index=False)

    if OUTPUT_MAIN.exists() and not BACKUP_MAIN.exists():
        old = pd.read_csv(OUTPUT_MAIN).fillna("")
        old.to_csv(BACKUP_MAIN, index=False)
        print(f"Backed up old supplier file to: {BACKUP_MAIN}")

    combined.to_csv(OUTPUT_MAIN, index=False)

    print()
    print("=" * 72)
    print("MULTI-SOURCE SUPPLIER FILE CREATED")
    print(f"Total products: {len(combined)}")

    if "source_site" in combined.columns:
        print()
        print(combined["source_site"].value_counts())

    print()
    print(f"Saved: {OUTPUT_MULTI}")
    print(f"Updated main supplier file: {OUTPUT_MAIN}")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
