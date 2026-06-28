from __future__ import annotations

import argparse
import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import pandas as pd
from playwright.sync_api import sync_playwright


DATA_DIR = Path("data")
OUTPUT_PATH = DATA_DIR / "shein_smart_capture.csv"
USER_DATA_DIR = ".browser/shein_smart_profile"
START_URL = "https://us.shein.com/"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_url(value: Any) -> str:
    url = clean_text(value)

    if not url.startswith("http"):
        return ""

    try:
        parsed = urlparse(url)
        clean = parsed._replace(query="", fragment="")
        return urlunparse(clean).rstrip("/")
    except Exception:
        return url.split("?")[0].split("#")[0].rstrip("/")


def image_filename(value: Any) -> str:
    url = clean_url(value)

    if not url:
        return ""

    return url.split("/")[-1].lower()


def extract_shein_product_id(url: Any) -> str:
    url = clean_text(url)

    patterns = [
        r"-p-(\d+)",
        r"/p-(\d+)",
        r"goods_id=(\d+)",
        r"product_id=(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, url.lower())
        if match:
            return match.group(1)

    return ""


def parse_money_values(text: str) -> list[float]:
    text = clean_text(text).replace(",", "")
    values = re.findall(r"\$\s?(\d+(?:\.\d+)?)", text)
    return [round(float(v), 2) for v in values]


def smart_sale_price(cost: float) -> float:
    if cost <= 0:
        return 0.0

    if cost < 8:
        multiplier = 3.0
    elif cost < 20:
        multiplier = 2.5
    else:
        multiplier = 2.0

    return round(math.ceil(cost * multiplier) - 0.01, 2)


def make_key(row: dict) -> str:
    product_id = clean_text(row.get("shein_product_id", ""))

    if product_id:
        return f"shein|id|{product_id}"

    url = clean_url(row.get("supplier_url", ""))

    if url:
        return f"shein|url|{url}"

    return (
        "shein|name_image|"
        + normalize(row.get("product_name", ""))
        + "|"
        + image_filename(row.get("image_url", ""))
    )


def guess_product_name(text: str, image_alt: str) -> str:
    image_alt = clean_text(image_alt)

    if 6 <= len(image_alt) <= 170:
        bad_alt = {"image", "product", "logo", "icon", "avatar"}
        if image_alt.lower() not in bad_alt:
            return image_alt

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    bad_phrases = [
        "add to bag",
        "add to cart",
        "quick view",
        "wishlist",
        "free shipping",
        "coupon",
        "sale",
        "shein",
        "sign in",
        "login",
        "new user",
    ]

    for line in lines:
        lower = line.lower()

        if "$" in line:
            continue

        if len(line) < 6 or len(line) > 170:
            continue

        if any(phrase in lower for phrase in bad_phrases):
            continue

        return line

    return image_alt[:170]


def extract_reviews(text: str) -> int:
    text = clean_text(text).replace(",", "")

    patterns = [
        r"(\d+)\s*reviews?",
        r"(\d+)\s*ratings?",
        r"\((\d+)\)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return int(match.group(1))

    return 0


def extract_discount(text: str) -> int:
    match = re.search(r"(\d{1,2})\s*%\s*off", text.lower())

    if match:
        return int(match.group(1))

    return 0


def detect_security(page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=2500).lower()
    except Exception:
        body = ""

    signals = [
        "captcha",
        "verify you are human",
        "security check",
        "access denied",
        "unusual traffic",
        "robot",
    ]

    return any(signal in body for signal in signals)


def pause_for_security(page):
    if detect_security(page):
        print()
        print("=" * 72)
        print("SECURITY CHECK DETECTED")
        print("Complete it manually in Chrome.")
        print("After the normal SHEIN product page is visible, return here.")
        print("=" * 72)
        input("Press ENTER to continue... ")


def extract_visible_products(page, keyword: str) -> list[dict]:
    raw_cards = page.evaluate(
        """
        () => {
            const results = [];
            const seen = new Set();

            const anchors = Array.from(document.querySelectorAll("a[href]"));

            const getImageUrl = (img) => {
                if (!img) return "";
                return (
                    img.currentSrc ||
                    img.src ||
                    img.getAttribute("data-src") ||
                    img.getAttribute("data-original") ||
                    img.getAttribute("data-lazy") ||
                    img.getAttribute("lazy-src") ||
                    ""
                );
            };

            for (const anchor of anchors) {
                let node = anchor;

                for (let depth = 0; depth < 9; depth++) {
                    if (!node) break;

                    const text = (node.innerText || "").trim();
                    const img = node.querySelector("img");
                    const imageUrl = getImageUrl(img);

                    const hasImage = !!imageUrl;
                    const hasPrice = /\\$\\s?\\d+(?:\\.\\d+)?/.test(text);
                    const enoughText = text.length >= 8;

                    if (hasImage && hasPrice && enoughText) {
                        const href = anchor.href || "";
                        const imageAlt = img ? img.alt || "" : "";
                        const key = href + "|" + imageUrl + "|" + text.slice(0, 120);

                        if (!seen.has(key)) {
                            seen.add(key);

                            results.push({
                                text,
                                href,
                                image_url: imageUrl,
                                image_alt: imageAlt,
                                page_url: window.location.href
                            });
                        }

                        break;
                    }

                    node = node.parentElement;
                }
            }

            return results.slice(0, 800);
        }
        """
    )

    products = []
    local_seen = set()

    for raw in raw_cards:
        text = clean_text(raw.get("text", ""))
        href = clean_text(raw.get("href", ""))
        image_url = clean_text(raw.get("image_url", ""))
        image_alt = clean_text(raw.get("image_alt", ""))

        prices = parse_money_values(text)

        if not prices:
            continue

        product_name = guess_product_name(text, image_alt)

        if len(product_name) < 6:
            continue

        price_min = min(prices)
        price_max = max(prices)

        product = {
            "source_site": "shein",
            "marketplace_source": "SHEIN",
            "source_role": "TREND_REFERENCE",
            "shein_product_id": extract_shein_product_id(href),
            "product_name": product_name,
            "keyword": keyword,
            "category": keyword if keyword else "SHEIN Browse",
            "product_cost": price_min,
            "price_min": price_min,
            "price_max": price_max,
            "shipping_cost": 0,
            "estimated_sale_price": smart_sale_price(price_min),
            "supplier_url": href,
            "clean_supplier_url": clean_url(href),
            "image_url": image_url,
            "image_filename": image_filename(image_url),
            "store_name": "SHEIN",
            "reviews_count": extract_reviews(text),
            "discount_pct": extract_discount(text),
            "capture_page_url": clean_text(raw.get("page_url", "")),
            "first_seen_at": now_text(),
            "last_seen_at": now_text(),
            "raw_card_text": text[:1000],
        }

        key = make_key(product)

        if key in local_seen:
            continue

        local_seen.add(key)
        products.append(product)

    return products


def load_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path).fillna("").astype("object")


def save_products(path: Path, new_products: list[dict]) -> tuple[int, int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)

    old = load_existing(path)
    new = pd.DataFrame(new_products)

    if old.empty and new.empty:
        return 0, 0, 0

    if new.empty:
        old.to_csv(path, index=False)
        return len(old), 0, len(old)

    combined = pd.concat([old, new], ignore_index=True).fillna("").astype("object")

    if "first_seen_at" not in combined.columns:
        combined["first_seen_at"] = now_text()

    combined["dedupe_key"] = combined.apply(lambda row: make_key(row.to_dict()), axis=1)

    before = len(old)

    combined = combined.sort_values("last_seen_at").drop_duplicates(
        subset=["dedupe_key"],
        keep="last",
    )

    combined = combined.drop(columns=["dedupe_key"])
    combined.to_csv(path, index=False)

    after = len(combined)
    added = max(after - before, 0)

    return before, added, after


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", default="")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--interval", type=int, default=3)
    parser.add_argument("--scroll", action="store_true")
    args = parser.parse_args()

    print()
    print("=" * 72)
    print("SHEIN SMART CAPTURE")
    print("This works like your Zendrop capture.")
    print("Browse SHEIN manually. The script captures visible product cards.")
    print("No bot/security bypassing.")
    print(f"Output: {OUTPUT_PATH}")
    print("=" * 72)
    print()

    run_products = []

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1500, "height": 950},
        )

        page = browser.new_page()
        page.goto(START_URL, wait_until="commit", timeout=60000)
        page.wait_for_timeout(3000)

        print("In Chrome:")
        print("1. Search SHEIN manually.")
        print("2. Open the product results page.")
        print("3. Scroll normally if needed.")
        print("4. Return here and press ENTER.")
        input("Press ENTER when SHEIN product cards are visible... ")

        started = time.time()
        loop = 0

        try:
            while True:
                loop += 1
                pause_for_security(page)

                products = extract_visible_products(page, args.keyword)
                run_products.extend(products)

                before, added, total = save_products(OUTPUT_PATH, run_products)

                print(
                    f"[{now_text()}] Loop {loop} | "
                    f"visible captured={len(products)} | "
                    f"new added={added} | "
                    f"total saved={total}"
                )

                if args.scroll:
                    page.evaluate("(jump) => window.scrollBy(0, jump)", 1200)

                if args.seconds > 0 and time.time() - started >= args.seconds:
                    break

                time.sleep(args.interval)

        except KeyboardInterrupt:
            print("Stopped manually. Saving...")

        finally:
            save_products(OUTPUT_PATH, run_products)
            browser.close()

    print()
    print(f"Done. Saved SHEIN products to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
