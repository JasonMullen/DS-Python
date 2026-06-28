from __future__ import annotations

import argparse
import re
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd
from playwright.sync_api import sync_playwright


START_URL = "https://app.zendrop.com/product?page=1"
USER_DATA_DIR = ".browser/zendrop_profile"
VERIFICATION_PATH = Path("output/all_products_verification.csv")
AUTO_RESULTS_PATH = Path("output/auto_verification_results.csv")

WAIT_AFTER_SEARCH_MS = 3500
SAVE_EVERY = 10


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_money(value: Any) -> float:
    if value is None:
        return 0.0

    text = str(value).replace(",", "")
    match = re.search(r"\$?\s?(\d+(?:\.\d+)?)", text)

    return round(float(match.group(1)), 2) if match else 0.0


def normalize_text(text: Any) -> str:
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_similarity(a: str, b: str) -> float:
    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return 0.0

    return SequenceMatcher(None, a, b).ratio()


def token_overlap(a: str, b: str) -> float:
    a_tokens = {x for x in normalize_text(a).split() if len(x) > 2}
    b_tokens = {x for x in normalize_text(b).split() if len(x) > 2}

    if not a_tokens or not b_tokens:
        return 0.0

    return len(a_tokens & b_tokens) / max(len(a_tokens), 1)


def cost_close(board_cost: float, zendrop_cost: float) -> bool:
    if board_cost <= 0 or zendrop_cost <= 0:
        return False

    difference_pct = abs(board_cost - zendrop_cost) / board_cost

    return difference_pct <= 0.15


def product_match_score(
    board_name: str,
    board_cost: float,
    board_image_url: str,
    card: dict,
) -> float:
    card_name = card.get("product_name", "")
    card_cost = clean_money(card.get("product_cost", 0))
    card_image_url = str(card.get("image_url", ""))

    name_score = text_similarity(board_name, card_name) * 70
    overlap_score = token_overlap(board_name, card_name) * 20

    cost_score = 0
    if cost_close(board_cost, card_cost):
        cost_score = 10

    image_score = 0
    if board_image_url and card_image_url:
        board_image_clean = board_image_url.split("?")[0].split("/")[-1]
        card_image_clean = card_image_url.split("?")[0].split("/")[-1]

        if board_image_clean and board_image_clean == card_image_clean:
            image_score = 15

    return round(name_score + overlap_score + cost_score + image_score, 2)


def wait_if_security_check(page):
    try:
        body_text = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        body_text = ""

    current_url = page.url.lower()

    security_signals = [
        "performing security verification",
        "verifies you are not a bot",
        "security service",
        "checking your browser",
        "cloudflare",
    ]

    if any(signal in body_text for signal in security_signals) or "security" in current_url:
        print()
        print("=" * 72)
        print("SECURITY VERIFICATION DETECTED")
        print("Complete the verification manually in the Chrome window.")
        print("After Zendrop products are visible again, return here and press ENTER.")
        print("=" * 72)
        input("Press ENTER after completing verification... ")
        time.sleep(3)


def set_zendrop_search(page, query: str) -> bool:
    try:
        success = page.evaluate(
            """
            (query) => {
                const inputs = Array.from(document.querySelectorAll("input"));

                const visibleInputs = inputs.filter((input) => {
                    const rect = input.getBoundingClientRect();
                    return rect.width > 100 && rect.height > 20;
                });

                const searchInput =
                    visibleInputs.find((input) =>
                        (input.placeholder || "").toLowerCase().includes("search")
                    ) || visibleInputs[0];

                if (!searchInput) return false;

                searchInput.focus();
                searchInput.value = "";

                searchInput.dispatchEvent(new Event("input", { bubbles: true }));
                searchInput.dispatchEvent(new Event("change", { bubbles: true }));

                searchInput.value = query;

                searchInput.dispatchEvent(new Event("input", { bubbles: true }));
                searchInput.dispatchEvent(new Event("change", { bubbles: true }));

                return true;
            }
            """,
            query,
        )

        if success:
            page.keyboard.press("Enter")
            return True

    except Exception as e:
        print(f"Could not search Zendrop: {e}")

    return False


def extract_zendrop_product_cards(page) -> list[dict]:
    try:
        raw_cards = page.evaluate(
            """
            () => {
                const results = [];
                const seen = new Set();

                const buttons = Array.from(
                    document.querySelectorAll("button, [role='button']")
                );

                for (const button of buttons) {
                    const buttonText = (button.innerText || "").trim().toLowerCase();

                    if (!buttonText.includes("add")) continue;

                    let node = button;

                    for (let depth = 0; depth < 10; depth++) {
                        if (!node || !node.parentElement) break;

                        node = node.parentElement;

                        const text = node.innerText || "";
                        const lower = text.toLowerCase();

                        const hasCost = lower.includes("cost");
                        const hasPC = lower.includes("p/c");
                        const hasGrowth = lower.includes("growth");
                        const hasMoney = /\\$\\s?\\d+(?:\\.\\d+)?/.test(text);
                        const hasImage = node.querySelector("img") !== null;

                        if (!(hasCost && hasPC && hasGrowth && hasMoney && hasImage)) {
                            continue;
                        }

                        const img = node.querySelector("img");
                        const anchor = node.querySelector("a[href]") || node.closest("a[href]");
                        const key = text.replace(/\\s+/g, " ").trim();

                        if (seen.has(key)) break;
                        seen.add(key);

                        results.push({
                            text: text,
                            image_alt: img ? img.alt || "" : "",
                            image_src: img ? img.src || "" : "",
                            href: anchor ? anchor.href || "" : "",
                            url: window.location.href
                        });

                        break;
                    }
                }

                return results;
            }
            """
        )

    except Exception:
        return []

    cards = []

    for card in raw_cards:
        text = str(card.get("text", "")).strip()
        image_url = str(card.get("image_src", "")).strip()
        href = str(card.get("href", "")).strip()
        page_url = str(card.get("url", page.url)).strip()

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        money_values = re.findall(r"\$\s?\d+(?:\.\d+)?", text)
        ratio_values = re.findall(r"(\d+(?:\.\d+)?)\s*x", text.lower())
        growth_values = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", text)

        if not lines or not money_values:
            continue

        store_name = lines[0]
        product_cost = clean_money(money_values[0])
        p_c_ratio = float(ratio_values[0]) if ratio_values else 0.0
        growth_pct = float(growth_values[0]) if growth_values else 0.0

        stop_index = None
        for i, line in enumerate(lines):
            if line.lower() in ["cost", "p/c", "growth"]:
                stop_index = i
                break

        name_lines = lines[1:stop_index] if stop_index else lines[1:3]

        product_name = " ".join(
            line for line in name_lines
            if "$" not in line
            and line.lower() not in ["cost", "p/c", "growth", "+ add", "add"]
        ).strip()

        if len(product_name) < 4:
            continue

        cards.append(
            {
                "product_name": product_name,
                "store_name": store_name,
                "product_cost": product_cost,
                "p_c_ratio": p_c_ratio,
                "growth_pct": growth_pct,
                "image_url": image_url,
                "exact_product_url": href if href else page_url,
                "visible_page_url": page_url,
            }
        )

    return cards


def get_search_terms(row) -> list[str]:
    terms = []

    for col in ["zendrop_search_1", "zendrop_search_2", "zendrop_search_3", "product_name"]:
        value = str(row.get(col, "")).strip()

        if value and value.lower() not in [term.lower() for term in terms]:
            terms.append(value)

    return terms


def verify_one_product(page, row) -> dict:
    board_name = str(row.get("product_name", "")).strip()
    board_cost = clean_money(row.get("product_cost", 0))
    board_image_url = str(row.get("image_url", "")).strip()

    best_card = None
    best_score = 0
    best_search = ""

    search_terms = get_search_terms(row)

    for search_term in search_terms:
        print(f"Searching Zendrop for: {search_term}")

        searched = set_zendrop_search(page, search_term)

        if not searched:
            continue

        page.wait_for_timeout(WAIT_AFTER_SEARCH_MS)
        wait_if_security_check(page)

        cards = extract_zendrop_product_cards(page)

        print(f"Cards found: {len(cards)}")

        for card in cards:
            score = product_match_score(
                board_name=board_name,
                board_cost=board_cost,
                board_image_url=board_image_url,
                card=card,
            )

            if score > best_score:
                best_score = score
                best_card = card
                best_search = search_term

        if best_score >= 85:
            break

    if best_card is None:
        return {
            "auto_check_status": "NO MATCH",
            "auto_match_score": 0,
            "auto_search_used": " | ".join(search_terms),
            "auto_matched_name": "",
            "auto_matched_cost": "",
            "auto_matched_image_url": "",
            "auto_checked_at": now_text(),
            "verification_status": "NO MATCH",
            "exact_match_found": "NO",
            "exact_product_url": "",
            "verification_notes": "Auto-check could not find a matching Zendrop card.",
        }

    matched_name = best_card.get("product_name", "")
    matched_cost = clean_money(best_card.get("product_cost", 0))

    if best_score >= 85:
        status = "VERIFIED"
        exact_match = "YES"
        note = "Auto-check found a strong live Zendrop match."
    elif best_score >= 65:
        status = "NEEDS CHECK"
        exact_match = "MAYBE"
        note = "Auto-check found a possible match. Manually confirm before selling."
    else:
        status = "NO MATCH"
        exact_match = "NO"
        note = "Auto-check found weak matches only."

    return {
        "auto_check_status": status,
        "auto_match_score": best_score,
        "auto_search_used": best_search,
        "auto_matched_name": matched_name,
        "auto_matched_cost": matched_cost,
        "auto_matched_image_url": best_card.get("image_url", ""),
        "auto_checked_at": now_text(),
        "verification_status": status,
        "exact_match_found": exact_match,
        "exact_product_url": best_card.get("exact_product_url", ""),
        "real_product_cost": matched_cost if matched_cost > 0 else "",
        "verification_notes": note,
    }


def save_progress(df: pd.DataFrame):
    df.to_csv(VERIFICATION_PATH, index=False)
    df.to_csv(AUTO_RESULTS_PATH, index=False)
    print(f"Saved progress to {VERIFICATION_PATH}")
    print(f"Saved auto results to {AUTO_RESULTS_PATH}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Limit number of products to check. 0 means all.")
    parser.add_argument("--start", type=int, default=0, help="Start row index.")
    parser.add_argument("--include-verified", action="store_true", help="Re-check products already marked VERIFIED.")
    args = parser.parse_args()

    if not VERIFICATION_PATH.exists():
        raise FileNotFoundError(
            "Missing output/all_products_verification.csv. Run make_full_verification_queue.py first."
        )

    df = pd.read_csv(VERIFICATION_PATH).fillna("")

    needed_cols = [
        "auto_check_status",
        "auto_match_score",
        "auto_search_used",
        "auto_matched_name",
        "auto_matched_cost",
        "auto_matched_image_url",
        "auto_checked_at",
    ]

    for col in needed_cols:
        if col not in df.columns:
            df[col] = ""

    for col in [
        "verification_status",
        "exact_match_found",
        "exact_product_url",
        "real_product_cost",
        "verification_notes",
    ]:
        if col not in df.columns:
            df[col] = ""

    candidate_indexes = list(range(args.start, len(df)))

    if not args.include_verified and "verification_status" in df.columns:
        candidate_indexes = [
            idx for idx in candidate_indexes
            if str(df.loc[idx, "verification_status"]).upper() != "VERIFIED"
        ]

    if args.limit and args.limit > 0:
        candidate_indexes = candidate_indexes[: args.limit]

    print()
    print("=" * 72)
    print("ZENDROP AUTO PRODUCT VERIFIER")
    print(f"Total products in verification board: {len(df)}")
    print(f"Products scheduled to check: {len(candidate_indexes)}")
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
        page.goto(START_URL, wait_until="commit")

        print("Log into Zendrop if needed.")
        print("Complete verification if it appears.")
        print("Once the Find Products page is visible, return here.")
        input("Press ENTER to begin auto-checking products... ")

        wait_if_security_check(page)

        checked_count = 0

        try:
            for idx in candidate_indexes:
                product_name = str(df.loc[idx, "product_name"])

                print()
                print("=" * 72)
                print(f"Checking row {idx + 1}/{len(df)}")
                print(f"Product: {product_name}")
                print("=" * 72)

                result = verify_one_product(page, df.loc[idx])

                for key, value in result.items():
                    if key not in df.columns:
                        df[key] = ""
                    df.loc[idx, key] = value

                checked_count += 1

                print(f"Result: {result.get('auto_check_status')}")
                print(f"Match score: {result.get('auto_match_score')}")
                print(f"Matched name: {result.get('auto_matched_name')}")
                print(f"Matched cost: {result.get('auto_matched_cost')}")

                if checked_count % SAVE_EVERY == 0:
                    save_progress(df)

        except KeyboardInterrupt:
            print()
            print("Stopped by user. Saving progress...")

        finally:
            save_progress(df)
            browser.close()

    print()
    print("Auto-verification complete.")
    print(f"Checked this run: {checked_count}")


if __name__ == "__main__":
    main()
