from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from shein_smart_capture import (
    extract_visible_products,
    load_existing,
    make_key,
    now_text,
    pause_for_security,
    save_products,
)


DEFAULT_OUTPUT = Path("data/shein_smart_capture.csv")
CDP_URL = "http://127.0.0.1:9222"


def get_all_pages(browser):
    pages = []

    for context in browser.contexts:
        for page in context.pages:
            pages.append(page)

    return pages


def page_title_safe(page) -> str:
    try:
        return page.title()
    except Exception:
        return ""


def choose_page(pages):
    print()
    print("=" * 72)
    print("OPEN CHROME TABS")
    print("=" * 72)

    for i, page in enumerate(pages, start=1):
        title = page_title_safe(page)
        url = page.url

        print(f"[{i}] {title}")
        print(f"    {url}")
        print()

    while True:
        choice = input("Choose the SHEIN tab number to scrape: ").strip()

        if choice.isdigit():
            index = int(choice) - 1

            if 0 <= index < len(pages):
                return pages[index]

        print("Invalid choice. Try again.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", default="Women's Clothing")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--seconds", type=int, default=0, help="0 means run until Ctrl+C.")
    parser.add_argument("--interval", type=int, default=3)
    parser.add_argument("--scroll", action="store_true")
    parser.add_argument("--jump-px", type=int, default=1200)
    args = parser.parse_args()

    output_path = Path(args.output)

    existing = load_existing(output_path)
    seen_keys = set()

    if not existing.empty:
        for row in existing.to_dict("records"):
            seen_keys.add(make_key(row))

    run_products = []

    print()
    print("=" * 72)
    print("SHEIN EXISTING CHROME TAB CAPTURE")
    print("This connects to your already-open attachable Chrome window.")
    print("You choose the SHEIN tab. The scraper captures visible product cards.")
    print("No automatic navigation. No security bypassing.")
    print(f"Output: {output_path}")
    print("=" * 72)
    print()

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception:
            print()
            print("Could not connect to Chrome.")
            print("Make sure Chrome was opened with this first:")
            print()
            print('Start-Process "chrome.exe" -ArgumentList \'--remote-debugging-port=9222 --user-data-dir="C:\\Users\\jason\\OneDrive\\Attachments\\Desktop\\Drop Shipping Python\\dropship_trend_finder\\.browser\\attachable_chrome"\'')
            return

        pages = get_all_pages(browser)

        if not pages:
            print("No Chrome tabs found.")
            return

        page = choose_page(pages)

        try:
            page.bring_to_front()
        except Exception:
            pass

        print()
        print("Selected tab:")
        print(page_title_safe(page))
        print(page.url)
        print()

        input("Make sure SHEIN product cards are visible, then press ENTER to start capture... ")

        started = time.time()
        loop = 0

        try:
            while True:
                loop += 1

                pause_for_security(page)

                visible_products = extract_visible_products(page, args.section)

                new_this_loop = 0

                for product in visible_products:
                    key = make_key(product)

                    if key not in seen_keys:
                        seen_keys.add(key)
                        run_products.append(product)
                        new_this_loop += 1

                before, added, total = save_products(output_path, run_products)

                print(
                    f"[{now_text()}] Loop {loop} | "
                    f"visible={len(visible_products)} | "
                    f"new this loop={new_this_loop} | "
                    f"new saved={added} | "
                    f"total saved={total}"
                )

                if args.scroll:
                    try:
                        page.evaluate("(jump) => window.scrollBy(0, jump)", args.jump_px)
                    except Exception:
                        pass

                if args.seconds > 0 and time.time() - started >= args.seconds:
                    print("Time limit reached.")
                    break

                time.sleep(args.interval)

        except KeyboardInterrupt:
            print("Stopped manually. Saving final results...")

        finally:
            save_products(output_path, run_products)

    print()
    print("=" * 72)
    print("EXISTING CHROME TAB CAPTURE COMPLETE")
    print(f"Saved to: {output_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()
