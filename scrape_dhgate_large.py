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
STATE_PATH = DATA_DIR / "dhgate_crawl_state.json"

START_URL = "https://www.dhgate.com/"
USER_DATA_DIR = ".browser/dhgate_large_profile"


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
# FILE + STATE
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


def load_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path).fillna("").astype("object")


def load_seen_keys(path: Path) -> set[str]:
    df = load_existing(path)

    if df.empty:
        return set()

    keys = set()

    for _, row in df.iterrows():
        keys.add(
            "dhgate"
            + "|"
            + normalize(row.get("product_name", ""))
            + "|"
            + image_filename(row.get("image_url", ""))
        )

    return keys


def append_and_save(path: Path, new_products: list[dict]) -> tuple[int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)

    old = load_existing(path)
    new = pd.DataFrame(new_products)

    if old.empty and new.empty:
        return 0, 0

    if new.empty:
        old.to_csv(path, index=False)
        return 0, len(old)

    combined = pd.concat([old, new], ignore_index=True).fillna("").astype("object")

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

    return added, after


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
        text = page.locator("body").inner_text(timeout=3000).lower()
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
        page.wait_for_timeout(3000)


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


def is_near_bottom(page, buffer_px: int = 800) -> bool:
    info = get_scroll_info(page)

    return (
        float(info.get("scroll_y", 0))
        + float(info.get("inner_height", 0))
        + buffer_px
        >= float(info.get("scroll_height", 0))
    )


def scroll_step(page):
    distance = random.randint(750, 1300)
    page.mouse.wheel(0, distance)
    page.wait_for_timeout(random.randint(900, 1600))


def get_pagination_status(page) -> dict:
    """
    Reads visible pagination buttons like:
    < 1 2 3 4 5 6 7 8 9 10 >
    """
    try:
        return page.evaluate(
            """
            () => {
                const elements = Array.from(document.querySelectorAll("a, button, [role='button'], li, span"));
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return (
                        rect.width > 8 &&
                        rect.height > 8 &&
                        rect.top >= 0 &&
                        rect.top <= window.innerHeight + 300 &&
                        style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        style.opacity !== "0"
                    );
                };

                const items = elements
                    .filter(visible)
                    .map((el, index) => {
                        const text = (el.innerText || el.textContent || "").trim();
                        const aria = (el.getAttribute("aria-label") || "").trim();
                        const title = (el.getAttribute("title") || "").trim();
                        const cls = (el.className || "").toString();
                        const href = el.getAttribute("href") || "";
                        const bg = window.getComputedStyle(el).backgroundColor;
                        const color = window.getComputedStyle(el).color;

                        return {
                            index,
                            text,
                            aria,
                            title,
                            class_name: cls,
                            href,
                            bg,
                            color,
                            tag: el.tagName
                        };
                    })
                    .filter(x => {
                        const t = x.text.toLowerCase();
                        return (
                            /^\\d+$/.test(x.text) ||
                            t === "next" ||
                            t.includes("next") ||
                            x.aria.toLowerCase().includes("next") ||
                            x.title.toLowerCase().includes("next") ||
                            x.text === ">" ||
                            x.text === "›" ||
                            x.text === "»"
                        );
                    });

                const numbers = items
                    .filter(x => /^\\d+$/.test(x.text))
                    .map(x => {
                        const activeByClass = /active|current|selected|on/i.test(x.class_name);
                        const activeByColor =
                            x.bg.includes("0, 0, 0") ||
                            x.bg.includes("17, 24, 39") ||
                            x.bg.includes("31, 41, 55");

                        return {
                            number: parseInt(x.text, 10),
                            text: x.text,
                            class_name: x.class_name,
                            href: x.href,
                            bg: x.bg,
                            active: activeByClass || activeByColor
                        };
                    });

                let current = null;

                const activeNumber = numbers.find(x => x.active);
                if (activeNumber) {
                    current = activeNumber.number;
                } else if (numbers.length) {
                    current = Math.min(...numbers.map(x => x.number));
                }

                const maxVisible = numbers.length ? Math.max(...numbers.map(x => x.number)) : null;

                const hasNextButton = items.some(x => {
                    const t = x.text.toLowerCase();
                    return (
                        t === "next" ||
                        t.includes("next") ||
                        x.aria.toLowerCase().includes("next") ||
                        x.title.toLowerCase().includes("next") ||
                        x.text === ">" ||
                        x.text === "›" ||
                        x.text === "»"
                    );
                });

                return {
                    current_page: current,
                    max_visible_page: maxVisible,
                    visible_numbers: numbers.map(x => x.number),
                    has_next_button: hasNextButton,
                    items_count: items.length
                };
            }
            """
        )
    except Exception:
        return {
            "current_page": None,
            "max_visible_page": None,
            "visible_numbers": [],
            "has_next_button": False,
            "items_count": 0,
        }


def click_page_number(page, page_number: int) -> bool:
    try:
        clicked = page.evaluate(
            """
            (targetPage) => {
                const elements = Array.from(document.querySelectorAll("a, button, [role='button'], li, span"));

                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return (
                        rect.width > 8 &&
                        rect.height > 8 &&
                        style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        style.opacity !== "0"
                    );
                };

                const candidates = elements.filter((el) => {
                    const text = (el.innerText || el.textContent || "").trim();
                    return visible(el) && text === String(targetPage);
                });

                if (!candidates.length) return false;

                const el = candidates[candidates.length - 1];
                el.scrollIntoView({ block: "center", inline: "center" });
                el.click();
                return true;
            }
            """,
            page_number,
        )

        if clicked:
            print(f"Clicked page number: {page_number}")
            page.wait_for_timeout(random.randint(3500, 6500))
            pause_for_security(page)
            return True

        return False

    except Exception as e:
        print(f"Click page number failed: {e}")
        return False


def click_next_arrow(page) -> bool:
    try:
        clicked = page.evaluate(
            """
            () => {
                const elements = Array.from(document.querySelectorAll("a, button, [role='button'], li, span"));

                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return (
                        rect.width > 8 &&
                        rect.height > 8 &&
                        style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        style.opacity !== "0"
                    );
                };

                const candidates = elements.filter((el) => {
                    const text = (el.innerText || el.textContent || "").trim().toLowerCase();
                    const aria = (el.getAttribute("aria-label") || "").toLowerCase();
                    const title = (el.getAttribute("title") || "").toLowerCase();
                    const cls = (el.className || "").toString().toLowerCase();

                    return visible(el) && (
                        text === "next" ||
                        text.includes("next") ||
                        aria.includes("next") ||
                        title.includes("next") ||
                        cls.includes("next") ||
                        text === ">" ||
                        text === "›" ||
                        text === "»"
                    );
                });

                if (!candidates.length) return false;

                const el = candidates[candidates.length - 1];
                el.scrollIntoView({ block: "center", inline: "center" });
                el.click();
                return true;
            }
            """
        )

        if clicked:
            print("Clicked next arrow.")
            page.wait_for_timeout(random.randint(3500, 6500))
            pause_for_security(page)
            return True

        return False

    except Exception as e:
        print(f"Click next arrow failed: {e}")
        return False


def go_to_next_pagination_page(page, current_page_num: int, keyword: str, mode: str) -> tuple[bool, int]:
    """
    Goes from 1 → 2 → 3 → etc.

    Priority:
    1. Click exact next page number if visible.
    2. Click next arrow if visible.
    3. Optional URL fallback.
    4. Stop if no next page is found.
    """
    next_page_num = current_page_num + 1
    status = get_pagination_status(page)

    print()
    print("Pagination status:")
    print(f"Current page guess: {status.get('current_page')}")
    print(f"Visible numbers: {status.get('visible_numbers')}")
    print(f"Has next arrow: {status.get('has_next_button')}")

    if mode in {"click", "auto"}:
        if next_page_num in status.get("visible_numbers", []):
            if click_page_number(page, next_page_num):
                return True, next_page_num

        if status.get("has_next_button"):
            if click_next_arrow(page):
                return True, next_page_num

    if mode in {"url", "auto"}:
        next_url = make_search_url(keyword, next_page_num)
        print(f"Fallback opening page URL: {next_url}")

        try:
            page.goto(next_url, wait_until="commit", timeout=60000)
            page.wait_for_timeout(random.randint(3500, 6500))
            pause_for_security(page)

            body_text = page.locator("body").inner_text(timeout=5000).lower()

            if "no result" in body_text or "no products" in body_text:
                print("No results found on fallback URL.")
                return False, current_page_num

            return True, next_page_num

        except Exception as e:
            print(f"URL fallback failed: {e}")
            return False, current_page_num

    print("No next page found. Keyword finished.")
    return False, current_page_num


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

            for (const anchor of anchors) {
                let node = anchor;

                for (let depth = 0; depth < 10; depth++) {
                    if (!node) break;

                    const text = (node.innerText || "").trim();
                    const img = node.querySelector("img");

                    const hasImage = !!img && !!(img.currentSrc || img.src);
                    const hasPrice = /(?:US\\s*)?\\$\\s?\\d+(?:\\.\\d+)?/.test(text);
                    const hasUsefulText = text.length >= 15;

                    if (hasImage && hasPrice && hasUsefulText) {
                        const imageUrl = img.currentSrc || img.src || "";
                        const imageAlt = img.alt || "";
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

            return results.slice(0, 900);
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


# ============================================================
# SCROLL + CAPTURE
# ============================================================

def scroll_to_bottom_and_capture(
    page,
    keyword: str,
    page_num: int,
    seen_keys: set[str],
    max_scroll_steps: int,
    stable_rounds_needed: int,
) -> list[dict]:
    collected = []
    stable_rounds = 0
    last_scroll_height = 0
    last_collected_count = 0

    print("Scrolling and capturing until bottom...")

    for step in range(1, max_scroll_steps + 1):
        pause_for_security(page)

        products = extract_cards_from_page(page, keyword, page_num)

        new_this_step = 0

        for product in products:
            key = make_dedupe_key(product)

            if key not in seen_keys:
                seen_keys.add(key)
                collected.append(product)
                new_this_step += 1

        info = get_scroll_info(page)
        current_height = int(info.get("scroll_height", 0))
        current_y = int(info.get("scroll_y", 0))
        bottom = is_near_bottom(page)

        if current_height == last_scroll_height and len(collected) == last_collected_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        last_scroll_height = current_height
        last_collected_count = len(collected)

        print(
            f"Scroll {step}/{max_scroll_steps} | "
            f"y={current_y} | height={current_height} | "
            f"new step={new_this_step} | "
            f"new page={len(collected)} | "
            f"bottom={bottom} | stable={stable_rounds}/{stable_rounds_needed}"
        )

        if bottom and stable_rounds >= stable_rounds_needed:
            print("Reached bottom of current page.")
            break

        scroll_step(page)

    return collected


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords-file", default=str(KEYWORDS_PATH))
    parser.add_argument("--pages-per-keyword", type=int, default=0, help="0 means continue until no next page.")
    parser.add_argument("--max-products", type=int, default=5000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--navigation", choices=["auto", "url", "click"], default="auto")
    parser.add_argument("--max-scroll-steps", type=int, default=35)
    parser.add_argument("--stable-rounds", type=int, default=3)
    parser.add_argument("--delay-min", type=float, default=4)
    parser.add_argument("--delay-max", type=float, default=9)
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
    seen_keys = load_seen_keys(OUTPUT_PATH)
    existing_total = len(load_existing(OUTPUT_PATH))

    print()
    print("=" * 72)
    print("DHGATE PAGINATION CRAWLER")
    print("Scrapes page 1, scrolls to bottom, clicks page 2, then page 3, etc.")
    print("If pages-per-keyword is 0, it continues until there is no next page.")
    print("Does not bypass security checks. It pauses for manual verification.")
    print(f"Keywords: {len(keywords)}")
    print(f"Pages per keyword: {args.pages_per_keyword if args.pages_per_keyword else 'UNTIL NO NEXT PAGE'}")
    print(f"Max products: {args.max_products}")
    print(f"Existing products: {existing_total}")
    print(f"Output: {OUTPUT_PATH}")
    print("=" * 72)
    print()

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

        print("Chrome opened.")
        print("Log in or complete checks if needed.")
        print("Then return here.")
        input("Press ENTER to begin DHgate crawl... ")

        try:
            for keyword in keywords:
                if keyword in completed_keywords:
                    print(f"Skipping completed keyword: {keyword}")
                    continue

                print()
                print("#" * 72)
                print(f"STARTING KEYWORD: {keyword}")
                print("#" * 72)

                page_num = 1
                start_url = make_search_url(keyword, page_num)

                print(f"Opening first page: {start_url}")
                page.goto(start_url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(random.randint(3500, 6500))
                pause_for_security(page)

                while True:
                    current_total = len(load_existing(OUTPUT_PATH))

                    if current_total >= args.max_products:
                        print("Max product limit reached.")
                        return

                    if args.pages_per_keyword > 0 and page_num > args.pages_per_keyword:
                        print(f"Reached page limit for keyword: {keyword}")
                        break

                    print()
                    print("=" * 72)
                    print(f"Keyword: {keyword}")
                    print(f"Current Page: {page_num}")
                    print(f"Total saved before page: {current_total}")
                    print("=" * 72)

                    new_products = scroll_to_bottom_and_capture(
                        page=page,
                        keyword=keyword,
                        page_num=page_num,
                        seen_keys=seen_keys,
                        max_scroll_steps=args.max_scroll_steps,
                        stable_rounds_needed=args.stable_rounds,
                    )

                    added, total = append_and_save(OUTPUT_PATH, new_products)

                    state["last_keyword"] = keyword
                    state["last_page"] = page_num
                    state["total_saved"] = total
                    save_state(state)

                    print()
                    print(f"Page complete: {keyword} | page {page_num}")
                    print(f"New collected this page: {len(new_products)}")
                    print(f"New saved after dedupe: {added}")
                    print(f"Total saved: {total}")

                    if total >= args.max_products:
                        print("Max product limit reached.")
                        return

                    delay = random.uniform(args.delay_min, args.delay_max)
                    print(f"Waiting {delay:.1f} seconds before next page...")
                    time.sleep(delay)

                    moved, new_page_num = go_to_next_pagination_page(
                        page=page,
                        current_page_num=page_num,
                        keyword=keyword,
                        mode=args.navigation,
                    )

                    if not moved:
                        print(f"No more pages for keyword: {keyword}")
                        break

                    page_num = new_page_num

                completed_keywords.add(keyword)
                state["completed_keywords"] = sorted(completed_keywords)
                save_state(state)

        except KeyboardInterrupt:
            print("Stopped manually. Saving state...")
            save_state(state)

        finally:
            browser.close()

    print()
    print("=" * 72)
    print("DHGATE CRAWL COMPLETE")
    print(f"Saved to: {OUTPUT_PATH}")
    print("=" * 72)


if __name__ == "__main__":
    main()
