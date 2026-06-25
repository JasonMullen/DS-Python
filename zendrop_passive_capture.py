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
OUTPUT_PATH = Path("data/zendrop_passive_capture.csv")

PRODUCT_NAME_KEYS = ["name", "title", "productName", "product_name", "displayName"]
COST_KEYS = ["cost", "productCost", "product_cost", "price", "minPrice", "sourcePrice", "supplierPrice"]
RETAIL_KEYS = ["retailPrice", "suggestedRetailPrice", "sellingPrice", "salePrice", "recommendedPrice"]
SHIPPING_KEYS = ["shipping", "shippingCost", "shipping_cost", "shippingPrice"]
CATEGORY_KEYS = ["category", "categoryName", "collection", "type"]
IMAGE_KEYS = ["image", "imageUrl", "thumbnail", "thumbnailUrl", "mainImage"]


def clean_money(value: Any) -> float:
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return round(float(value), 2)

    text = str(value).replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return round(float(match.group(1)), 2) if match else 0.0


def first_value(data: dict, keys: list[str]) -> Any:
    lower_map = {str(k).lower(): v for k, v in data.items()}

    for key in keys:
        value = lower_map.get(key.lower())
        if value not in [None, "", [], {}]:
            return value

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

    if any(w in text for w in ["pet", "dog", "cat", "leash", "collar"]):
        return "pets"
    if any(w in text for w in ["kitchen", "cooking", "bottle", "cup", "food"]):
        return "kitchen"
    if any(w in text for w in ["beauty", "hair", "skin", "makeup"]):
        return "beauty"
    if any(w in text for w in ["fitness", "gym", "yoga", "workout"]):
        return "fitness"
    if any(w in text for w in ["phone", "charger", "usb", "led"]):
        return "tech"
    if any(w in text for w in ["car", "auto", "vehicle"]):
        return "car"
    if any(w in text for w in ["shirt", "shoes", "dress", "jacket", "pants"]):
        return "clothing"
    if any(w in text for w in ["toy", "kids", "puzzle"]):
        return "toys"
    if any(w in text for w in ["organizer", "storage", "shelf"]):
        return "home"

    return "general"


def product_from_json(item: dict, fallback_url: str) -> dict | None:
    name = first_value(item, PRODUCT_NAME_KEYS)

    if not name:
        return None

    name = str(name).strip()

    if len(name) < 4 or len(name) > 180:
        return None

    product_cost = clean_money(first_value(item, COST_KEYS))
    shipping_cost = clean_money(first_value(item, SHIPPING_KEYS))
    estimated_sale_price = clean_money(first_value(item, RETAIL_KEYS))

    if estimated_sale_price <= 0 and product_cost > 0:
        estimated_sale_price = round(product_cost * 2.5, 2)

    if product_cost <= 0 and estimated_sale_price > 0:
        product_cost = round(estimated_sale_price * 0.4, 2)

    if product_cost <= 0:
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
        "source": "Zendrop Passive Capture",
        "supplier": "Zendrop",
        "image_url": image_url,
        "zendrop_product_id": product_id,
    }


def extract_visible_products(page) -> list[dict]:
    """
    Capture only real Zendrop product cards.

    A real product card should have:
    - an Add button
    - Cost
    - P/C
    - Growth
    - a product image
    - a product name
    """
    products = []

    try:
        raw_cards = page.evaluate(
            """
            () => {
                const results = [];
                const seen = new Set();

                const buttons = Array.from(
                    document.querySelectorAll("button, [role='button']")
                );

                for (const button of buttons) {
                    const buttonText = (button.innerText || "").trim().toLowerCase();

                    if (!buttonText.includes("add")) continue;

                    let node = button;

                    for (let depth = 0; depth < 10; depth++) {
                        if (!node || !node.parentElement) break;

                        node = node.parentElement;

                        const text = node.innerText || "";
                        const lower = text.toLowerCase();

                        const hasCost = lower.includes("cost");
                        const hasPC = lower.includes("p/c");
                        const hasGrowth = lower.includes("growth");
                        const hasMoney = /\\$\\s?\\d+(?:\\.\\d+)?/.test(text);
                        const hasRatio = /\\d+(?:\\.\\d+)?x/.test(lower);
                        const hasImage = node.querySelector("img") !== null;

                        const addCount = (lower.match(/\\badd\\b/g) || []).length;

                        if (
                            hasCost &&
                            hasPC &&
                            hasGrowth &&
                            hasMoney &&
                            hasRatio &&
                            hasImage &&
                            addCount === 1
                        ) {
                            const rect = node.getBoundingClientRect();

                            if (rect.width < 120 || rect.height < 150) continue;

                            const img = node.querySelector("img");
                            const key = text.replace(/\\s+/g, " ").trim();

                            if (seen.has(key)) break;
                            seen.add(key);

                            results.push({
                                text: text,
                                image_alt: img ? img.alt || "" : "",
                                image_src: img ? img.src || "" : "",
                                url: window.location.href
                            });

                            break;
                        }
                    }
                }

                return results;
            }
            """
        )
    except Exception as e:
        print(f"Could not scan product cards: {e}")
        return products

    for card in raw_cards:
        text = str(card.get("text", "")).strip()
        image_alt = str(card.get("image_alt", "")).strip()
        image_src = str(card.get("image_src", "")).strip()
        page_url = str(card.get("url", page.url)).strip()

        if not text:
            continue

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        money_values = re.findall(r"\$\s?\d+(?:\.\d+)?", text)
        ratio_values = re.findall(r"(\d+(?:\.\d+)?)\s*x", text.lower())
        growth_values = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", text)

        if not money_values or not ratio_values:
            continue

        product_cost = clean_money(money_values[0])
        p_c_ratio = float(ratio_values[0])
        growth_pct = float(growth_values[0]) if growth_values else 0.0

        if product_cost <= 0:
            continue

        estimated_sale_price = round(product_cost * (1 + p_c_ratio), 2)

        stop_index = None
        for i, line in enumerate(lines):
            lower_line = line.lower()
            if "cost" in lower_line or "p/c" in lower_line or "growth" in lower_line:
                stop_index = i
                break

        store_name = lines[0] if lines else "Zendrop"

        if stop_index is not None:
            possible_name_lines = lines[1:stop_index]
        else:
            possible_name_lines = lines[1:3]

        cleaned_name_lines = []

        bad_name_terms = [
            "cost",
            "p/c",
            "growth",
            "add",
            "zendrop",
            "connect store",
            "find products",
            "upgrade",
            "amazon products",
        ]

        for line in possible_name_lines:
            lower_line = line.lower()

            if "$" in line:
                continue

            if any(term == lower_line for term in bad_name_terms):
                continue

            if any(term in lower_line for term in ["cost", "p/c", "growth", "+ add"]):
                continue

            if len(line) < 3:
                continue

            cleaned_name_lines.append(line)

        product_name = " ".join(cleaned_name_lines).strip()

        if not product_name and image_alt:
            product_name = image_alt.strip()

        if len(product_name) < 4:
            continue

        products.append(
            {
                "product_name": product_name,
                "store_name": store_name,
                "keyword": product_name.lower(),
                "product_cost": product_cost,
                "p_c_ratio": p_c_ratio,
                "growth_pct": growth_pct,
                "shipping_cost": 0.00,
                "estimated_sale_price": estimated_sale_price,
                "supplier_url": page_url,
                "category": guess_category(text + " " + product_name),
                "source": "Zendrop Product Card",
                "supplier": "Zendrop",
                "image_url": image_src,
                "zendrop_product_id": "",
            }
        )

    return products


def save_products(products: list[dict]):
    if not products:
        return

    df = pd.DataFrame(products)
    df = df.drop_duplicates(subset=["product_name"])

    columns = [
        "product_name",
        "store_name",
        "keyword",
        "product_cost",
        "p_c_ratio",
        "growth_pct",
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
    df = df.sort_values(["category", "product_name"])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Saved {len(df)} products to {OUTPUT_PATH}")


def main():
    captured_products = []
    seen_names = set()

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

                if "login" in url or "account.zendrop.com" in url:
                    return

                content_type = response.headers.get("content-type", "")

                if "json" not in content_type:
                    return

                if response.status >= 400:
                    return

                data = json.loads(response.text())

                for item in walk_json(data):
                    product = product_from_json(item, response.url)
                    if product:
                        add_product(product)

            except BaseException:
                return

        page.on("response", handle_response)

        page.goto(START_URL, wait_until="commit")

        print()
        print("Zendrop Passive Capture Mode")
        print("=" * 70)
        print("1. Complete Zendrop verification manually.")
        print("2. Browse Zendrop normally.")
        print("3. Search categories/keywords manually.")
        print("4. Scroll normally.")
        print("5. The script will save products automatically every 10 seconds.")
        print("6. Press Ctrl+C when you are done.")
        print("=" * 70)
        print()

        last_save = time.time()

        try:
            while True:
                page.wait_for_timeout(5000)

                for product in extract_visible_products(page):
                    add_product(product)

                if time.time() - last_save >= 10:
                    print(f"Products captured so far: {len(captured_products)}")
                    save_products(captured_products)
                    last_save = time.time()

        except KeyboardInterrupt:
            print()
            print("Stopping capture and saving final CSV...")

        finally:
            save_products(captured_products)
            browser.close()

    print()
    print("Done.")
    print(f"Final file: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
