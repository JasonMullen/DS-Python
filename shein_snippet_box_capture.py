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
from PIL import Image, ImageTk
from playwright.sync_api import sync_playwright
import tkinter as tk


DEFAULT_URL = "https://us.shein.com/Women-Clothing-c-2030.html?ici=us_tab03navbar03menu01dir01&src_module=topcat&src_identifier=fc%3DWomen%20Clothing%60sc%3DWomen%20Clothing%60tc%3DShop%20by%20Category%60oc%3DView%20All%60ps%3Dtab03navbar03menu01dir01%60jc%3Dreal_2030&adp=&src_tab_page_id=page_home1782657088706&categoryJump=common:375681:shein:us_en:ios_!_0"

OUTPUT_PATH = Path("data/shein_smart_capture.csv")
USER_DATA_DIR = ".browser/shein_smart_profile"
TEMP_SCREENSHOT = Path("data/_snippet_page_screenshot.png")


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


def close_popups(page):
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    selectors = [
        "button[aria-label='Close']",
        "[aria-label='Close']",
        "[aria-label='close']",
        "button:has-text('No thanks')",
        "button:has-text('Not now')",
        "button:has-text('Maybe later')",
        ".sui-dialog-close",
        ".icon-close",
        ".j-close",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector)

            if locator.count() > 0:
                locator.first.click(timeout=1000)
                page.wait_for_timeout(500)
        except Exception:
            pass


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
        print("After the normal product page is visible, return here.")
        print("=" * 72)
        input("Press ENTER to continue... ")


def select_region_from_screenshot(image_path: Path) -> tuple[int, int, int, int] | None:
    original = Image.open(image_path)

    root = tk.Tk()
    root.title("Draw a box around the section you want to scrape")

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    max_w = int(screen_w * 0.92)
    max_h = int(screen_h * 0.82)

    scale = min(max_w / original.width, max_h / original.height, 1.0)

    display_w = int(original.width * scale)
    display_h = int(original.height * scale)

    display = original.resize((display_w, display_h))

    tk_img = ImageTk.PhotoImage(display)

    result = {"rect": None}
    start = {"x": 0, "y": 0}
    rect_id = {"id": None}

    instructions = tk.Label(
        root,
        text="Click and drag a box around the product section. Press ESC to cancel.",
        font=("Arial", 12),
        pady=8,
    )
    instructions.pack()

    canvas = tk.Canvas(root, width=display_w, height=display_h, cursor="crosshair")
    canvas.pack()
    canvas.create_image(0, 0, anchor="nw", image=tk_img)

    def on_press(event):
        start["x"] = event.x
        start["y"] = event.y

        if rect_id["id"]:
            canvas.delete(rect_id["id"])

        rect_id["id"] = canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="red",
            width=3,
        )

    def on_drag(event):
        if rect_id["id"]:
            canvas.coords(
                rect_id["id"],
                start["x"],
                start["y"],
                event.x,
                event.y,
            )

    def on_release(event):
        x1 = min(start["x"], event.x)
        y1 = min(start["y"], event.y)
        x2 = max(start["x"], event.x)
        y2 = max(start["y"], event.y)

        if abs(x2 - x1) < 20 or abs(y2 - y1) < 20:
            result["rect"] = None
        else:
            result["rect"] = (
                int(x1 / scale),
                int(y1 / scale),
                int(x2 / scale),
                int(y2 / scale),
            )

        root.destroy()

    def on_escape(event):
        result["rect"] = None
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)

    root.mainloop()

    return result["rect"]


def extract_products_in_region(page, region: tuple[int, int, int, int], section: str) -> list[dict]:
    x1, y1, x2, y2 = region

    raw_cards = page.evaluate(
        """
        (region) => {
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

            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);

                return (
                    rect.width > 5 &&
                    rect.height > 5 &&
                    style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    style.opacity !== "0"
                );
            };

            const intersects = (rect, region) => {
                return !(
                    rect.right < region.x1 ||
                    rect.left > region.x2 ||
                    rect.bottom < region.y1 ||
                    rect.top > region.y2
                );
            };

            for (const anchor of anchors) {
                let node = anchor;

                for (let depth = 0; depth < 9; depth++) {
                    if (!node) break;

                    if (!visible(node)) {
                        node = node.parentElement;
                        continue;
                    }

                    const rect = node.getBoundingClientRect();

                    if (!intersects(rect, region)) {
                        node = node.parentElement;
                        continue;
                    }

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
                                page_url: window.location.href,
                                x: rect.left,
                                y: rect.top,
                                width: rect.width,
                                height: rect.height
                            });
                        }

                        break;
                    }

                    node = node.parentElement;
                }
            }

            return results.slice(0, 1000);
        }
        """,
        {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
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
            "keyword": section,
            "category": section,
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
            "snippet_x": int(raw.get("x", 0)),
            "snippet_y": int(raw.get("y", 0)),
            "snippet_width": int(raw.get("width", 0)),
            "snippet_height": int(raw.get("height", 0)),
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--section", default="Women's Clothing")
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 72)
    print("SHEIN SNIPPET BOX CAPTURE TOOL")
    print("You draw a box around the section. The scraper captures products inside it.")
    print("No automatic navigation. No security bypassing.")
    print(f"Output: {output_path}")
    print("=" * 72)
    print()

    all_new_products = []

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1500, "height": 950},
        )

        page = browser.new_page()

        print("Opening SHEIN page...")
        page.goto(args.url, wait_until="commit", timeout=60000)
        page.wait_for_timeout(5000)

        close_popups(page)
        pause_for_security(page)

        print()
        print("In Chrome:")
        print("1. Make sure the section you want is visible.")
        print("2. Return to PowerShell.")
        print("3. Press ENTER to draw a snippet box.")
        print()

        try:
            while True:
                choice = input("Press ENTER to capture a snippet box, or type q to quit: ").strip().lower()

                if choice == "q":
                    break

                close_popups(page)
                pause_for_security(page)

                TEMP_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(TEMP_SCREENSHOT), full_page=False)

                region = select_region_from_screenshot(TEMP_SCREENSHOT)

                if region is None:
                    print("No region selected.")
                    continue

                print(f"Selected region: {region}")

                products = extract_products_in_region(page, region, args.section)
                all_new_products.extend(products)

                before, added, total = save_products(output_path, all_new_products)

                print()
                print("SNIPPET RESULT")
                print(f"Products detected in box: {len(products)}")
                print(f"New products added: {added}")
                print(f"Total saved: {total}")
                print()

                print("You can now scroll/navigate manually in Chrome and capture another box.")

        except KeyboardInterrupt:
            print("Stopped manually. Saving final results...")

        finally:
            save_products(output_path, all_new_products)
            browser.close()

    print()
    print("=" * 72)
    print("SNIPPET CAPTURE COMPLETE")
    print(f"Saved to: {output_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()
