from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import sync_playwright


START_URL = "https://app.zendrop.com/product?page=1"
USER_DATA_DIR = ".browser/zendrop_profile"
OUTPUT_PATH = Path("data/zendrop_smart_capture.csv")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_money(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(",", "")
    match = re.search(r"\$?\s?(\d+(?:\.\d+)?)", text)
    return round(float(match.group(1)), 2) if match else 0.0


def clean_float(value: Any) -> float:
    if value is None:
        return 0.0
    match = re.search(r"([+-]?\d+(?:\.\d+)?)", str(value))
    return round(float(match.group(1)), 2) if match else 0.0


def normalize_key(name: str, image_url: str = "") -> str:
    name = re.sub(r"\s+", " ", str(name).lower()).strip()
    image_url = str(image_url).split("?")[0].lower().strip()
    return f"{name}|{image_url}"


def guess_category(text: str) -> str:
    text = text.lower()

    if any(w in text for w in ["pet", "dog", "cat", "leash", "collar", "shampoo"]):
        return "pets"
    if any(w in text for w in ["kitchen", "bottle", "cup", "cooking"]):
        return "kitchen"
    if any(w in text for w in ["beauty", "hair", "skin", "makeup", "iron"]):
        return "beauty"
    if any(w in text for w in ["fitness", "gym", "yoga", "ankle", "weight"]):
        return "fitness"
    if any(w in text for w in ["phone", "charger", "usb", "led"]):
        return "tech"
    if any(w in text for w in ["car", "auto", "vehicle"]):
        return "car"
    if any(w in text for w in ["shirt", "t-shirt", "hoodie", "dress", "jeans", "boots", "coat"]):
        return "clothing"
    if any(w in text for w in ["ring", "silver", "bracelet", "jewelry"]):
        return "jewelry"
    if any(w in text for w in ["decor", "sculpture", "home"]):
        return "home"

    return "general"


def load_existing_products() -> list[dict]:
    if not OUTPUT_PATH.exists():
        return []

    df = pd.read_csv(OUTPUT_PATH)
    return df.fillna("").to_dict("records")


def capture_product_cards(page) -> list[dict]:
    raw_cards = page.evaluate(
        """
        () => {
            const results = [];
            const seen = new Set();
            const buttons = Array.from(document.querySelectorAll("button, [role='button']"));

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

                    if (!(hasCost && hasPC && hasGrowth && hasMoney && hasRatio && hasImage)) continue;

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

            return results;
        }
        """
    )

    products = []

    for card in raw_cards:
        text = str(card.get("text", "")).strip()
        image_url = str(card.get("image_src", "")).strip()
        page_url = str(card.get("url", page.url)).strip()

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        money_values = re.findall(r"\$\s?\d+(?:\.\d+)?", text)
        ratio_values = re.findall(r"(\d+(?:\.\d+)?)\s*x", text.lower())
        growth_values = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", text)

        if not lines or not money_values or not ratio_values:
            continue

        store_name = lines[0]
        product_cost = clean_money(money_values[0])
        p_c_ratio = clean_float(ratio_values[0])
        growth_pct = clean_float(growth_values[0]) if growth_values else 0.0

        stop_index = None
        for i, line in enumerate(lines):
            if line.lower() in ["cost", "p/c", "growth"]:
                stop_index = i
                break

        name_lines = lines[1:stop_index] if stop_index else lines[1:3]
        product_name = " ".join(
            line for line in name_lines
            if "$" not in line and line.lower() not in ["cost", "p/c", "growth", "+ add", "add"]
        ).strip()

        if len(product_name) < 4:
            continue

        estimated_sale_price = round(product_cost * (1 + p_c_ratio), 2)

        products.append({
            "product_name": product_name,
            "store_name": store_name,
            "keyword": product_name.lower(),
            "product_cost": product_cost,
            "p_c_ratio": p_c_ratio,
            "growth_pct": growth_pct,
            "order_trend_score": "",
            "trend_change_pct": growth_pct,
            "saturation": "",
            "top_country": "",
            "shipping_cost": 0.00,
            "estimated_sale_price": estimated_sale_price,
            "supplier_url": page_url,
            "category": guess_category(text + " " + product_name),
            "source": "Zendrop Product Card",
            "supplier": "Zendrop",
            "image_url": image_url,
            "zendrop_product_id": "",
            "first_seen_at": now_text(),
            "last_seen_at": now_text(),
        })

    return products


def capture_detail_page(page) -> dict | None:
    try:
        detail = page.evaluate(
            """
            () => {
                const text = document.body.innerText || "";
                const titleEl = document.querySelector("h1, h2");
                const imgs = Array.from(document.querySelectorAll("img"));

                let biggestImg = "";
                let biggestArea = 0;

                for (const img of imgs) {
                    const rect = img.getBoundingClientRect();
                    const area = rect.width * rect.height;

                    if (area > biggestArea) {
                        biggestArea = area;
                        biggestImg = img.src || "";
                    }
                }

                return {
                    text: text,
                    title: titleEl ? titleEl.innerText || "" : "",
                    image_url: biggestImg,
                    url: window.location.href
                };
            }
            """
        )
    except Exception:
        return None

    text = str(detail.get("text", ""))
    title = str(detail.get("title", "")).strip()
    image_url = str(detail.get("image_url", "")).strip()
    url = str(detail.get("url", page.url)).strip()

    if "Product cost" not in text and "Order Trend Score" not in text:
        return None

    product_cost = 0.0
    order_trend_score = ""
    trend_change_pct = ""
    saturation = ""
    top_country = ""

    cost_match = re.search(r"Product cost\s*\$?\s?(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if cost_match:
        product_cost = clean_money(cost_match.group(1))

    score_match = re.search(r"Order Trend Score.*?(\d{1,3})", text, re.IGNORECASE | re.DOTALL)
    if score_match:
        order_trend_score = clean_float(score_match.group(1))

    change_match = re.search(r"Order Trend Score.*?([+-]\d+(?:\.\d+)?)\s*%", text, re.IGNORECASE | re.DOTALL)
    if change_match:
        trend_change_pct = clean_float(change_match.group(1))

    sat_match = re.search(r"Saturation.*?(Low|Medium|High)", text, re.IGNORECASE | re.DOTALL)
    if sat_match:
        saturation = sat_match.group(1).title()

    country_match = re.search(r"Orders by countries.*?([A-Z][a-zA-Z\s]+)\s+100%", text, re.IGNORECASE | re.DOTALL)
    if country_match:
        top_country = country_match.group(1).strip()

    if len(title) < 4:
        return None

    return {
        "product_name": title,
        "keyword": title.lower(),
        "product_cost": product_cost,
        "order_trend_score": order_trend_score,
        "trend_change_pct": trend_change_pct,
        "saturation": saturation,
        "top_country": top_country,
        "supplier_url": url,
        "category": guess_category(text + " " + title),
        "source": "Zendrop Detail Page",
        "supplier": "Zendrop",
        "image_url": image_url,
        "last_seen_at": now_text(),
    }


def save_products(products: list[dict]):
    if not products:
        return

    df = pd.DataFrame(products).fillna("")

    columns = [
        "product_name",
        "store_name",
        "keyword",
        "product_cost",
        "p_c_ratio",
        "growth_pct",
        "order_trend_score",
        "trend_change_pct",
        "saturation",
        "top_country",
        "shipping_cost",
        "estimated_sale_price",
        "supplier_url",
        "category",
        "source",
        "supplier",
        "image_url",
        "zendrop_product_id",
        "first_seen_at",
        "last_seen_at",
    ]

    for col in columns:
        if col not in df.columns:
            df[col] = ""

    df = df[columns]
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Saved {len(df)} products to {OUTPUT_PATH}")


def main():
    products = load_existing_products()
    product_map = {}

    for product in products:
        key = normalize_key(product.get("product_name", ""), product.get("image_url", ""))
        product_map[key] = product

    starting_count = len(product_map)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1700, "height": 1300},
        )

        page = browser.new_page()
        page.goto(START_URL, wait_until="commit")

        print()
        print("Zendrop Smart Capture")
        print("=" * 70)
        print("Browse Zendrop normally.")
        print("The script will:")
        print("- capture real product cards")
        print("- check image_url for better duplicate detection")
        print("- capture detail-page data when you click a product")
        print("- print NEW PRODUCT alerts")
        print("- print total products captured")
        print("Press Ctrl+C when done.")
        print("=" * 70)
        print(f"Starting products already saved: {starting_count}")
        print()

        last_save = time.time()

        try:
            while True:
                page.wait_for_timeout(1000)

                captured_now = capture_product_cards(page)

                detail_product = capture_detail_page(page)
                if detail_product:
                    captured_now.append(detail_product)

                total_before_capture = len(product_map)
                new_products_this_capture = []
                existing_products_seen = 0

                for item in captured_now:
                    key = normalize_key(item.get("product_name", ""), item.get("image_url", ""))

                    if not key.strip("|"):
                        continue

                    if key not in product_map:
                        product_map[key] = item
                        new_products_this_capture.append(item)
                    else:
                        existing_products_seen += 1
                        old = product_map[key]
                        for k, v in item.items():
                            if v not in ["", None, 0, 0.0]:
                                old[k] = v
                        old["last_seen_at"] = now_text()
                        product_map[key] = old

                if captured_now:
                    print()
                    print("=" * 72)
                    print("CAPTURE SUMMARY")
                    print(f"Already saved before this capture: {total_before_capture}")
                    print(f"Cards detected this capture: {len(captured_now)}")
                    print(f"Existing products re-seen/updated: {existing_products_seen}")
                    print(f"New products added this capture: {len(new_products_this_capture)}")
                    print(f"Total products saved now: {len(product_map)}")

                    if new_products_this_capture:
                        print()
                        print("New products added:")
                        for number, product in enumerate(new_products_this_capture, start=1):
                            print(
                                f"{number}. {product.get('product_name')} "
                                f"| Cost: ${product.get('product_cost')} "
                                f"| P/C: {product.get('p_c_ratio', '')} "
                                f"| Growth: {product.get('growth_pct', '')}%"
                            )
                    else:
                        print("No new products added this capture.")

                    print("=" * 72)
                    print()

                if time.time() - last_save >= 3:
                    save_products(list(product_map.values()))
                    print(f"Total unique products captured: {len(product_map)}")
                    last_save = time.time()

        except KeyboardInterrupt:
            print()
            print("Stopping capture...")

        finally:
            save_products(list(product_map.values()))
            browser.close()

    print()
    print("Done.")
    print(f"Final file: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
