from __future__ import annotations

import argparse
import json
import math
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
from playwright.sync_api import sync_playwright


DATA_DIR = Path("data")
OUTPUT_PATH = DATA_DIR / "dhgate_large_capture.csv"
KEYWORDS_PATH = DATA_DIR / "dhgate_seed_keywords.txt"
STATE_PATH = DATA_DIR / "dhgate_fast_crawl_state.json"

START_URL = "https://www.dhgate.com/"
USER_DATA_DIR = ".browser/dhgate_fast_profile"


# ============================================================
# BASIC HELPERS
# ============================================================

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


def parse_money_values(text: str) -> list[float]:
    text = clean_text(text).replace(",", "")
    values = re.findall(r"(?:US\s*)?\$\s?(\d+(?:\.\d+)?)", text)
    return [round(float(v), 2) for v in values]


def parse_int(value: Any) -> int:
    value = clean_text(value).replace(",", "")
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else 0


def smart_price(cost: float, multiplier: float = 2.6) -> float:
    if cost <= 0:
        return 0.0
    return round(math.ceil(cost * multiplier) - 0.01, 2)


def make_dedupe_key(product: dict) -> str:
    return (
        clean_text(product.get("source_site", "dhgate")).lower()
        + "|"
        + normalize(product.get("product_name", ""))
        + "|"
        + image_filename(product.get("image_url", ""))
    )


def fmt_seconds(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


# ============================================================
# PRODUCT PARSING
# ============================================================

def guess_product_name(text: str, image_alt: str) -> str:
    image_alt = clean_text(image_alt)

    if 8 <= len(image_alt) <= 180:
        bad_alt = {"image", "product", "logo", "icon", "avatar"}
        if image_alt.lower() not in bad_alt:
            return image_alt

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    bad_phrases = [
        "free shipping",
        "add to cart",
        "quick view",
        "wishlist",
        "reviews",
        "rating",
        "coupon",
        "login",
        "sign in",
        "new user",
        "flash sale",
        "sponsored",
        "dhgate",
        "buyer protection",
        "shop now",
        "view details",
        "recommended",
        "similar items",
        "buyer guarantee",
    ]

    for line in lines:
        lower = line.lower()

        if "$" in line:
            continue

        if len(line) < 8 or len(line) > 180:
            continue

        if any(phrase in lower for phrase in bad_phrases):
            continue

        if re.fullmatch(r"[\d\s\.\,\+\-\%]+", line):
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
        r"\((\d[\d,]*)\)",
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
        r"(\d[\d,]*)\+?\s*transactions?",
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
            return line[:180]

    return ""


# ============================================================
# FILE STORE
# ============================================================

class ProductStore:
    def __init__(self, path: Path):
        self.path = path
        self.rows: list[dict] = []
        self.keys: set[str] = set()
        self.dirty = False
        self.load()

    def load(self):
        if not self.path.exists():
            self.rows = []
            self.keys = set()
            return

        df = pd.read_csv(self.path).fillna("").astype("object")
        self.rows = df.to_dict("records")
        self.keys = set()

        for row in self.rows:
            self.keys.add(
                "dhgate"
                + "|"
                + normalize(row.get("product_name", ""))
                + "|"
                + image_filename(row.get("image_url", ""))
            )

    def add_many(self, products: list[dict]) -> int:
        added = 0

        for product in products:
            key = make_dedupe_key(product)

            if key in self.keys:
                continue

            self.keys.add(key)
            self.rows.append(product)
            added += 1

        if added:
            self.dirty = True

        return added

    def save(self, force: bool = False):
        if not self.dirty and not force:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)

        df = pd.DataFrame(self.rows).fillna("").astype("object")

        if not df.empty:
            df["dedupe_key"] = (
                df["source_site"].astype(str).str.lower()
                + "|"
                + df["product_name"].astype(str).map(normalize)
                + "|"
                + df["image_url"].astype(str).map(image_filename)
            )

            df = df.drop_duplicates(subset=["dedupe_key"], keep="last")
            df = df.drop(columns=["dedupe_key"])

        df.to_csv(self.path, index=False)

        self.rows = df.to_dict("records")
        self.keys = set()

        for row in self.rows:
            self.keys.add(
                "dhgate"
                + "|"
                + normalize(row.get("product_name", ""))
                + "|"
                + image_filename(row.get("image_url", ""))
            )

        self.dirty = False

    def count(self) -> int:
        return len(self.rows)


# ============================================================
# KEYWORDS + STATE
# ============================================================

def load_keywords(path: Path) -> list[str]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "home gadgets",
                    "kitchen gadgets",
                    "pet supplies",
                    "dog accessories",
                    "cat accessories",
                    "car accessories",
                    "phone accessories",
                    "beauty tools",
                    "home organization",
                    "cleaning tools",
                    "fitness equipment",
                    "travel accessories",
                    "garden tools",
                    "led lights",
                    "smart home",
                    "bathroom accessories",
                    "gift items",
                    "holiday decorations",
                ]
            ),
            encoding="utf-8",
        )

    keywords = []

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keywords.append(line)

    return list(dict.fromkeys(keywords))


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "completed_keywords": [],
            "last_keyword": "",
            "last_page": 0,
            "total_saved": 0,
            "updated_at": now_text(),
        }

    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_text()
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ============================================================
# PAGE CONTROL
# ============================================================

def make_search_url(keyword: str, page_num: int) -> str:
    encoded = quote_plus(keyword)
    return f"https://www.dhgate.com/wholesale/search.do?searchkey={encoded}&pageNo={page_num}"


def detect_security(page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=2500).lower()
    except Exception:
        text = ""

    current_url = page.url.lower()

    signals = [
        "verify you are human",
        "captcha",
        "security check",
        "unusual traffic",
        "access denied",
        "checking your browser",
        "cloudflare",
        "robot",
        "are you a human",
    ]

    return any(signal in text for signal in signals) or "captcha" in current_url


def pause_for_security(page):
    if detect_security(page):
        print()
        print("=" * 72)
        print("SECURITY CHECK DETECTED")
        print("Complete it manually in Chrome.")
        print("After normal DHgate product results are visible, return here.")
        print("=" * 72)
        input("Press ENTER to continue... ")
        page.wait_for_timeout(2500)


def page_has_no_results(page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=4000).lower()
    except Exception:
        return False

    signals = [
        "no result",
        "no products",
        "no items",
        "couldn't find",
        "did not match",
        "try different keywords",
    ]

    return any(signal in body for signal in signals)


def get_scroll_info(page) -> dict:
    try:
        return page.evaluate(
            """
            () => {
                const doc = document.documentElement;
                const body = document.body;

                return {
                    scroll_y: window.scrollY || doc.scrollTop || body.scrollTop || 0,
                    inner_height: window.innerHeight || 0,
                    scroll_height: Math.max(
                        body.scrollHeight,
                        body.offsetHeight,
                        doc.clientHeight,
                        doc.scrollHeight,
                        doc.offsetHeight
                    )
                };
            }
            """
        )
    except Exception:
        return {"scroll_y": 0, "inner_height": 0, "scroll_height": 0}


def fast_scroll(page, jump_px: int, wait_ms: int):
    page.evaluate("(jump) => window.scrollBy(0, jump)", jump_px)
    page.wait_for_timeout(wait_ms)


# ============================================================
# NETWORK OPTIMIZATION
# ============================================================

def install_fast_routes(context, turbo: bool):
    if not turbo:
        return

    blocked_url_parts = [
        "google-analytics",
        "googletagmanager",
        "doubleclick",
        "facebook",
        "tiktok",
        "hotjar",
        "criteo",
        "bing.com",
        "clarity",
        "analytics",
    ]

    def handle_route(route):
        request = route.request
        url = request.url.lower()
        resource_type = request.resource_type

        if resource_type in {"font", "media"}:
            route.abort()
            return

        if any(part in url for part in blocked_url_parts):
            route.abort()
            return

        route.continue_()

    context.route("**/*", handle_route)


# ============================================================
# EXTRACT PRODUCTS
# ============================================================

def extract_cards_from_page(page, keyword: str, page_num: int) -> list[dict]:
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
                    const hasPrice = /(?:US\\s*)?\\$\\s?\\d+(?:\\.\\d+)?/.test(text);
                    const hasUsefulText = text.length >= 15;

                    if (hasImage && hasPrice && hasUsefulText) {
                        const imageAlt = img ? img.alt || "" : "";
                        const href = anchor.href || "";

                        const key = href + "|" + imageUrl + "|" + text.slice(0, 160);

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

            return results.slice(0, 1200);
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

        if len(product_name) < 8:
            continue

        price_min = min(prices)
        price_max = max(prices)

        product = {
            "source_site": "dhgate",
            "marketplace_source": "DHGATE",
            "product_name": product_name,
            "keyword": keyword,
            "category": keyword,
            "product_cost": price_min,
            "price_min": price_min,
            "price_max": price_max,
            "shipping_cost": 0,
            "estimated_sale_price": smart_price(price_min),
            "supplier_url": href,
            "image_url": image_url,
            "store_name": "DHGATE",
            "rating": extract_rating(text),
            "reviews_count": extract_reviews(text),
            "sold_count": extract_sold(text),
            "shipping_text": extract_shipping_text(text),
            "p_c_ratio": "",
            "growth_pct": "",
            "order_trend_score": "",
            "saturation": "",
            "top_country": "",
            "crawl_keyword": keyword,
            "crawl_page": page_num,
            "capture_page_url": clean_text(raw.get("page_url", "")),
            "first_seen_at": now_text(),
            "last_seen_at": now_text(),
            "raw_card_text": text[:1200],
        }

        key = make_dedupe_key(product)

        if key in local_seen:
            continue

        local_seen.add(key)
        products.append(product)

    return products


def fast_scroll_and_capture(
    page,
    keyword: str,
    page_num: int,
    global_seen: set[str],
    max_scroll_steps: int,
    scroll_wait_ms: int,
    jump_px: int,
    stable_rounds_needed: int,
) -> list[dict]:
    collected = []
    last_height = 0
    last_count = 0
    stable_rounds = 0

    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(500)

    for step in range(1, max_scroll_steps + 1):
        pause_for_security(page)

        products = extract_cards_from_page(page, keyword, page_num)
        new_this_step = 0

        for product in products:
            key = make_dedupe_key(product)

            if key not in global_seen:
                global_seen.add(key)
                collected.append(product)
                new_this_step += 1

        info = get_scroll_info(page)
        y = int(info.get("scroll_y", 0))
        height = int(info.get("scroll_height", 0))
        inner = int(info.get("inner_height", 0))
        near_bottom = y + inner + 900 >= height

        if height == last_height and len(collected) == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        print(
            f"Scroll {step}/{max_scroll_steps} | "
            f"new={new_this_step} | page_new={len(collected)} | "
            f"y={y} | height={height} | bottom={near_bottom} | "
            f"stable={stable_rounds}/{stable_rounds_needed}"
        )

        if near_bottom and stable_rounds >= stable_rounds_needed:
            break

        last_height = height
        last_count = len(collected)

        fast_scroll(page, jump_px=jump_px, wait_ms=scroll_wait_ms)

    return collected


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords-file", default=str(KEYWORDS_PATH))
    parser.add_argument("--pages-per-keyword", type=int, default=0, help="0 means continue until no next page or repeated empty pages.")
    parser.add_argument("--max-products", type=int, default=5000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--turbo", action="store_true", help="Blocks heavy nonessential network requests.")
    parser.add_argument("--headless", action="store_true", help="Optional. May trigger more security checks.")
    parser.add_argument("--max-scroll-steps", type=int, default=18)
    parser.add_argument("--scroll-wait-ms", type=int, default=450)
    parser.add_argument("--page-wait-ms", type=int, default=1800)
    parser.add_argument("--jump-px", type=int, default=1600)
    parser.add_argument("--stable-rounds", type=int, default=2)
    parser.add_argument("--save-every-pages", type=int, default=5)
    parser.add_argument("--empty-pages-stop", type=int, default=2)
    parser.add_argument("--delay-between-pages", type=float, default=1.0)
    args = parser.parse_args()

    keywords = load_keywords(Path(args.keywords_file))
    state = load_state() if args.resume else {
        "completed_keywords": [],
        "last_keyword": "",
        "last_page": 0,
        "total_saved": 0,
        "updated_at": now_text(),
    }

    completed_keywords = set(state.get("completed_keywords", []))
    store = ProductStore(OUTPUT_PATH)
    global_seen = set(store.keys)

    start_time = time.time()
    pages_done = 0
    last_save_page_count = 0

    print()
    print("=" * 72)
    print("FAST DHGATE CRAWLER")
    print("Faster version: in-memory dedupe, batch saving, faster scroll, URL pagination.")
    print("Does not bypass security checks. It pauses for manual verification.")
    print(f"Keywords: {len(keywords)}")
    print(f"Pages per keyword: {args.pages_per_keyword if args.pages_per_keyword else 'UNTIL NO MORE PRODUCTS'}")
    print(f"Max products: {args.max_products}")
    print(f"Existing products: {store.count()}")
    print(f"Turbo: {args.turbo}")
    print(f"Output: {OUTPUT_PATH}")
    print("=" * 72)
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel="chrome",
            headless=args.headless,
            viewport={"width": 1500, "height": 950},
        )

        install_fast_routes(browser, args.turbo)

        page = browser.new_page()
        page.goto(START_URL, wait_until="commit", timeout=60000)
        page.wait_for_timeout(2000)

        print("Chrome opened.")
        print("Log in or complete checks if needed.")
        print("Then return here.")
        input("Press ENTER to begin fast DHgate crawl... ")

        try:
            for keyword in keywords:
                if keyword in completed_keywords:
                    print(f"Skipping completed keyword: {keyword}")
                    continue

                page_num = 1
                empty_pages_in_a_row = 0

                if args.resume and state.get("last_keyword") == keyword:
                    page_num = max(int(state.get("last_page", 0)) + 1, 1)

                print()
                print("#" * 72)
                print(f"STARTING KEYWORD: {keyword}")
                print(f"START PAGE: {page_num}")
                print("#" * 72)

                while True:
                    if store.count() >= args.max_products:
                        print("Max product limit reached.")
                        store.save(force=True)
                        save_state(state)
                        return

                    if args.pages_per_keyword > 0 and page_num > args.pages_per_keyword:
                        print(f"Reached page limit for keyword: {keyword}")
                        break

                    url = make_search_url(keyword, page_num)

                    print()
                    print("=" * 72)
                    print(f"Keyword: {keyword}")
                    print(f"Page: {page_num}")
                    print(f"Total saved before page: {store.count()}")
                    print(f"Opening: {url}")
                    print("=" * 72)

                    try:
                        page.goto(url, wait_until="commit", timeout=60000)
                        page.wait_for_timeout(args.page_wait_ms)
                        pause_for_security(page)

                        if page_has_no_results(page):
                            empty_pages_in_a_row += 1
                            print(f"No-results page detected. Empty streak: {empty_pages_in_a_row}/{args.empty_pages_stop}")
                        else:
                            new_products = fast_scroll_and_capture(
                                page=page,
                                keyword=keyword,
                                page_num=page_num,
                                global_seen=global_seen,
                                max_scroll_steps=args.max_scroll_steps,
                                scroll_wait_ms=args.scroll_wait_ms,
                                jump_px=args.jump_px,
                                stable_rounds_needed=args.stable_rounds,
                            )

                            added = store.add_many(new_products)

                            if added == 0:
                                empty_pages_in_a_row += 1
                            else:
                                empty_pages_in_a_row = 0

                            pages_done += 1

                            elapsed = time.time() - start_time
                            products_per_min = store.count() / max(elapsed / 60, 0.01)
                            pages_per_min = pages_done / max(elapsed / 60, 0.01)

                            remaining_products = max(args.max_products - store.count(), 0)
                            eta_seconds = remaining_products / max(products_per_min / 60, 0.01)

                            print()
                            print("PAGE RESULT")
                            print(f"Collected this page before dedupe: {len(new_products)}")
                            print(f"New saved after dedupe: {added}")
                            print(f"Total saved: {store.count()}")
                            print(f"Products/min: {products_per_min:.1f}")
                            print(f"Pages/min: {pages_per_min:.2f}")
                            print(f"Elapsed: {fmt_seconds(elapsed)}")
                            print(f"ETA to max-products: {fmt_seconds(eta_seconds)}")

                        state["last_keyword"] = keyword
                        state["last_page"] = page_num
                        state["total_saved"] = store.count()
                        save_state(state)

                        if pages_done - last_save_page_count >= args.save_every_pages:
                            store.save(force=True)
                            last_save_page_count = pages_done
                            print(f"Saved batch to: {OUTPUT_PATH}")

                        if empty_pages_in_a_row >= args.empty_pages_stop:
                            print(f"No useful products for {empty_pages_in_a_row} pages. Keyword finished.")
                            break

                        page_num += 1

                        if args.delay_between_pages > 0:
                            time.sleep(args.delay_between_pages)

                    except KeyboardInterrupt:
                        print("Stopped manually. Saving progress...")
                        store.save(force=True)
                        save_state(state)
                        return

                    except Exception as e:
                        print(f"Page failed: {e}")
                        empty_pages_in_a_row += 1
                        page_num += 1

                        if empty_pages_in_a_row >= args.empty_pages_stop:
                            print("Too many failed/empty pages. Moving to next keyword.")
                            break

                completed_keywords.add(keyword)
                state["completed_keywords"] = sorted(completed_keywords)
                save_state(state)
                store.save(force=True)

        finally:
            store.save(force=True)
            save_state(state)
            browser.close()

    print()
    print("=" * 72)
    print("FAST DHGATE CRAWL COMPLETE")
    print(f"Saved to: {OUTPUT_PATH}")
    print(f"Total saved: {store.count()}")
    print("=" * 72)


if __name__ == "__main__":
    main()
