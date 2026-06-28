from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from shein_smart_capture import (
    USER_DATA_DIR,
    extract_visible_products,
    load_existing,
    make_key,
    now_text,
    pause_for_security,
    save_products,
)


DEFAULT_URL = "https://us.shein.com/Women-Clothing-c-2030.html?ici=us_tab03navbar03menu01dir01&src_module=topcat&src_identifier=fc%3DWomen%20Clothing%60sc%3DWomen%20Clothing%60tc%3DShop%20by%20Category%60oc%3DView%20All%60ps%3Dtab03navbar03menu01dir01%60jc%3Dreal_2030&adp=&src_tab_page_id=page_home1782657088706&categoryJump=common:375681:shein:us_en:ios_!_0"

OUTPUT_PATH = Path("data/shein_smart_capture.csv")


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


def near_bottom(page, buffer_px: int = 900) -> bool:
    info = get_scroll_info(page)

    return (
        float(info.get("scroll_y", 0))
        + float(info.get("inner_height", 0))
        + buffer_px
        >= float(info.get("scroll_height", 0))
    )


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


def click_next_page(page) -> bool:
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

                const disabled = (el) => {
                    const aria = (el.getAttribute("aria-disabled") || "").toLowerCase();
                    const cls = (el.className || "").toString().toLowerCase();
                    return aria === "true" || cls.includes("disabled");
                };

                const candidates = elements.filter((el) => {
                    const text = (el.innerText || el.textContent || "").trim().toLowerCase();
                    const aria = (el.getAttribute("aria-label") || "").toLowerCase();
                    const title = (el.getAttribute("title") || "").toLowerCase();
                    const cls = (el.className || "").toString().toLowerCase();

                    return visible(el) && !disabled(el) && (
                        text === "next" ||
                        text === ">" ||
                        text === "›" ||
                        text === "»" ||
                        aria.includes("next") ||
                        title.includes("next") ||
                        cls.includes("next")
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
            print("Clicked next page.")
            page.wait_for_timeout(3500)
            close_popups(page)
            pause_for_security(page)
            return True

        return False

    except Exception:
        return False


def page_fingerprint(products: list[dict]) -> str:
    keys = sorted([make_key(product) for product in products[:25]])
    return "|".join(keys)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--section", default="Women's Clothing")
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--max-scrolls", type=int, default=250)
    parser.add_argument("--scroll-wait-ms", type=int, default=650)
    parser.add_argument("--jump-px", type=int, default=1500)
    parser.add_argument("--stable-rounds", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=0, help="0 means continue until no next page.")
    parser.add_argument("--no-next-pages", action="store_true")
    args = parser.parse_args()

    output_path = Path(args.output)

    existing = load_existing(output_path)
    seen_keys = set()

    if not existing.empty:
        for row in existing.to_dict("records"):
            seen_keys.add(make_key(row))

    run_products = []
    last_page_fingerprint = ""
    repeated_pages = 0
    page_num = 1

    print()
    print("=" * 72)
    print("SHEIN DIRECT PAGE CAPTURE")
    print("Opening your exact SHEIN Women’s Clothing URL.")
    print("It will scroll, capture products, remove duplicates, and save to SHEIN data.")
    print("No security bypassing. Complete checks manually if they appear.")
    print(f"Output: {output_path}")
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
        page.goto(args.url, wait_until="commit", timeout=60000)
        page.wait_for_timeout(5000)

        close_popups(page)
        pause_for_security(page)

        print("Page opened.")
        print("If product cards are visible, press ENTER.")
        print("If SHEIN asks for verification, complete it first.")
        input("Press ENTER to start scraping this page... ")

        try:
            while True:
                print()
                print("=" * 72)
                print(f"CAPTURING PAGE {page_num}")
                print("=" * 72)

                stable_count = 0
                last_total = len(seen_keys)
                last_height = 0
                page_products = []

                for scroll_num in range(1, args.max_scrolls + 1):
                    pause_for_security(page)

                    visible_products = extract_visible_products(page, args.section)

                    new_this_scroll = 0

                    for product in visible_products:
                        key = make_key(product)

                        if key not in seen_keys:
                            seen_keys.add(key)
                            run_products.append(product)
                            page_products.append(product)
                            new_this_scroll += 1

                    before, added, total = save_products(output_path, run_products)

                    info = get_scroll_info(page)
                    height = int(info.get("scroll_height", 0))
                    y = int(info.get("scroll_y", 0))
                    bottom = near_bottom(page)

                    if total == last_total and height == last_height and bottom:
                        stable_count += 1
                    else:
                        stable_count = 0

                    last_total = total
                    last_height = height

                    print(
                        f"[{now_text()}] Page {page_num} | "
                        f"Scroll {scroll_num}/{args.max_scrolls} | "
                        f"visible={len(visible_products)} | "
                        f"new scroll={new_this_scroll} | "
                        f"page new={len(page_products)} | "
                        f"total saved={total} | "
                        f"bottom={bottom} | "
                        f"stable={stable_count}/{args.stable_rounds}"
                    )

                    if bottom and stable_count >= args.stable_rounds:
                        print("Reached bottom of current page.")
                        break

                    page.evaluate("(jump) => window.scrollBy(0, jump)", args.jump_px)
                    page.wait_for_timeout(args.scroll_wait_ms)

                current_fingerprint = page_fingerprint(page_products)

                if current_fingerprint and current_fingerprint == last_page_fingerprint:
                    repeated_pages += 1
                    print(f"Repeated page detected: {repeated_pages}/2")
                else:
                    repeated_pages = 0

                last_page_fingerprint = current_fingerprint

                save_products(output_path, run_products)

                if repeated_pages >= 2:
                    print("Stopping because pages are repeating.")
                    break

                if args.no_next_pages:
                    print("Next pages disabled.")
                    break

                if args.max_pages > 0 and page_num >= args.max_pages:
                    print("Reached max page limit.")
                    break

                moved = click_next_page(page)

                if not moved:
                    print("No next page found. Capture complete.")
                    break

                page_num += 1
                time.sleep(1)

        except KeyboardInterrupt:
            print("Stopped manually. Saving final results...")

        finally:
            save_products(output_path, run_products)
            browser.close()

    print()
    print("=" * 72)
    print("SHEIN DIRECT PAGE CAPTURE COMPLETE")
    print(f"Saved to: {output_path}")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
