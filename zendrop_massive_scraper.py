from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import sync_playwright


START_URL = "https://app.zendrop.com/product?page=1"
USER_DATA_DIR = ".browser/zendrop_profile"
OUTPUT_PATH = Path("data/zendrop_massive_products.csv")

MAX_PAGES = 100
SEARCH_TERMS = [
    "",
    "pet", "dog", "cat",
    "kitchen", "home", "beauty",
    "fitness", "gym", "car",
    "phone", "charger", "led",
    "toy", "clothing", "shoes",
    "jewelry", "office", "cleaning",
    "travel", "outdoor", "storage",
    "organizer",
]

PAGES_PER_SEARCH_TERM = 10
PAGE_WAIT_SECONDS = 5
SCROLL_TIMES = 6


PRODUCT_NAME_KEYS = ["name", "title", "productName", "product_name", "displayName"]
COST_KEYS = ["cost", "productCost", "product_cost", "price", "minPrice", "sourcePrice", "supplierPrice"]
RETAIL_KEYS = ["retailPrice", "suggestedRetailPrice", "sellingPrice", "salePrice", "recommendedPrice"]
SHIPPING_KEYS = ["shipping", "shippingCost", "shipping_cost", "shippingPrice"]
CATEGORY_KEYS = ["category", "categoryName", "collection", "type"]
IMAGE_KEYS = ["image", "imageUrl", "thumbnail", "thumbnailUrl", "mainImage"]


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def print_progress(products_count: int, completed_steps: int, total_steps: int, started_at: float, task: str):
    elapsed = time.time() - started_at

    if completed_steps <= 0:
        estimated_left = 0
        progress_pct = 0
    else:
        avg_time = elapsed / completed_steps
        remaining_steps = max(total_steps - completed_steps, 0)
        estimated_left = avg_time * remaining_steps
        progress_pct = (completed_steps / total_steps) * 100

    print()
    print("=" * 70)
    print(f"Current task: {task}")
    print(f"Products scraped: {products_count}")
    print(f"Steps completed: {completed_steps}/{total_steps}")
    print(f"Progress: {progress_pct:.1f}%")
    print(f"Elapsed time: {format_duration(elapsed)}")
    print(f"Estimated time left: {format_duration(estimated_left)}")
    print("=" * 70)
    print()


def clean_money(value: Any) -> float:
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return round(float(value), 2)

    text = str(value).replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return round(float(match.group(1)), 2) if match else 0.0


def first_value(data: dict, keys: list[str]) -> Any:
    for key in keys:
        if key in data and data[key] not in [None, "", [], {}]:
            return data[key]
    return None


def walk_json(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk_json(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_json(item)


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
    if any(w in text for w in ["phone", "usb", "charger", "led"]):
        return "tech"
    if any(w in text for w in ["shirt", "dress", "shoes", "jacket", "clothing"]):
        return "clothing"
    if any(w in text for w in ["toy", "kids", "game"]):
        return "toys"
    if any(w in text for w in ["necklace", "ring", "bracelet", "jewelry"]):
        return "jewelry"
    if any(w in text for w in ["organizer", "storage", "shelf"]):
        return "home"

    return "general"


def looks_like_product(item: dict) -> bool:
    name = first_value(item, PRODUCT_NAME_KEYS)
    cost = first_value(item, COST_KEYS)
    retail = first_value(item, RETAIL_KEYS)

    if not name:
        return False

    name_text = str(name).strip()

    if len(name_text) < 4 or len(name_text) > 180:
        return False

    if cost is None and retail is None:
        return False

    return True


def product_from_json(item: dict, fallback_url: str) -> dict | None:
    if not looks_like_product(item):
        return None

    name = str(first_value(item, PRODUCT_NAME_KEYS)).strip()

    product_cost = clean_money(first_value(item, COST_KEYS))
    shipping_cost = clean_money(first_value(item, SHIPPING_KEYS))
    estimated_sale_price = clean_money(first_value(item, RETAIL_KEYS))

    if estimated_sale_price <= 0 and product_cost > 0:
        estimated_sale_price = round(product_cost * 2.5, 2)

    if product_cost <= 0 and estimated_sale_price > 0:
        product_cost = round(estimated_sale_price * 0.4, 2)

    if product_cost <= 0 or estimated_sale_price <= 0:
        return None

    category_value = first_value(item, CATEGORY_KEYS)
    category = str(category_value).strip() if category_value else guess_category(name)

    image_value = first_value(item, IMAGE_KEYS)
    image_url = str(image_value) if image_value else ""

    product_id = item.get("id") or item.get("_id") or item.get("productId") or item.get("product_id") or ""

    supplier_url = fallback_url
    if product_id:
        supplier_url = f"https://app.zendrop.com/product/{product_id}"

    return {
        "product_name": name,
        "keyword": name.lower(),
        "product_cost": product_cost,
        "shipping_cost": shipping_cost,
        "estimated_sale_price": estimated_sale_price,
        "supplier_url": supplier_url,
        "category": category,
        "source": "Zendrop Account",
        "supplier": "Zendrop",
        "image_url": image_url,
        "zendrop_product_id": product_id,
    }


def extract_visible_products(page, page_url: str) -> list[dict]:
    products = []
    seen = set()

    try:
        cards = page.locator("div").all()
    except Exception:
        return products

    for card in cards:
        try:
            text = card.inner_text(timeout=300).strip()
        except Exception:
            continue

        if not text:
            continue

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        money_values = re.findall(r"\$\s?\d+(?:\.\d+)?", text)

        if len(lines) < 2 or not money_values:
            continue

        name = lines[0]

        if len(name) < 4 or len(name) > 120:
            continue

        key = name.lower()

        if key in seen:
            continue

        seen.add(key)

        product_cost = clean_money(money_values[0])
        sale_price = clean_money(money_values[-1]) if len(money_values) > 1 else round(product_cost * 2.5, 2)

        if product_cost <= 0:
            continue

        products.append(
            {
                "product_name": name,
                "keyword": name.lower(),
                "product_cost": product_cost,
                "shipping_cost": 0.00,
                "estimated_sale_price": sale_price,
                "supplier_url": page_url,
                "category": guess_category(text),
                "source": "Zendrop Account",
                "supplier": "Zendrop",
                "image_url": "",
                "zendrop_product_id": "",
            }
        )

    return products


def scroll_page(page):
    for _ in range(SCROLL_TIMES):
        page.mouse.wheel(0, 1800)
        time.sleep(1)


def save_products(products: list[dict]):
    if not products:
        return

    df = pd.DataFrame(products)

    columns = [
        "product_name",
        "keyword",
        "product_cost",
        "shipping_cost",
        "estimated_sale_price",
        "supplier_url",
        "category",
        "source",
        "supplier",
        "image_url",
        "zendrop_product_id",
    ]

    for col in columns:
        if col not in df.columns:
            df[col] = ""

    df = df[columns]
    df = df.drop_duplicates(subset=["product_name"])
    df = df.sort_values(["category", "product_name"])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Saved {len(df)} products to {OUTPUT_PATH}")


def main():
    captured_products = []
    seen_names = set()

    started_at = time.time()
    total_steps = MAX_PAGES + (len(SEARCH_TERMS) * PAGES_PER_SEARCH_TERM)
    completed_steps = 0

    def add_product(product: dict):
        name = str(product.get("product_name", "")).strip().lower()

        if not name or name in seen_names:
            return

        seen_names.add(name)
        captured_products.append(product)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1500, "height": 950},
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

        print("Opening Zendrop in Chrome...")
        page.goto(START_URL, wait_until="domcontentloaded")

        print()
        print("Make sure you are logged in and products are visible.")
        input("Press ENTER here when ready to start scraping... ")

        for page_number in range(1, MAX_PAGES + 1):
            page_url = f"https://app.zendrop.com/product?page={page_number}"
            task = f"Catalog page {page_number}/{MAX_PAGES}"

            page.goto(page_url, wait_until="domcontentloaded")
            time.sleep(PAGE_WAIT_SECONDS)
            scroll_page(page)

            for product in extract_visible_products(page, page_url):
                add_product(product)

            completed_steps += 1

            print_progress(
                products_count=len(captured_products),
                completed_steps=completed_steps,
                total_steps=total_steps,
                started_at=started_at,
                task=task,
            )

            if completed_steps % 5 == 0:
                save_products(captured_products)

        for term in SEARCH_TERMS:
            for page_number in range(1, PAGES_PER_SEARCH_TERM + 1):
                if term:
                    page_url = f"https://app.zendrop.com/product?page={page_number}&search={term}"
                else:
                    page_url = f"https://app.zendrop.com/product?page={page_number}"

                task = f"Search '{term or 'blank'}' page {page_number}/{PAGES_PER_SEARCH_TERM}"

                page.goto(page_url, wait_until="domcontentloaded")
                time.sleep(PAGE_WAIT_SECONDS)
                scroll_page(page)

                for product in extract_visible_products(page, page_url):
                    add_product(product)

                completed_steps += 1

                print_progress(
                    products_count=len(captured_products),
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                    started_at=started_at,
                    task=task,
                )

                if completed_steps % 5 == 0:
                    save_products(captured_products)

        browser.close()

    save_products(captured_products)

    print()
    print("Zendrop scrape complete.")
    print(f"Final file saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
