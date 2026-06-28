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
from urllib.parse import quote_plus, urlparse, urlunparse

import pandas as pd
from playwright.sync_api import sync_playwright


DATA_DIR = Path("data")
OUTPUT_PATH = DATA_DIR / "shein_large_capture.csv"
STATE_PATH = DATA_DIR / "shein_full_keyword_state.json"

START_URL = "https://us.shein.com/"
USER_DATA_DIR = ".browser/shein_profile"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_url(url: Any) -> str:
    url = clean_text(url)

    if not url.startswith("http"):
        return ""

    try:
        parsed = urlparse(url)
        clean = parsed._replace(query="", fragment="")
        return urlunparse(clean).rstrip("/")
    except Exception:
        return url.split("?")[0].split("#")[0].rstrip("/")


def image_filename(url: Any) -> str:
    url = normalize_url(url)

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


def parse_int(value: Any) -> int:
    text = clean_text(value).replace(",", "")
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 0


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


def make_search_url(keyword: str, page_num: int) -> str:
    encoded = quote_plus(keyword)
    return f"https://us.shein.com/pdsearch/{encoded}/?page={page_num}"


def make_product_key(product: dict) -> str:
    product_id = clean_text(product.get("shein_product_id", ""))

    if product_id:
        return f"shein|id|{product_id}"

    url = normalize_url(product.get("supplier_url", ""))

    if url:
        return f"shein|url|{url}"

    return (
        "shein|name_image|"
        + normalize(product.get("product_name", ""))
        + "|"
        + image_filename(product.get("image_url", ""))
    )


def make_page_fingerprint(products: list[dict]) -> str:
    keys = sorted([make_product_key(p) for p in products[:20]])
    return "|".join(keys)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}

    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["_updated_at"] = now_text()
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def keyword_key(keyword: str) -> str:
    return normalize(keyword).replace(" ", "_")


class ProductStore:
    def __init__(self, path: Path):
        self.path = path
        self.rows: list[dict] = []
        self.keys: set[str] = set()
        self.load()

    def load(self):
        if not self.path.exists():
            return

        df = pd.read_csv(self.path).fillna("").astype("object")
        self.rows = df.to_dict("records")
        self.keys = set(make_product_key(row) for row in self.rows)

    def add_many(self, products: list[dict]) -> int:
        added = 0

        for product in products:
            key = make_product_key(product)

            if key in self.keys:
                continue

            self.keys.add(key)
            self.rows.append(product)
            added += 1

        return added

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)

        if not self.rows:
            pd.DataFrame().to_csv(self.path, index=False)
            return

        df = pd.DataFrame(self.rows).fillna("").astype("object")
        df["dedupe_key"] = df.apply(lambda row: make_product_key(row.to_dict()), axis=1)
        df = df.drop_duplicates(subset=["dedupe_key"], keep="last")
        df = df.drop(columns=["dedupe_key"])
        df.to_csv(self.path, index=False)

        self.rows = df.to_dict("records")
        self.keys = set(make_product_key(row) for row in self.rows)

    def count(self) -> int:
        return len(self.rows)


def detect_security(page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=2500).lower()
    except Exception:
        text = ""

    url = page.url.lower()

    signals = [
        "captcha",
        "verify you are human",
        "security check",
        "access denied",
        "unusual traffic",
        "robot",
        "are you human",
    ]

    return any(signal in text for signal in signals) or "captcha" in url


def pause_for_security(page):
    if detect_security(page):
        print()
        print("=" * 72)
        print("SECURITY CHECK DETECTED")
        print("Complete it manually in Chrome.")
        print("After the normal SHEIN product page is visible, return here.")
        print("=" * 72)
        input("Press ENTER to continue... ")
        page.wait_for_timeout(2500)


def page_has_no_results(page) -> bool:
    try:
        body = page.locator("body").inner_text(timeout=4000).lower()
    except Exception:
        return False

    signals = [
        "no results",
        "no result",
        "no products",
        "try another keyword",
        "couldn't find",
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


def install_fast_routes(context, turbo: bool):
    if not turbo:
        return

    blocked = [
        "google-analytics",
        "googletagmanager",
        "doubleclick",
        "facebook",
        "tiktok",
        "hotjar",
        "criteo",
        "clarity",
        "analytics",
        "ads",
    ]

    def handle_route(route):
        request = route.request
        url = request.url.lower()

        if request.resource_type in {"font", "media"}:
            route.abort()
            return

        if any(part in url for part in blocked):
            route.abort()
            return

        route.continue_()

    context.route("**/*", handle_route)


def guess_product_name(text: str, image_alt: str) -> str:
    image_alt = clean_text(image_alt)

    if 6 <= len(image_alt) <= 160:
        return image_alt

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    bad = [
        "add to bag",
        "add to cart",
        "quick view",
        "wishlist",
        "sale",
        "discount",
        "coupon",
        "free shipping",
        "shein",
        "$",
    ]

    for line in lines:
        lower = line.lower()

        if len(line) < 6 or len(line) > 160:
            continue

        if any(word in lower for word in bad):
            continue

        return line

    return image_alt[:160]


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


def extract_discount(text: str) -> int:
    match = re.search(r"(\d{1,2})\s*%\s*off", text.lower())

    if match:
        return int(match.group(1))

    return 0


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
                    const hasPrice = /\\$\\s?\\d+(?:\\.\\d+)?/.test(text);
                    const useful = text.length >= 8;

                    if (hasImage && hasPrice && useful) {
                        const href = anchor.href || "";
                        const imageAlt = img ? img.alt || "" : "";
                        const key = href + "|" + imageUrl + "|" + text.slice(0, 100);

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
            "category": keyword,
            "product_cost": price_min,
            "price_min": price_min,
            "price_max": price_max,
            "shipping_cost": 0,
            "estimated_sale_price": smart_sale_price(price_min),
            "supplier_url": href,
            "clean_supplier_url": normalize_url(href),
            "image_url": image_url,
            "image_filename": image_filename(image_url),
            "store_name": "SHEIN",
            "reviews_count": extract_reviews(text),
            "discount_pct": extract_discount(text),
            "crawl_keyword": keyword,
            "crawl_page": page_num,
            "capture_page_url": clean_text(raw.get("page_url", "")),
            "first_seen_at": now_text(),
            "last_seen_at": now_text(),
            "raw_card_text": text[:1000],
        }

        key = make_product_key(product)

        if key in local_seen:
            continue

        local_seen.add(key)
        products.append(product)

    return products


def scroll_and_capture(page, keyword: str, page_num: int, args) -> list[dict]:
    collected = {}
    stable_rounds = 0
    last_height = 0
    last_count = 0

    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(500)

    for step in range(1, args.max_scroll_steps + 1):
        pause_for_security(page)

        products = extract_cards_from_page(page, keyword, page_num)

        for product in products:
            collected[make_product_key(product)] = product

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
            f"Scroll {step}/{args.max_scroll_steps} | "
            f"visible_unique={len(collected)} | "
            f"bottom={near_bottom} | "
            f"stable={stable_rounds}/{args.stable_rounds}"
        )

        if near_bottom and stable_rounds >= args.stable_rounds:
            break

        last_height = height
        last_count = len(collected)

        page.evaluate("(jump) => window.scrollBy(0, jump)", args.jump_px)
        page.wait_for_timeout(args.scroll_wait_ms)

    return list(collected.values())


def crawl_keyword(page, keyword: str, args, store: ProductStore, state: dict):
    key = keyword_key(keyword)

    if key not in state:
        state[key] = {
            "keyword": keyword,
            "next_page": 1,
            "completed": False,
            "last_page_fingerprint": "",
            "repeat_pages": 0,
            "empty_pages": 0,
            "total_added_for_keyword": 0,
        }

    keyword_state = state[key]

    if keyword_state.get("completed") and not args.force:
        print(f"Skipping completed keyword: {keyword}")
        return

    page_num = int(keyword_state.get("next_page", 1)) if args.resume else 1
    pages_done = 0
    started = time.time()

    print()
    print("#" * 72)
    print(f"STARTING SHEIN KEYWORD: {keyword}")
    print(f"START PAGE: {page_num}")
    print("#" * 72)

    while True:
        if args.max_pages > 0 and page_num > args.max_pages:
            keyword_state["completed"] = True
            save_state(state)
            store.save()
            return

        if args.max_products > 0 and store.count() >= args.max_products:
            store.save()
            save_state(state)
            return

        url = make_search_url(keyword, page_num)

        print()
        print("=" * 72)
        print(f"Keyword: {keyword}")
        print(f"Page: {page_num}")
        print(f"Total unique saved: {store.count()}")
        print(f"Opening: {url}")
        print("=" * 72)

        try:
            page.goto(url, wait_until="commit", timeout=60000)
            page.wait_for_timeout(args.page_wait_ms)
            pause_for_security(page)

            if args.manual_start and page_num == 1:
                print()
                print("Check Chrome. If the search page is wrong, search manually on SHEIN.")
                input("Press ENTER when the correct product results are visible... ")

            if page_has_no_results(page):
                keyword_state["empty_pages"] += 1
                print(f"Empty page: {keyword_state['empty_pages']}/{args.empty_pages_stop}")

                if keyword_state["empty_pages"] >= args.empty_pages_stop:
                    keyword_state["completed"] = True
                    store.save()
                    save_state(state)
                    return

                page_num += 1
                keyword_state["next_page"] = page_num
                save_state(state)
                continue

            products = scroll_and_capture(page, keyword, page_num, args)
            fingerprint = make_page_fingerprint(products)

            if fingerprint and fingerprint == keyword_state.get("last_page_fingerprint", ""):
                keyword_state["repeat_pages"] += 1
            else:
                keyword_state["repeat_pages"] = 0

            keyword_state["last_page_fingerprint"] = fingerprint

            added = store.add_many(products)
            keyword_state["total_added_for_keyword"] += added
            keyword_state["empty_pages"] = keyword_state["empty_pages"] + 1 if len(products) == 0 else 0

            pages_done += 1
            elapsed = time.time() - started
            ppm = pages_done / max(elapsed / 60, 0.01)
            products_per_min = keyword_state["total_added_for_keyword"] / max(elapsed / 60, 0.01)

            print()
            print("PAGE RESULT")
            print(f"Products visible: {len(products)}")
            print(f"New unique added: {added}")
            print(f"Total unique saved: {store.count()}")
            print(f"Pages/min: {ppm:.2f}")
            print(f"Products/min: {products_per_min:.1f}")
            print(f"Repeat pages: {keyword_state['repeat_pages']}/{args.repeat_pages_stop}")

            keyword_state["next_page"] = page_num + 1
            keyword_state["last_page"] = page_num
            keyword_state["last_updated"] = now_text()
            state["_total_saved"] = store.count()
            save_state(state)

            if pages_done % args.save_every_pages == 0:
                store.save()
                print(f"Saved batch: {OUTPUT_PATH}")

            if keyword_state["repeat_pages"] >= args.repeat_pages_stop:
                print("SHEIN keyword finished because pages are repeating.")
                keyword_state["completed"] = True
                store.save()
                save_state(state)
                return

            if keyword_state["empty_pages"] >= args.empty_pages_stop:
                print("SHEIN keyword finished because pages are empty.")
                keyword_state["completed"] = True
                store.save()
                save_state(state)
                return

            page_num += 1

            if args.delay_between_pages > 0:
                time.sleep(args.delay_between_pages)

        except KeyboardInterrupt:
            print("Stopped manually. Saving progress...")
            keyword_state["next_page"] = page_num
            store.save()
            save_state(state)
            raise

        except Exception as e:
            print(f"Page failed: {e}")
            keyword_state["empty_pages"] += 1
            page_num += 1
            keyword_state["next_page"] = page_num
            save_state(state)

            if keyword_state["empty_pages"] >= args.empty_pages_stop:
                keyword_state["completed"] = True
                store.save()
                save_state(state)
                return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", required=True, help='Example: "soccer shirts"')
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--manual-start", action="store_true")
    parser.add_argument("--max-pages", type=int, default=0, help="0 means all available pages until empty/repeating.")
    parser.add_argument("--max-products", type=int, default=0, help="0 means no product limit.")
    parser.add_argument("--empty-pages-stop", type=int, default=3)
    parser.add_argument("--repeat-pages-stop", type=int, default=2)
    parser.add_argument("--turbo", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-scroll-steps", type=int, default=18)
    parser.add_argument("--scroll-wait-ms", type=int, default=350)
    parser.add_argument("--page-wait-ms", type=int, default=1800)
    parser.add_argument("--jump-px", type=int, default=1800)
    parser.add_argument("--stable-rounds", type=int, default=2)
    parser.add_argument("--save-every-pages", type=int, default=5)
    parser.add_argument("--delay-between-pages", type=float, default=0.75)
    args = parser.parse_args()

    store = ProductStore(OUTPUT_PATH)
    state = load_state() if args.resume else {}

    print()
    print("=" * 72)
    print("SHEIN FULL KEYWORD CRAWLER")
    print("Trend/reference source only. No security bypassing.")
    print(f"Keyword: {args.keyword}")
    print(f"Max pages: {args.max_pages if args.max_pages else 'ALL AVAILABLE'}")
    print(f"Existing unique products: {store.count()}")
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
        input("Press ENTER to begin SHEIN crawl... ")

        try:
            crawl_keyword(page, args.keyword, args, store, state)

        except KeyboardInterrupt:
            print("Stopped by user.")

        finally:
            store.save()
            save_state(state)
            browser.close()

    print()
    print("=" * 72)
    print("SHEIN CRAWL COMPLETE")
    print(f"Total unique products saved: {store.count()}")
    print(f"Saved to: {OUTPUT_PATH}")
    print("=" * 72)


if __name__ == "__main__":
    main()
