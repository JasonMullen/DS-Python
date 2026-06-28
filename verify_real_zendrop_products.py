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
RESULTS_PATH = Path("output/live_zendrop_verification_results.csv")

WAIT_AFTER_SEARCH_MS = 3500
SAVE_EVERY = 10


# ============================================================
# BASIC HELPERS
# ============================================================

def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_money(value: Any) -> float:
    if value is None:
        return 0.0

    text = str(value).replace(",", "")
    match = re.search(r"\$?\s?(\d+(?:\.\d+)?)", text)

    return round(float(match.group(1)), 2) if match else 0.0


def clean_float(value: Any) -> float:
    if value is None:
        return 0.0

    match = re.search(r"([+-]?\d+(?:\.\d+)?)", str(value))

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


def image_filename(url: Any) -> str:
    url = str(url).strip().split("?")[0]
    return url.split("/")[-1].lower()


def percent_difference(old: float, new: float) -> float:
    if old <= 0 or new <= 0:
        return 999.0

    return round(abs(old - new) / old * 100, 2)


def close_enough(old: float, new: float, tolerance_pct: float = 15.0) -> bool:
    if old <= 0 or new <= 0:
        return False

    return percent_difference(old, new) <= tolerance_pct


# ============================================================
# ZENDROP SECURITY PAUSE
# ============================================================

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


# ============================================================
# SEARCH TERMS
# ============================================================

STOP_WORDS = {
    "for", "with", "and", "the", "a", "an", "of", "to", "in", "on",
    "new", "hot", "best", "fashion", "trend", "premium", "portable",
    "comfortable", "adjustable", "creative", "stylish", "oversized",
    "men", "mens", "women", "womens", "unisex",
}


def make_search_terms(product_name: str) -> list[str]:
    cleaned = normalize_text(product_name)

    words = [
        word for word in cleaned.split()
        if len(word) > 2 and word not in STOP_WORDS
    ]

    terms = []

    if len(words) >= 5:
        terms.append(" ".join(words[:5]))

    if len(words) >= 3:
        terms.append(" ".join(words[:3]))

    if len(words) >= 4:
        terms.append(" ".join(words[-4:]))

    if words:
        terms.append(" ".join(words))

    terms.append(product_name)

    unique_terms = []
    for term in terms:
        term = str(term).strip()
        if term and term.lower() not in [x.lower() for x in unique_terms]:
            unique_terms.append(term)

    return unique_terms[:4]


def get_search_terms(row) -> list[str]:
    terms = []

    for col in ["zendrop_search_1", "zendrop_search_2", "zendrop_search_3"]:
        value = str(row.get(col, "")).strip()
        if value:
            terms.append(value)

    product_name = str(row.get("product_name", "")).strip()

    for term in make_search_terms(product_name):
        terms.append(term)

    unique = []
    for term in terms:
        if term and term.lower() not in [x.lower() for x in unique]:
            unique.append(term)

    return unique[:5]


# ============================================================
# ZENDROP SEARCH
# ============================================================

def open_find_products(page):
    page.goto(START_URL, wait_until="commit")
    page.wait_for_timeout(3000)
    wait_if_security_check(page)


def search_zendrop(page, query: str) -> bool:
    """
    Safely search Zendrop using the visible Search Products input.
    Avoids hidden inputs that cause Playwright click timeouts.
    """
    try:
        if page.is_closed():
            print("Search stopped: page is closed.")
            return False

        success = page.evaluate(
            """
            (query) => {
                const inputs = Array.from(document.querySelectorAll("input"));

                const visibleInputs = inputs.filter((input) => {
                    const rect = input.getBoundingClientRect();
                    const style = window.getComputedStyle(input);

                    return (
                        rect.width > 120 &&
                        rect.height > 20 &&
                        rect.top >= 0 &&
                        rect.left >= 0 &&
                        style.display !== "none" &&
                        style.visibility !== "hidden" &&
                        style.opacity !== "0"
                    );
                });

                let searchInput =
                    visibleInputs.find((input) =>
                        (input.placeholder || "").toLowerCase().includes("search")
                    ) || visibleInputs[0];

                if (!searchInput) {
                    return false;
                }

                searchInput.scrollIntoView({ block: "center", inline: "center" });
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

        if not success:
            print(f"No visible search input found for: {query}")
            return False

        page.keyboard.press("Enter")
        page.wait_for_timeout(WAIT_AFTER_SEARCH_MS)
        wait_if_security_check(page)

        return True

    except Exception as e:
        print(f"Search failed for '{query}': {e}")
        return False


# ============================================================
# EXTRACT LIVE ZENDROP CARDS
# ============================================================

def extract_live_cards(page) -> list[dict]:
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
                        const hasRatio = /\\d+(?:\\.\\d+)?x/.test(lower);
                        const hasImage = node.querySelector("img") !== null;

                        if (!(hasCost && hasPC && hasGrowth && hasMoney && hasRatio && hasImage)) {
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
                            page_url: window.location.href
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
        page_url = str(card.get("page_url", page.url)).strip()

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        money_values = re.findall(r"\$\s?\d+(?:\.\d+)?", text)
        ratio_values = re.findall(r"(\d+(?:\.\d+)?)\s*x", text.lower())
        growth_values = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", text)

        if not lines or not money_values:
            continue

        store_name = lines[0]
        product_cost = clean_money(money_values[0])
        p_c_ratio = clean_float(ratio_values[0]) if ratio_values else 0.0
        growth_pct = clean_float(growth_values[0]) if growth_values else 0.0

        stop_index = None
        for i, line in enumerate(lines):
            if line.lower() in ["cost", "p/c", "growth"]:
                stop_index = i
                break

        if stop_index:
            name_lines = lines[1:stop_index]
        else:
            name_lines = lines[1:3]

        product_name = " ".join(
            line for line in name_lines
            if "$" not in line
            and line.lower() not in ["cost", "p/c", "growth", "+ add", "add"]
        ).strip()

        if len(product_name) < 4:
            continue

        cards.append(
            {
                "live_product_name": product_name,
                "live_store_name": store_name,
                "live_product_cost": product_cost,
                "live_p_c_ratio": p_c_ratio,
                "live_growth_pct": growth_pct,
                "live_image_url": image_url,
                "live_product_url": href if href else page_url,
                "live_page_url": page_url,
            }
        )

    return cards


# ============================================================
# MATCHING + VERIFICATION
# ============================================================

def score_match(board_row, live_card: dict) -> float:
    board_name = str(board_row.get("product_name", "")).strip()
    board_image = str(board_row.get("image_url", "")).strip()
    board_cost = clean_money(board_row.get("product_cost", 0))

    live_name = str(live_card.get("live_product_name", "")).strip()
    live_image = str(live_card.get("live_image_url", "")).strip()
    live_cost = clean_money(live_card.get("live_product_cost", 0))

    name_score = text_similarity(board_name, live_name) * 60
    overlap_score = token_overlap(board_name, live_name) * 20

    image_score = 0
    if image_filename(board_image) and image_filename(board_image) == image_filename(live_image):
        image_score = 25

    cost_score = 0
    if close_enough(board_cost, live_cost, tolerance_pct=15):
        cost_score = 10

    return round(name_score + overlap_score + image_score + cost_score, 2)


def verify_stats(board_row, live_card: dict) -> dict:
    board_cost = clean_money(board_row.get("product_cost", 0))
    board_p_c = clean_float(board_row.get("p_c_ratio", 0))
    board_growth = clean_float(board_row.get("growth_pct", 0))

    live_cost = clean_money(live_card.get("live_product_cost", 0))
    live_p_c = clean_float(live_card.get("live_p_c_ratio", 0))
    live_growth = clean_float(live_card.get("live_growth_pct", 0))

    cost_diff_pct = percent_difference(board_cost, live_cost)
    p_c_diff = round(abs(board_p_c - live_p_c), 2)
    growth_diff = round(abs(board_growth - live_growth), 2)

    cost_verified = "YES" if close_enough(board_cost, live_cost, 15) else "NO"
    p_c_verified = "YES" if p_c_diff <= 0.2 else "NO"
    growth_verified = "YES" if growth_diff <= 10 else "NO"

    if board_growth == 0 and live_growth == 0:
        growth_verified = "UNKNOWN"

    return {
        "price_verified": cost_verified,
        "p_c_verified": p_c_verified,
        "growth_verified": growth_verified,
        "cost_difference_pct": cost_diff_pct,
        "p_c_difference": p_c_diff,
        "growth_difference": growth_diff,
    }


def verify_one_product(page, row) -> dict:
    board_name = str(row.get("product_name", "")).strip()
    search_terms = get_search_terms(row)

    best_card = None
    best_score = 0
    best_search = ""
    total_cards_seen = 0

    for search_term in search_terms:
        print(f"Searching: {search_term}")

        if not search_zendrop(page, search_term):
            continue

        cards = extract_live_cards(page)
        total_cards_seen += len(cards)

        print(f"Live cards found: {len(cards)}")

        for card in cards:
            score = score_match(row, card)

            if score > best_score:
                best_score = score
                best_card = card
                best_search = search_term

        if best_score >= 90:
            break

    if best_card is None:
        return {
            "real_item_verified": "NO",
            "auto_check_status": "NO MATCH",
            "auto_match_score": 0,
            "auto_search_used": " | ".join(search_terms),
            "live_cards_seen": total_cards_seen,
            "auto_matched_name": "",
            "auto_matched_cost": "",
            "auto_matched_image_url": "",
            "live_p_c_ratio": "",
            "live_growth_pct": "",
            "price_verified": "NO",
            "p_c_verified": "NO",
            "growth_verified": "NO",
            "cost_difference_pct": "",
            "p_c_difference": "",
            "growth_difference": "",
            "auto_checked_at": now_text(),
            "verification_status": "NO MATCH",
            "exact_match_found": "NO",
            "exact_product_url": "",
            "verification_notes": "Live Zendrop search did not find a reliable matching product.",
        }

    stat_result = verify_stats(row, best_card)

    if best_score >= 90:
        item_status = "VERIFIED"
        exact_match = "YES"
        real_item_verified = "YES"
    elif best_score >= 70:
        item_status = "NEEDS CHECK"
        exact_match = "MAYBE"
        real_item_verified = "MAYBE"
    else:
        item_status = "NO MATCH"
        exact_match = "NO"
        real_item_verified = "NO"

    stats_ok = (
        stat_result["price_verified"] == "YES"
        and stat_result["p_c_verified"] == "YES"
    )

    if real_item_verified == "YES" and stats_ok:
        notes = "Live Zendrop match found. Price and main stats look verified."
    elif real_item_verified in ["YES", "MAYBE"]:
        notes = "Live Zendrop match found, but price/stats need manual review."
    else:
        notes = "Weak live match. Manual review required."

    return {
        "real_item_verified": real_item_verified,
        "auto_check_status": item_status,
        "auto_match_score": best_score,
        "auto_search_used": best_search,
        "live_cards_seen": total_cards_seen,
        "auto_matched_name": best_card.get("live_product_name", ""),
        "auto_matched_cost": best_card.get("live_product_cost", ""),
        "auto_matched_image_url": best_card.get("live_image_url", ""),
        "live_p_c_ratio": best_card.get("live_p_c_ratio", ""),
        "live_growth_pct": best_card.get("live_growth_pct", ""),
        "live_store_name": best_card.get("live_store_name", ""),
        "exact_product_url": best_card.get("live_product_url", ""),
        "auto_checked_at": now_text(),
        "verification_status": item_status,
        "exact_match_found": exact_match,
        "real_product_cost": best_card.get("live_product_cost", ""),
        "verification_notes": notes,
        **stat_result,
    }


# ============================================================
# SAVE
# ============================================================

def save_progress(df: pd.DataFrame):
    VERIFICATION_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.parent.mkdir(exist_ok=True)

    df.to_csv(VERIFICATION_PATH, index=False)
    df.to_csv(RESULTS_PATH, index=False)

    print()
    print(f"Saved verification board: {VERIFICATION_PATH}")
    print(f"Saved live verification results: {RESULTS_PATH}")
    print()


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10, help="How many products to verify this run.")
    parser.add_argument("--start", type=int, default=0, help="Start row index.")
    parser.add_argument("--include-verified", action="store_true", help="Re-check already verified products.")
    args = parser.parse_args()

    if not VERIFICATION_PATH.exists():
        raise FileNotFoundError(
            "Missing output/all_products_verification.csv. Run make_full_verification_queue.py first."
        )

    df = pd.read_csv(VERIFICATION_PATH).fillna("").astype("object")

    result_cols = [
        "real_item_verified",
        "auto_check_status",
        "auto_match_score",
        "auto_search_used",
        "live_cards_seen",
        "auto_matched_name",
        "auto_matched_cost",
        "auto_matched_image_url",
        "live_p_c_ratio",
        "live_growth_pct",
        "live_store_name",
        "price_verified",
        "p_c_verified",
        "growth_verified",
        "cost_difference_pct",
        "p_c_difference",
        "growth_difference",
        "auto_checked_at",
        "verification_status",
        "exact_match_found",
        "exact_product_url",
        "real_product_cost",
        "verification_notes",
    ]

    for col in result_cols:
        if col not in df.columns:
            df[col] = ""

    indexes = list(range(args.start, len(df)))

    if not args.include_verified:
        indexes = [
            idx for idx in indexes
            if str(df.loc[idx, "verification_status"]).upper() != "VERIFIED"
        ]

    if args.limit > 0:
        indexes = indexes[: args.limit]

    print()
    print("=" * 72)
    print("LIVE ZENDROP PRODUCT + PRICE/STATS VERIFIER")
    print(f"Products in board: {len(df)}")
    print(f"Products scheduled this run: {len(indexes)}")
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
        open_find_products(page)

        print("Log into Zendrop if needed.")
        print("Complete verification if it appears.")
        print("Make sure Find Products is visible.")
        input("Press ENTER to begin verification... ")

        checked = 0

        try:
            for idx in indexes:
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
                    df[key] = df[key].astype("object")
                    df.loc[idx, key] = value

                checked += 1

                print(f"Result: {result.get('auto_check_status')}")
                print(f"Real item verified: {result.get('real_item_verified')}")
                print(f"Match score: {result.get('auto_match_score')}")
                print(f"Matched name: {result.get('auto_matched_name')}")
                print(f"Board/live price verified: {result.get('price_verified')}")
                print(f"P/C verified: {result.get('p_c_verified')}")
                print(f"Growth verified: {result.get('growth_verified')}")

                if checked % SAVE_EVERY == 0:
                    save_progress(df)

        except KeyboardInterrupt:
            print()
            print("Stopped by user. Saving progress...")

        finally:
            save_progress(df)
            browser.close()

    print()
    print("Verification complete.")
    print(f"Checked this run: {checked}")


if __name__ == "__main__":
    main()
