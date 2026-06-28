from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import sync_playwright


START_URL = "https://app.zendrop.com/product?page=1"
USER_DATA_DIR = ".browser/zendrop_profile"
OUTPUT_PATH = Path("data/zendrop_account_products.csv")
MAX_PAGES = 10


PRODUCT_NAME_KEYS = [
    "name",
    "title",
    "productName",
    "product_name",
]

COST_KEYS = [
    "cost",
    "productCost",
    "product_cost",
    "price",
    "minPrice",
    "min_price",
    "variantPrice",
]

RETAIL_KEYS = [
    "retailPrice",
    "retail_price",
    "suggestedRetailPrice",
    "suggested_retail_price",
    "compareAtPrice",
    "sellingPrice",
    "salePrice",
]

SHIPPING_KEYS = [
    "shipping",
    "shippingCost",
    "shipping_cost",
    "shippingPrice",
]

CATEGORY_KEYS = [
    "category",
    "categoryName",
    "category_name",
    "collection",
]


def clean_money(value: Any) -> float:
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else 0.0


def first_value(data: dict, keys: list[str]) -> Any:
    for key in keys:
        if key in data and data[key] not in [None, "", [], {}]:
            return data[key]
    return None


def guess_category(text: str) -> str:
    text = text.lower()

    if any(w in text for w in ["pet", "dog", "cat"]):
        return "pets"
    if any(w in text for w in ["kitchen", "cooking", "food", "bottle"]):
        return "kitchen"
    if any(w in text for w in ["fitness", "gym", "yoga", "massage"]):
        return "fitness"
    if any(w in text for w in ["beauty", "hair", "skin", "makeup"]):
        return "beauty"
    if any(w in text for w in ["car", "auto", "vehicle"]):
        return "car"
    if any(w in text for w in ["phone", "usb", "charger", "led", "tech"]):
        return "tech"
    if any(w in text for w in ["shirt", "dress", "shoes", "jacket", "clothing"]):
        return "clothing"

    return "general"


def walk_json(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_json(value)

    elif isinstance(obj, list):
        for item in obj:
            yield from walk_json(item)


def looks_like_product(item: dict) -> bool:
    name = first_value(item, PRODUCT_NAME_KEYS)
    cost = first_value(item, COST_KEYS)

    if not name:
        return False

    if len(str(name)) < 4:
        return False

    if cost is None:
        return False

    return True


def product_from_json(item: dict, fallback_url: str) -> dict | None:
    if not looks_like_product(item):
        return None

    name = str(first_value(item, PRODUCT_NAME_KEYS)).strip()

    product_cost = clean_money(first_value(item, COST_KEYS))
    shipping_cost = clean_money(first_value(item, SHIPPING_KEYS))

    retail_value = first_value(item, RETAIL_KEYS)
    estimated_sale_price = clean_money(retail_value)

    if estimated_sale_price <= 0 and product_cost > 0:
        estimated_sale_price = round(product_cost * 2.5, 2)

    category_value = first_value(item, CATEGORY_KEYS)
    category = str(category_value).strip() if category_value else guess_category(name)

    product_id = item.get("id") or item.get("_id") or item.get("productId") or item.get("product_id")

    supplier_url = fallback_url
    if product_id:
        supplier_url = f"https://app.zendrop.com/product/{product_id}"

    if product_cost <= 0 or estimated_sale_price <= 0:
        return None

    return {
        "product_name": name,
        "keyword": name.lower(),
        "product_cost": product_cost,
        "shipping_cost": shipping_cost,
        "estimated_sale_price": estimated_sale_price,
        "supplier_url": supplier_url,
        "category": category,
        "source": "Zendrop Account",
    }


def extract_products_from_text(page, page_url: str) -> list[dict]:
    products = []

    possible_cards = page.locator("div").all()
    seen = set()

    for card in possible_cards:
        try:
            text = card.inner_text(timeout=300).strip()
        except Exception:
            continue

        if not text:
            continue

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        if len(lines) < 3:
            continue

        money_values = re.findall(r"\$\s?\d+(?:\.\d+)?", text)

        if len(money_values) < 1:
            continue

        possible_name = lines[0]

        if len(possible_name) < 4 or len(possible_name) > 100:
            continue

        if possible_name.lower() in seen:
            continue

        seen.add(possible_name.lower())

        product_cost = clean_money(money_values[0])

        if len(money_values) >= 2:
            estimated_sale_price = clean_money(money_values[-1])
        else:
            estimated_sale_price = round(product_cost * 2.5, 2)

        if product_cost <= 0 or estimated_sale_price <= 0:
            continue

        products.append(
            {
                "product_name": possible_name,
                "keyword": possible_name.lower(),
                "product_cost": product_cost,
                "shipping_cost": 0.00,
                "estimated_sale_price": estimated_sale_price,
                "supplier_url": page_url,
                "category": guess_category(text),
                "source": "Zendrop Account",
            }
        )

    return products


def main():
    captured_products = []
    seen_names = set()

    def add_product(product: dict):
        name = str(product.get("product_name", "")).strip().lower()

        if not name:
            return

        if name in seen_names:
            return

        seen_names.add(name)
        captured_products.append(product)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1400, "height": 900},
        )

        page = browser.new_page()

        def handle_response(response):
            try:
                url = response.url.lower()

                if "zendrop" not in url:
                    return

                content_type = response.headers.get("content-type", "")

                if "json" not in content_type:
                    return

                data = response.json()

                for item in walk_json(data):
                    product = product_from_json(item, response.url)
                    if product:
                        add_product(product)

            except Exception:
                return

        page.on("response", handle_response)

        print("Opening Zendrop account page...")
        page.goto(START_URL, wait_until="domcontentloaded")

        print()
        print("If you are not logged in, log into Zendrop in the browser window.")
        print("Once you can see products, come back here and press ENTER.")
        input("Press ENTER after Zendrop products are visible... ")

        for page_number in range(1, MAX_PAGES + 1):
            page_url = f"https://app.zendrop.com/product?page={page_number}"
            print(f"Scanning page {page_number}: {page_url}")

            page.goto(page_url, wait_until="domcontentloaded")
            time.sleep(6)

            fallback_products = extract_products_from_text(page, page_url)

            for product in fallback_products:
                add_product(product)

            print(f"Products captured so far: {len(captured_products)}")

        browser.close()

    if not captured_products:
        print("No products found.")
        print("Try increasing MAX_PAGES or manually scroll the product page before pressing ENTER.")
        return

    df = pd.DataFrame(captured_products)

    columns = [
        "product_name",
        "keyword",
        "product_cost",
        "shipping_cost",
        "estimated_sale_price",
        "supplier_url",
        "category",
        "source",
    ]

    df = df[[col for col in columns if col in df.columns]]
    df = df.drop_duplicates(subset=["product_name"])
    df = df.sort_values("product_name")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print()
    print(f"Saved {len(df)} Zendrop account products to:")
    print(OUTPUT_PATH)
    print()
    print("Next steps:")
    print("1. Review data/zendrop_account_products.csv")
    print("2. Copy it into data/supplier_products.csv if it looks good")
    print("3. Run: python -m dropship_researcher.main")


if __name__ == "__main__":
    main()
