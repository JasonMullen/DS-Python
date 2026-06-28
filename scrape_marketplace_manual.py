from __future__ import annotations

import argparse
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import sync_playwright


DATA_DIR = Path("data")

SITE_CONFIG = {
    "dhgate": {
        "start_url": "https://www.dhgate.com/",
        "output": DATA_DIR / "dhgate_manual_capture.csv",
        "price_multiplier": 2.6,
    },
    "shein": {
        "start_url": "https://us.shein.com/",
        "output": DATA_DIR / "shein_manual_capture.csv",
        "price_multiplier": 2.0,
    },
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def image_filename(url: str) -> str:
    url = clean_text(url).split("?")[0].strip("/")
    if not url:
        return ""
    return url.split("/")[-1].lower()


def parse_money_values(text: str) -> list[float]:
    values = re.findall(r"(?:US\s*)?\$\s?(\d+(?:\.\d+)?)", text)
    return [round(float(v), 2) for v in values]


def parse_int(value: str) -> int:
    value = clean_text(value).replace(",", "")
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else 0


def smart_price(cost: float, multiplier: float) -> float:
    if cost <= 0:
        return 0.0

    raw = cost * multiplier
    rounded = int(raw) + 0.99

    return round(rounded, 2)


def guess_product_name(text: str, image_alt: str) -> str:
    image_alt = clean_text(image_alt)

    bad_alt_words = ["image", "product", "logo", "avatar", "icon"]

    if (
        len(image_alt) >= 8
        and len(image_alt) <= 180
        and not any(word == image_alt.lower() for word in bad_alt_words)
    ):
        return image_alt

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    bad_phrases = [
        "free shipping",
        "add to cart",
        "quick view",
        "wishlist",
        "sold",
        "reviews",
        "rating",
        "coupon",
        "login",
        "sign in",
        "new user",
        "flash sale",
        "sponsored",
        "ad",
        "sale",
    ]

    for line in lines:
        lower = line.lower()

        if "$" in line:
            continue

        if len(line) < 6 or len(line) > 180:
            continue

        if any(phrase in lower for phrase in bad_phrases):
            continue

        return line

    return image_alt[:180]


def extract_rating(text: str) -> float:
    patterns = [
        r"(\d(?:\.\d)?)\s*out of\s*5",
        r"rating\s*[: ]\s*(\d(?:\.\d)?)",
        r"(\d(?:\.\d)?)\s*stars?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return float(match.group(1))

    return 0.0


def extract_reviews(text: str) -> int:
    patterns = [
        r"(\d[\d,]*)\s*reviews?",
        r"(\d[\d,]*)\s*ratings?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return parse_int(match.group(1))

    return 0


def extract_sold(text: str) -> int:
    patterns = [
        r"(\d[\d,]*)\+?\s*sold",
        r"(\d[\d,]*)\+?\s*orders?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return parse_int(match.group(1))

    return 0


def extract_shipping_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        lower = line.lower()

        if "shipping" in lower or "delivery" in lower:
            return line[:150]

    return ""


def extract_cards_from_page(page, site: str, keyword: str) -> list[dict]:
    raw_cards = page.evaluate(
        """
        () => {
            const results = [];
            const seen = new Set();

            const anchors = Array.from(document.querySelectorAll("a[href]"));

            for (const anchor of anchors) {
                let node = anchor;

                for (let depth = 0; depth < 9; depth++) {
                    if (!node) break;

                    const text = (node.innerText || "").trim();
                    const img = node.querySelector("img");

                    const hasImage = !!img && !!(img.currentSrc || img.src);
                    const hasPrice = /(?:US\\s*)?\\$\\s?\\d+(?:\\.\\d+)?/.test(text);
                    const enoughText = text.length >= 10;

                    if (hasImage && hasPrice && enoughText) {
                        const imageUrl = img.currentSrc || img.src || "";
                        const imageAlt = img.alt || "";
                        const href = anchor.href || "";

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

            return results.slice(0, 500);
        }
        """
    )

    products = []
    seen = set()
    config = SITE_CONFIG[site]

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

        dedupe_key = normalize(product_name) + "|" + image_filename(image_url)

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)

        products.append(
            {
                "source_site": site,
                "marketplace_source": site.upper(),
                "product_name": product_name,
                "keyword": keyword,
                "category": keyword if keyword else "marketplace",
                "product_cost": price_min,
                "price_min": price_min,
                "price_max": price_max,
                "shipping_cost": 0,
                "estimated_sale_price": smart_price(price_min, config["price_multiplier"]),
                "supplier_url": href,
                "image_url": image_url,
                "store_name": site.upper(),
                "rating": extract_rating(text),
                "reviews_count": extract_reviews(text),
                "sold_count": extract_sold(text),
                "shipping_text": extract_shipping_text(text),
                "p_c_ratio": "",
                "growth_pct": "",
                "order_trend_score": "",
                "saturation": "",
                "top_country": "",
                "capture_page_url": clean_text(raw.get("page_url", "")),
                "first_seen_at": now_text(),
                "last_seen_at": now_text(),
                "raw_card_text": text[:1000],
            }
        )

    return products


def detect_security(page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=2500).lower()
    except Exception:
        text = ""

    signals = [
        "verify you are human",
        "captcha",
        "security check",
        "unusual traffic",
        "access denied",
        "checking your browser",
        "cloudflare",
        "robot",
    ]

    return any(signal in text for signal in signals)


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

    combined["dedupe_key"] = (
        combined["source_site"].astype(str).str.lower()
        + "|"
        + combined["product_name"].astype(str).map(normalize)
        + "|"
        + combined["image_url"].astype(str).map(image_filename)
    )

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
    parser.add_argument("--site", required=True, choices=["dhgate", "shein"])
    parser.add_argument("--keyword", default="")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--interval", type=int, default=4)
    args = parser.parse_args()

    site = args.site
    config = SITE_CONFIG[site]
    output_path = config["output"]

    print()
    print("=" * 72)
    print(f"{site.upper()} MANUAL PRODUCT CAPTURE")
    print("This does not bypass security checks.")
    print("Browse/search/scroll manually. The script captures visible product cards.")
    print(f"Output: {output_path}")
    print("=" * 72)
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            f".browser/{site}_profile",
            channel="chrome",
            headless=False,
            viewport={"width": 1500, "height": 950},
        )

        page = browser.new_page()
        page.goto(config["start_url"], wait_until="commit", timeout=60000)
        page.wait_for_timeout(3000)

        print("In Chrome:")
        print(f"1. Log in if needed.")
        print(f"2. Search for products on {site.upper()}.")
        print("3. Scroll through product results.")
        print("4. Return here and press ENTER to begin capture.")
        input("Press ENTER when product cards are visible... ")

        start_time = time.time()
        all_seen_this_run = []
        loop_count = 0

        try:
            while True:
                loop_count += 1

                if detect_security(page):
                    print()
                    print("Security/captcha page detected.")
                    print("Complete it manually in Chrome, then return here.")
                    input("Press ENTER after the normal product page is visible... ")

                products = extract_cards_from_page(page, site, args.keyword)
                all_seen_this_run.extend(products)

                before, added, total = save_products(output_path, all_seen_this_run)

                print(
                    f"[{now_text()}] Loop {loop_count} | "
                    f"visible captured: {len(products)} | "
                    f"new added: {added} | "
                    f"total saved: {total}"
                )

                if args.limit > 0 and total >= args.limit:
                    print(f"Limit reached: {args.limit}")
                    break

                if args.seconds > 0 and (time.time() - start_time) >= args.seconds:
                    print(f"Time reached: {args.seconds} seconds")
                    break

                time.sleep(args.interval)

        except KeyboardInterrupt:
            print("Stopped manually. Saving final results...")

        finally:
            save_products(output_path, all_seen_this_run)
            browser.close()

    print()
    print(f"Done. Saved products to: {output_path}")


if __name__ == "__main__":
    main()
