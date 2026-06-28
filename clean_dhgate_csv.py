from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


INPUT_PATH = Path("data/dhgate_large_capture.csv")
OUTPUT_CLEAN = Path("data/dhgate_clean_user_friendly.csv")
OUTPUT_FULL = Path("data/dhgate_clean_full.csv")
OUTPUT_TOP = Path("output/dhgate_top_100_clean.csv")


PLATFORM_FEE_RATE = 0.04
ESTIMATED_AD_COST = 5.00
DEFAULT_SHIPPING_COST = 0.00


BRAND_RISK_WORDS = [
    "nike", "adidas", "puma", "reebok", "under armour", "jordan",
    "real madrid", "barcelona", "fc barcelona", "manchester united",
    "manchester city", "chelsea", "arsenal", "liverpool", "tottenham",
    "psg", "paris saint germain", "bayern", "juventus", "inter milan",
    "ac milan", "messi", "ronaldo", "mbappe", "neymar",
    "nba", "nfl", "mlb", "fifa", "world cup", "disney", "marvel",
    "pokemon", "hello kitty", "spiderman", "batman", "supreme",
    "gucci", "louis vuitton", "lv", "prada", "dior", "chanel",
]


BAD_PRODUCT_WORDS = [
    "replica", "fake", "copy", "inspired", "aaa", "1:1", "counterfeit",
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_number(value: Any) -> float:
    text = clean_text(value)
    text = text.replace("$", "").replace("%", "").replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return round(float(match.group(1)), 2) if match else 0.0


def clean_int(value: Any) -> int:
    text = clean_text(value).replace(",", "")
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 0


def clean_url(value: Any) -> str:
    url = clean_text(value)

    if not url.startswith("http"):
        return ""

    return url.split("?")[0].split("#")[0].rstrip("/")


def image_filename(value: Any) -> str:
    url = clean_url(value)

    if not url:
        return ""

    return url.split("/")[-1].lower()


def extract_dhgate_product_id(url: Any) -> str:
    url = clean_text(url)

    patterns = [
        r"/(\d+)\.html",
        r"productid=(\d+)",
        r"itemcode=(\d+)",
        r"goodsid=(\d+)",
        r"sku=(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url.lower())
        if match:
            return match.group(1)

    return ""


def title_clean_product_name(name: Any) -> str:
    name = clean_text(name)

    remove_phrases = [
        "free shipping",
        "hot sale",
        "new arrival",
        "high quality",
        "best selling",
        "dropshipping",
        "drop shipping",
    ]

    lowered = name.lower()

    for phrase in remove_phrases:
        lowered = lowered.replace(phrase, "")

    name = re.sub(r"\s+", " ", lowered).strip()

    if not name:
        return ""

    return name.title()


def smart_sale_price(cost: float) -> float:
    if cost <= 0:
        return 0.0

    if cost < 5:
        multiplier = 3.5
    elif cost < 15:
        multiplier = 3.0
    elif cost < 35:
        multiplier = 2.5
    else:
        multiplier = 2.0

    return round(math.ceil(cost * multiplier) - 0.01, 2)


def profit_metrics(cost: float, sale_price: float, shipping: float) -> dict:
    if sale_price <= 0:
        return {
            "estimated_profit": 0.0,
            "profit_margin_pct": 0.0,
            "roi_pct": 0.0,
            "platform_fee": 0.0,
        }

    platform_fee = round(sale_price * PLATFORM_FEE_RATE, 2)
    profit = round(sale_price - cost - shipping - platform_fee - ESTIMATED_AD_COST, 2)
    margin = round((profit / sale_price) * 100, 2) if sale_price else 0.0
    roi = round((profit / max(cost + shipping, 0.01)) * 100, 2)

    return {
        "estimated_profit": profit,
        "profit_margin_pct": margin,
        "roi_pct": roi,
        "platform_fee": platform_fee,
    }


def brand_risk(name: str) -> tuple[str, str]:
    lowered = normalize(name)

    risky_matches = [word for word in BRAND_RISK_WORDS if word in lowered]
    bad_matches = [word for word in BAD_PRODUCT_WORDS if word in lowered]

    if risky_matches or bad_matches:
        matches = risky_matches + bad_matches
        return "HIGH", "Possible trademark/counterfeit risk: " + ", ".join(matches[:8])

    return "LOW", ""


def shipping_risk(row) -> tuple[str, str]:
    text = normalize(row.get("shipping_text", ""))

    if "free shipping" in text:
        return "LOW", "Free shipping mentioned"

    if "shipping" in text or "delivery" in text:
        return "MEDIUM", clean_text(row.get("shipping_text", ""))[:120]

    return "UNKNOWN", "No clear shipping info captured"


def make_dedupe_key(row) -> str:
    product_id = clean_text(row.get("dhgate_product_id", ""))

    if product_id:
        return f"id|{product_id}"

    url = clean_url(row.get("supplier_url", ""))

    if url:
        return f"url|{url}"

    return (
        "name_image|"
        + normalize(row.get("product_name", ""))
        + "|"
        + image_filename(row.get("image_url", ""))
    )


def marketplace_score(row) -> float:
    rating = clean_number(row.get("rating", 0))
    reviews = clean_int(row.get("reviews_count", 0))
    sold = clean_int(row.get("sold_count", 0))

    score = 0

    if rating >= 4.7:
        score += 25
    elif rating >= 4.3:
        score += 18
    elif rating >= 4.0:
        score += 10

    if reviews >= 500:
        score += 25
    elif reviews >= 100:
        score += 18
    elif reviews >= 25:
        score += 10

    if sold >= 1000:
        score += 30
    elif sold >= 300:
        score += 22
    elif sold >= 50:
        score += 12

    return min(score, 100)


def opportunity_score(row) -> float:
    profit = clean_number(row.get("estimated_profit", 0))
    margin = clean_number(row.get("profit_margin_pct", 0))
    roi = clean_number(row.get("roi_pct", 0))
    cost = clean_number(row.get("product_cost", 0))
    market = clean_number(row.get("marketplace_score", 0))
    brand_risk_value = clean_text(row.get("brand_risk", ""))

    score = 0

    score += min(max(margin, 0), 70) * 0.45
    score += min(max(roi, 0), 200) * 0.15
    score += market * 0.25

    if profit >= 20:
        score += 15
    elif profit >= 10:
        score += 10
    elif profit >= 5:
        score += 5

    if 5 <= cost <= 35:
        score += 8
    elif cost > 60:
        score -= 12

    if brand_risk_value == "HIGH":
        score -= 35

    return round(max(min(score, 100), 0), 2)


def action_label(row) -> str:
    score = clean_number(row.get("dhgate_opportunity_score", 0))
    profit = clean_number(row.get("estimated_profit", 0))
    margin = clean_number(row.get("profit_margin_pct", 0))
    brand = clean_text(row.get("brand_risk", ""))

    if brand == "HIGH":
        return "PASS"

    if score >= 70 and profit >= 10 and margin >= 30:
        return "TEST"

    if score >= 50 and profit >= 5:
        return "WATCH"

    return "PASS"


def risk_level(row) -> str:
    brand = clean_text(row.get("brand_risk", ""))
    cost = clean_number(row.get("product_cost", 0))
    profit = clean_number(row.get("estimated_profit", 0))
    image = clean_text(row.get("image_url", ""))
    url = clean_text(row.get("supplier_url", ""))

    if brand == "HIGH":
        return "HIGH"

    if cost <= 0 or profit <= 0 or not image or not url:
        return "HIGH"

    if cost > 50:
        return "MEDIUM"

    return "LOW"


def risk_notes(row) -> str:
    notes = []

    if clean_text(row.get("brand_risk_notes", "")):
        notes.append(clean_text(row.get("brand_risk_notes", "")))

    if clean_number(row.get("product_cost", 0)) <= 0:
        notes.append("Missing or invalid product cost")

    if clean_number(row.get("estimated_profit", 0)) <= 0:
        notes.append("Weak or negative estimated profit")

    if not clean_text(row.get("image_url", "")):
        notes.append("Missing product image")

    if not clean_text(row.get("supplier_url", "")):
        notes.append("Missing supplier URL")

    if clean_number(row.get("product_cost", 0)) > 50:
        notes.append("Higher product cost; risky for beginner testing")

    return " | ".join(notes)


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_PATH}")

    df = pd.read_csv(INPUT_PATH).fillna("").astype("object")

    # Make sure important columns exist.
    needed_cols = [
        "source_site",
        "marketplace_source",
        "dhgate_product_id",
        "product_name",
        "keyword",
        "category",
        "product_cost",
        "price_min",
        "price_max",
        "shipping_cost",
        "estimated_sale_price",
        "supplier_url",
        "clean_supplier_url",
        "image_url",
        "image_filename",
        "store_name",
        "rating",
        "reviews_count",
        "sold_count",
        "shipping_text",
        "crawl_keyword",
        "crawl_page",
        "capture_page_url",
        "first_seen_at",
        "last_seen_at",
        "raw_card_text",
    ]

    for col in needed_cols:
        if col not in df.columns:
            df[col] = ""

    df["source_site"] = "dhgate"
    df["marketplace_source"] = "DHGATE"

    df["product_name"] = df["product_name"].apply(title_clean_product_name)
    df["keyword"] = df["keyword"].apply(clean_text)
    df["category"] = df["category"].where(df["category"].astype(str).str.len() > 0, df["keyword"])
    df["category"] = df["category"].apply(clean_text)

    df["supplier_url"] = df["supplier_url"].apply(clean_url)
    df["clean_supplier_url"] = df["supplier_url"]
    df["image_url"] = df["image_url"].apply(clean_text)
    df["image_filename"] = df["image_url"].apply(image_filename)

    df["dhgate_product_id"] = df.apply(
        lambda row: clean_text(row["dhgate_product_id"])
        if clean_text(row["dhgate_product_id"])
        else extract_dhgate_product_id(row["supplier_url"]),
        axis=1,
    )

    numeric_cols = [
        "product_cost",
        "price_min",
        "price_max",
        "shipping_cost",
        "estimated_sale_price",
        "rating",
        "reviews_count",
        "sold_count",
        "crawl_page",
    ]

    for col in numeric_cols:
        df[col] = df[col].apply(clean_number)

    df["reviews_count"] = df["reviews_count"].astype(int)
    df["sold_count"] = df["sold_count"].astype(int)

    df["shipping_cost"] = df["shipping_cost"].where(df["shipping_cost"] > 0, DEFAULT_SHIPPING_COST)

    df["estimated_sale_price"] = df.apply(
        lambda row: clean_number(row["estimated_sale_price"])
        if clean_number(row["estimated_sale_price"]) > 0
        else smart_sale_price(clean_number(row["product_cost"])),
        axis=1,
    )

    profit_df = df.apply(
        lambda row: profit_metrics(
            clean_number(row["product_cost"]),
            clean_number(row["estimated_sale_price"]),
            clean_number(row["shipping_cost"]),
        ),
        axis=1,
        result_type="expand",
    )

    df = pd.concat([df, profit_df], axis=1)

    brand_data = df["product_name"].apply(brand_risk)
    df["brand_risk"] = brand_data.apply(lambda x: x[0])
    df["brand_risk_notes"] = brand_data.apply(lambda x: x[1])

    shipping_data = df.apply(shipping_risk, axis=1)
    df["shipping_risk"] = shipping_data.apply(lambda x: x[0])
    df["shipping_risk_notes"] = shipping_data.apply(lambda x: x[1])

    df["marketplace_score"] = df.apply(marketplace_score, axis=1)
    df["dhgate_opportunity_score"] = df.apply(opportunity_score, axis=1)

    df["next_action"] = df.apply(action_label, axis=1)
    df["risk_level"] = df.apply(risk_level, axis=1)
    df["risk_notes"] = df.apply(risk_notes, axis=1)

    df["has_image"] = df["image_url"].astype(str).str.startswith("http")
    df["has_supplier_url"] = df["supplier_url"].astype(str).str.startswith("http")
    df["cleaned_at"] = now_text()

    df["dedupe_key"] = df.apply(make_dedupe_key, axis=1)

    before = len(df)

    df = df.sort_values(
        by=["dhgate_opportunity_score", "estimated_profit", "sold_count", "reviews_count"],
        ascending=[False, False, False, False],
    )

    df = df.drop_duplicates(subset=["dedupe_key"], keep="first")
    after = len(df)

    user_friendly_cols = [
        "next_action",
        "risk_level",
        "dhgate_opportunity_score",
        "marketplace_score",
        "product_name",
        "category",
        "keyword",
        "product_cost",
        "price_min",
        "price_max",
        "shipping_cost",
        "estimated_sale_price",
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "rating",
        "reviews_count",
        "sold_count",
        "brand_risk",
        "brand_risk_notes",
        "shipping_risk",
        "shipping_risk_notes",
        "risk_notes",
        "supplier_url",
        "image_url",
        "dhgate_product_id",
        "crawl_page",
        "crawl_keyword",
        "first_seen_at",
        "last_seen_at",
        "cleaned_at",
    ]

    full_cols = user_friendly_cols + [
        "source_site",
        "marketplace_source",
        "clean_supplier_url",
        "image_filename",
        "store_name",
        "capture_page_url",
        "raw_card_text",
    ]

    user_friendly_cols = [col for col in user_friendly_cols if col in df.columns]
    full_cols = [col for col in full_cols if col in df.columns]

    clean_df = df[user_friendly_cols].copy()
    full_df = df[full_cols].copy()

    OUTPUT_CLEAN.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FULL.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_TOP.parent.mkdir(parents=True, exist_ok=True)

    clean_df.to_csv(OUTPUT_CLEAN, index=False)
    full_df.to_csv(OUTPUT_FULL, index=False)

    clean_df.head(100).to_csv(OUTPUT_TOP, index=False)

    print()
    print("=" * 72)
    print("DHGATE CLEAN CSV CREATED")
    print(f"Original rows: {before}")
    print(f"Clean unique rows: {after}")
    print(f"Duplicates removed: {before - after}")
    print()
    print(f"User-friendly CSV: {OUTPUT_CLEAN}")
    print(f"Full clean CSV: {OUTPUT_FULL}")
    print(f"Top 100 review CSV: {OUTPUT_TOP}")
    print()
    print("Action counts:")
    print(clean_df["next_action"].value_counts())
    print()
    print("Risk counts:")
    print(clean_df["risk_level"].value_counts())
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
