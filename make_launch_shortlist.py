from pathlib import Path

import pandas as pd


OPPORTUNITIES_PATH = Path("output/opportunities.csv")
SUPPLIER_PATH = Path("data/supplier_products.csv")
OUTPUT_PATH = Path("output/launch_shortlist.csv")
TOP_OUTPUT_PATH = Path("output/top_25_launch_shortlist.csv")


def clean_number(series):
    return pd.to_numeric(
        series.astype(str).str.replace("$", "", regex=False).str.replace("%", "", regex=False),
        errors="coerce",
    ).fillna(0)


def merge_extra_data(df):
    if not SUPPLIER_PATH.exists():
        return df

    supplier = pd.read_csv(SUPPLIER_PATH).fillna("")

    if "product_name" not in supplier.columns:
        return df

    useful_cols = [
        "product_name",
        "image_url",
        "store_name",
        "p_c_ratio",
        "growth_pct",
        "order_trend_score",
        "saturation",
        "top_country",
        "first_seen_at",
        "last_seen_at",
        "supplier_url",
    ]

    useful_cols = [col for col in useful_cols if col in supplier.columns]

    supplier = supplier[useful_cols].drop_duplicates(subset=["product_name"])

    df = df.merge(
        supplier,
        on="product_name",
        how="left",
        suffixes=("", "_supplier"),
    )

    for col in useful_cols:
        extra = f"{col}_supplier"

        if col != "product_name" and extra in df.columns:
            if col not in df.columns:
                df[col] = df[extra]
            else:
                df[col] = df[col].where(df[col].astype(str).str.len() > 0, df[extra])

    df = df.drop(columns=[col for col in df.columns if col.endswith("_supplier")])

    return df.fillna("")


def make_ad_angle(row):
    name = str(row.get("product_name", "")).lower()
    category = str(row.get("category", "")).lower()

    if "pet" in name or "dog" in name or "cat" in name or "pet" in category:
        return "Pet owner convenience / solves an annoying daily problem"

    if "car" in name or "auto" in name:
        return "Useful car accessory / practical upgrade"

    if "home" in name or "decor" in name or "kitchen" in name:
        return "Home improvement / makes life easier or cleaner"

    if "beauty" in name or "skin" in name or "hair" in name:
        return "Beauty improvement / confidence angle"

    if "fitness" in name or "gym" in name or "sport" in name:
        return "Fitness improvement / performance and confidence"

    if "gift" in name or "christmas" in name or "holiday" in name:
        return "Giftable product / seasonal buyer intent"

    return "Problem-solution angle / impulse-buy product test"


def make_next_step(row):
    tier = row.get("launch_tier", "")

    if tier == "A - Test First":
        return "Build product page, write 3 ad hooks, and test with small budget"

    if tier == "B - Maybe Test":
        return "Review manually, compare competitors, then decide"

    return "Do not test yet unless manually reviewed"


def main():
    if not OPPORTUNITIES_PATH.exists():
        raise FileNotFoundError("Missing output/opportunities.csv. Run: python -m dropship_researcher.main")

    df = pd.read_csv(OPPORTUNITIES_PATH).fillna("")
    df = merge_extra_data(df)

    needed_cols = [
        "product_name",
        "category",
        "product_cost",
        "estimated_sale_price",
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "opportunity_score",
        "final_score",
        "risk_level",
        "next_action",
        "risk_notes",
        "image_url",
        "supplier_url",
        "store_name",
        "p_c_ratio",
        "growth_pct",
        "saturation",
        "first_seen_at",
    ]

    for col in needed_cols:
        if col not in df.columns:
            df[col] = ""

    numeric_cols = [
        "product_cost",
        "estimated_sale_price",
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "opportunity_score",
        "final_score",
        "p_c_ratio",
        "growth_pct",
    ]

    for col in numeric_cols:
        df[col] = clean_number(df[col])

    df["has_image"] = df["image_url"].astype(str).str.startswith("http")
    df["risk_text"] = df["risk_level"].astype(str).str.lower()
    df["action_text"] = df["next_action"].astype(str).str.lower()
    df["saturation_text"] = df["saturation"].astype(str).str.lower()

    df["launch_score"] = 0.0

    df["launch_score"] += df["final_score"].clip(0, 100) * 0.35
    df["launch_score"] += df["opportunity_score"].clip(0, 100) * 0.20
    df["launch_score"] += df["profit_margin_pct"].clip(0, 80) * 0.15
    df["launch_score"] += df["roi_pct"].clip(0, 200) * 0.05
    df["launch_score"] += df["growth_pct"].clip(0, 100) * 0.10
    df["launch_score"] += df["p_c_ratio"].clip(0, 5) * 3

    df.loc[df["has_image"], "launch_score"] += 5
    df.loc[df["action_text"].str.contains("test", na=False), "launch_score"] += 8
    df.loc[df["risk_text"].str.contains("low", na=False), "launch_score"] += 8
    df.loc[df["risk_text"].str.contains("high", na=False), "launch_score"] -= 15
    df.loc[df["saturation_text"].str.contains("high", na=False), "launch_score"] -= 10

    # Avoid products that are too expensive for a beginner test.
    df.loc[df["product_cost"] > 60, "launch_score"] -= 15
    df.loc[df["product_cost"] <= 0, "launch_score"] -= 30

    # Reward beginner-friendly product costs.
    df.loc[(df["product_cost"] >= 5) & (df["product_cost"] <= 35), "launch_score"] += 8

    df["launch_score"] = df["launch_score"].round(2)

    df["launch_tier"] = "C - Skip For Now"
    df.loc[df["launch_score"] >= 70, "launch_tier"] = "B - Maybe Test"
    df.loc[df["launch_score"] >= 85, "launch_tier"] = "A - Test First"

    df["ad_angle"] = df.apply(make_ad_angle, axis=1)
    df["launch_next_step"] = df.apply(make_next_step, axis=1)

    output_cols = [
        "image_url",
        "product_name",
        "launch_tier",
        "launch_score",
        "ad_angle",
        "launch_next_step",
        "category",
        "product_cost",
        "estimated_sale_price",
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "p_c_ratio",
        "growth_pct",
        "final_score",
        "opportunity_score",
        "risk_level",
        "next_action",
        "risk_notes",
        "saturation",
        "store_name",
        "first_seen_at",
        "supplier_url",
    ]

    output_cols = [col for col in output_cols if col in df.columns]

    result = df.sort_values("launch_score", ascending=False)[output_cols]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    result.to_csv(OUTPUT_PATH, index=False)
    result.head(25).to_csv(TOP_OUTPUT_PATH, index=False)

    print()
    print("=" * 72)
    print("LAUNCH SHORTLIST CREATED")
    print(f"Total products ranked: {len(result)}")
    print(f"A - Test First: {(result['launch_tier'] == 'A - Test First').sum()}")
    print(f"B - Maybe Test: {(result['launch_tier'] == 'B - Maybe Test').sum()}")
    print(f"C - Skip For Now: {(result['launch_tier'] == 'C - Skip For Now').sum()}")
    print()
    print(f"Saved full shortlist: {OUTPUT_PATH}")
    print(f"Saved top 25: {TOP_OUTPUT_PATH}")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
