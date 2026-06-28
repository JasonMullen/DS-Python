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


DEFAULT_OUTPUT = Path("data/shein_smart_capture.csv")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", default="Women's Clothing")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--seconds", type=int, default=0, help="0 means run until you press Ctrl+C.")
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
    print("SHEIN MANUAL CAPTURE MODE")
    print("Use this when SHEIN will not allow automated navigation.")
    print("You navigate manually. The script captures whatever products are visible.")
    print("No security bypassing.")
    print(f"Section label: {args.section}")
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
        page.goto("about:blank")

        print("In the Chrome window:")
        print("1. Manually go to SHEIN.")
        print("2. Go to Women's Clothing or paste your SHEIN URL.")
        print("3. Wait until product cards are visible.")
        print("4. Return here and press ENTER.")
        input("Press ENTER when product cards are visible... ")

        start_time = time.time()
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

                if args.seconds > 0 and time.time() - start_time >= args.seconds:
                    print("Time limit reached.")
                    break

                time.sleep(args.interval)

        except KeyboardInterrupt:
            print("Stopped manually. Saving final results...")

        finally:
            save_products(output_path, run_products)
            browser.close()

    print()
    print("=" * 72)
    print("SHEIN MANUAL CAPTURE COMPLETE")
    print(f"Saved to: {output_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()
