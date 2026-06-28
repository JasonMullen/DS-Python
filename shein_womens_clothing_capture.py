from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from shein_smart_capture import (
    START_URL,
    USER_DATA_DIR,
    extract_visible_products,
    now_text,
    pause_for_security,
    save_products,
)


DEFAULT_OUTPUT = Path("data/shein_smart_capture.csv")


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", default="Women's Clothing")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-scrolls", type=int, default=250)
    parser.add_argument("--scroll-wait-ms", type=int, default=700)
    parser.add_argument("--jump-px", type=int, default=1400)
    parser.add_argument("--stable-rounds", type=int, default=5)
    args = parser.parse_args()

    output_path = Path(args.output)

    print()
    print("=" * 72)
    print("SHEIN WOMEN'S CLOTHING SECTION CAPTURE")
    print("This works like Zendrop smart capture.")
    print("You browse to the Women's Clothing section manually.")
    print("The script scrolls, captures visible product cards, and removes duplicates.")
    print("No security bypassing.")
    print(f"Section label: {args.section}")
    print(f"Output: {output_path}")
    print("=" * 72)
    print()

    run_products = []
    stable_count = 0
    last_total = 0
    last_height = 0

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
        print("1. Go to SHEIN Women's Clothing.")
        print("2. Make sure product cards are visible.")
        print("3. Return here and press ENTER.")
        input("Press ENTER when the Women's Clothing section is visible... ")

        try:
            for scroll_num in range(1, args.max_scrolls + 1):
                pause_for_security(page)

                products = extract_visible_products(page, args.section)
                run_products.extend(products)

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
                    f"[{now_text()}] Scroll {scroll_num}/{args.max_scrolls} | "
                    f"visible captured={len(products)} | "
                    f"new added={added} | "
                    f"total saved={total} | "
                    f"y={y} | bottom={bottom} | "
                    f"stable={stable_count}/{args.stable_rounds}"
                )

                if bottom and stable_count >= args.stable_rounds:
                    print()
                    print("Reached the bottom and no new products appeared.")
                    break

                page.evaluate("(jump) => window.scrollBy(0, jump)", args.jump_px)
                page.wait_for_timeout(args.scroll_wait_ms)

        except KeyboardInterrupt:
            print("Stopped manually. Saving final results...")

        finally:
            save_products(output_path, run_products)
            browser.close()

    print()
    print("=" * 72)
    print("SHEIN WOMEN'S CLOTHING CAPTURE COMPLETE")
    print(f"Saved to: {output_path}")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
