from pathlib import Path
import pandas as pd
import math


INPUT_PATH = Path("output/top_25_launch_shortlist.csv")
OUTPUT_PATH = Path("output/product_test_plan.csv")


def money(value):
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except Exception:
        return 0.0


def smart_price(value):
    price = money(value)

    if price <= 0:
        return ""

    rounded = math.ceil(price) - 0.01
    return round(rounded, 2)


def make_customer(row):
    name = str(row.get("product_name", "")).lower()
    category = str(row.get("category", "")).lower()

    if "pet" in name or "dog" in name or "cat" in name or "pet" in category:
        return "Pet owners who want easier daily care"

    if "home" in name or "decor" in name or "kitchen" in name:
        return "People who like practical home upgrades"

    if "beauty" in name or "skin" in name or "hair" in name:
        return "People interested in appearance, grooming, or self-care"

    if "fitness" in name or "sport" in name or "gym" in name:
        return "People interested in fitness, confidence, or performance"

    if "gift" in name or "christmas" in name or "holiday" in name:
        return "Gift buyers looking for easy seasonal purchases"

    if "car" in name or "auto" in name:
        return "Car owners who want useful accessories"

    return "Impulse buyers looking for useful problem-solving products"


def make_pain_point(row):
    name = str(row.get("product_name", "")).lower()

    if "pet" in name or "dog" in name or "cat" in name:
        return "Pet care is messy, annoying, or time-consuming"

    if "organizer" in name or "storage" in name:
        return "Clutter makes daily life harder"

    if "clean" in name or "wipe" in name:
        return "People want a faster and easier way to clean"

    if "decor" in name or "home" in name:
        return "People want their space to look better without spending too much"

    if "gift" in name or "christmas" in name:
        return "People need simple gift ideas"

    return "The product should solve a clear everyday problem"


def make_hooks(row):
    name = str(row.get("product_name", "")).strip()
    customer = make_customer(row)
    pain = make_pain_point(row)

    return [
        f"This simple product solves a problem most people ignore: {pain}.",
        f"If you are one of these people — {customer.lower()} — this could make life easier.",
        f"I tested this because it looked small, useful, and easy to impulse-buy: {name}.",
    ]


def make_video_script(row):
    name = str(row.get("product_name", "")).strip()
    pain = make_pain_point(row)

    return (
        f"Hook: 'I found a product that fixes this annoying problem.' "
        f"Problem: {pain}. "
        f"Show the product: {name}. "
        f"Demonstrate how it works. "
        f"Explain why it is useful. "
        f"End with: 'Would you use this?'"
    )


def make_pass_fail_rule(row):
    profit = money(row.get("estimated_profit", 0))
    cost = money(row.get("product_cost", 0))

    if profit >= 20 and cost <= 35:
        return "Test with small budget. Keep if clicks and add-to-carts are strong."

    if profit >= 15:
        return "Review competitors before testing. Only test if product page looks strong."

    return "Do not test unless manually reviewed first."


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError("Missing output/top_25_launch_shortlist.csv. Run make_launch_shortlist.py first.")

    df = pd.read_csv(INPUT_PATH).fillna("")

    rows = []

    for idx, row in df.iterrows():
        hooks = make_hooks(row)

        test_price = smart_price(row.get("estimated_sale_price", ""))

        rows.append({
            "test_rank": idx + 1,
            "image_url": row.get("image_url", ""),
            "product_name": row.get("product_name", ""),
            "launch_tier": row.get("launch_tier", ""),
            "launch_score": row.get("launch_score", ""),
            "product_cost": row.get("product_cost", ""),
            "recommended_test_price": test_price,
            "estimated_profit": row.get("estimated_profit", ""),
            "profit_margin_pct": row.get("profit_margin_pct", ""),
            "roi_pct": row.get("roi_pct", ""),
            "ideal_customer": make_customer(row),
            "customer_pain_point": make_pain_point(row),
            "product_page_angle": row.get("ad_angle", ""),
            "ad_hook_1": hooks[0],
            "ad_hook_2": hooks[1],
            "ad_hook_3": hooks[2],
            "short_video_script": make_video_script(row),
            "test_budget": "$10-$20 small test",
            "pass_fail_rule": make_pass_fail_rule(row),
            "risk_level": row.get("risk_level", ""),
            "risk_notes": row.get("risk_notes", ""),
            "supplier_url": row.get("supplier_url", ""),
        })

    output = pd.DataFrame(rows)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(OUTPUT_PATH, index=False)

    print()
    print("=" * 72)
    print("PRODUCT TEST PLAN CREATED")
    print(f"Products planned: {len(output)}")
    print(f"Saved to: {OUTPUT_PATH}")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
