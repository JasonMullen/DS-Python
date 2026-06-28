from __future__ import annotations

import argparse
import hashlib
import io
import re
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import pandas as pd
from PIL import Image
from playwright.sync_api import sync_playwright


USER_DATA_DIR = ".browser/zendrop_profile"
START_URL = "https://app.zendrop.com/product?page=1"

DEFAULT_INPUT = Path("output/all_products_verification.csv")
DEFAULT_OUTPUT = Path("output/url_image_verification_results.csv")

WAIT_MS = 3500
SAVE_EVERY = 5


# ============================================================
# CLEANING HELPERS
# ============================================================

def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_money(value: Any) -> float:
    text = clean_text(value).replace(",", "")
    match = re.search(r"\$?\s?(\d+(?:\.\d+)?)", text)
    return round(float(match.group(1)), 2) if match else 0.0


def clean_float(value: Any) -> float:
    text = clean_text(value).replace(",", "")
    match = re.search(r"([+-]?\d+(?:\.\d+)?)", text)
    return round(float(match.group(1)), 2) if match else 0.0


def text_similarity(a: Any, b: Any) -> float:
    a = normalize_text(a)
    b = normalize_text(b)
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b).ratio(), 4)


def token_overlap(a: Any, b: Any) -> float:
    a_tokens = {x for x in normalize_text(a).split() if len(x) > 2}
    b_tokens = {x for x in normalize_text(b).split() if len(x) > 2}

    if not a_tokens or not b_tokens:
        return 0.0

    return round(len(a_tokens & b_tokens) / max(len(a_tokens), 1), 4)


def image_filename(url: Any) -> str:
    url = clean_text(url).split("?")[0].strip("/")
    if not url:
        return ""
    return url.split("/")[-1].lower()


def percent_difference(expected: float, actual: float) -> float:
    if expected <= 0 or actual <= 0:
        return 999.0
    return round(abs(expected - actual) / expected * 100, 2)


def close_enough(expected: float, actual: float, tolerance_pct: float) -> bool:
    if expected <= 0 or actual <= 0:
        return False
    return percent_difference(expected, actual) <= tolerance_pct


def safe_url(value: Any) -> str:
    url = clean_text(value)
    if not url or url.lower() in ["nan", "none", "null"]:
        return ""
    if url.startswith("http"):
        return url
    return ""


# ============================================================
# IMAGE HASH HELPERS
# ============================================================

def download_image_bytes(url: str, timeout: int = 12) -> bytes | None:
    if not url:
        return None

    try:
        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )
        with urlopen(req, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()

        if not data:
            return None

        if "image" not in content_type.lower() and not url.lower().endswith(
            (".jpg", ".jpeg", ".png", ".webp", ".gif")
        ):
            return None

        return data

    except Exception:
        return None


def average_hash_from_bytes(data: bytes, hash_size: int = 8) -> str:
    image = Image.open(io.BytesIO(data)).convert("L").resize((hash_size, hash_size))
    pixels = list(image.getdata())
    avg = sum(pixels) / len(pixels)

    bits = "".join("1" if pixel > avg else "0" for pixel in pixels)
    width = int(len(bits) / 4)

    return f"{int(bits, 2):0{width}x}"


def hamming_distance(hash_a: str, hash_b: str) -> int:
    if not hash_a or not hash_b:
        return 999

    try:
        a = bin(int(hash_a, 16))[2:].zfill(64)
        b = bin(int(hash_b, 16))[2:].zfill(64)
        return sum(x != y for x, y in zip(a, b))
    except Exception:
        return 999


def image_hash_from_url(url: str) -> str:
    data = download_image_bytes(url)
    if not data:
        return ""
    try:
        return average_hash_from_bytes(data)
    except Exception:
        return ""


def quick_image_id(url: Any) -> str:
    url = clean_text(url)
    if not url:
        return ""
    return hashlib.md5(url.split("?")[0].encode("utf-8")).hexdigest()


# ============================================================
# PAGE + ZENDROP HELPERS
# ============================================================

def wait_if_security_check(page):
    try:
        body = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        body = ""

    current_url = page.url.lower()

    signals = [
        "security verification",
        "checking your browser",
        "verify you are human",
        "cloudflare",
        "not a bot",
        "just a moment",
    ]

    if any(signal in body for signal in signals) or "challenge" in current_url:
        print()
        print("=" * 72)
        print("ZENDROP SECURITY CHECK DETECTED")
        print("Complete the check manually in Chrome.")
        print("After the product page is visible, return here and press ENTER.")
        print("=" * 72)
        input("Press ENTER after completing verification... ")
        time.sleep(3)


def page_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def page_is_bad(page) -> bool:
    text = page_text(page).lower()
    url = page.url.lower()

    bad_signals = [
        "404",
        "page not found",
        "not found",
        "something went wrong",
        "this page doesn't exist",
        "this page does not exist",
        "error",
    ]

    if any(signal in text for signal in bad_signals):
        return True

    if "login" in url and "zendrop" in url:
        return False

    return False


def extract_page_images(page) -> list[dict]:
    try:
        return page.evaluate(
            """
            () => Array.from(document.querySelectorAll("img")).map((img) => {
                const rect = img.getBoundingClientRect();
                return {
                    src: img.src || "",
                    alt: img.alt || "",
                    width: rect.width || img.naturalWidth || 0,
                    height: rect.height || img.naturalHeight || 0,
                    visible: rect.width > 20 && rect.height > 20
                };
            }).filter(x => x.src && x.visible)
            """
        )
    except Exception:
        return []


def extract_live_numbers_from_text(text: str) -> dict:
    money_values = re.findall(r"\$\s?\d+(?:\.\d+)?", text)
    ratio_values = re.findall(r"(\d+(?:\.\d+)?)\s*x", text.lower())
    pct_values = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", text)

    return {
        "live_cost": clean_money(money_values[0]) if money_values else 0.0,
        "live_p_c_ratio": clean_float(ratio_values[0]) if ratio_values else 0.0,
        "live_growth_pct": clean_float(pct_values[0]) if pct_values else 0.0,
        "money_values_seen": " | ".join(money_values[:8]),
        "ratio_values_seen": " | ".join(ratio_values[:8]),
        "percent_values_seen": " | ".join(pct_values[:8]),
    }


def extract_product_cards(page) -> list[dict]:
    try:
        raw_cards = page.evaluate(
            """
            () => {
                const results = [];
                const seen = new Set();
                const buttons = Array.from(document.querySelectorAll("button, [role='button']"));

                for (const button of buttons) {
                    const bText = (button.innerText || "").toLowerCase();
                    if (!bText.includes("add")) continue;

                    let node = button;

                    for (let depth = 0; depth < 12; depth++) {
                        if (!node || !node.parentElement) break;
                        node = node.parentElement;

                        const text = node.innerText || "";
                        const lower = text.toLowerCase();
                        const img = node.querySelector("img");
                        const anchor = node.querySelector("a[href]") || node.closest("a[href]");

                        const hasProductSignals =
                            lower.includes("cost") &&
                            lower.includes("p/c") &&
                            lower.includes("growth") &&
                            /\\$\\s?\\d+(?:\\.\\d+)?/.test(text) &&
                            img;

                        if (!hasProductSignals) continue;

                        const key = text.replace(/\\s+/g, " ").trim();
                        if (seen.has(key)) break;
                        seen.add(key);

                        results.push({
                            text,
                            image_url: img ? img.src || "" : "",
                            image_alt: img ? img.alt || "" : "",
                            href: anchor ? anchor.href || "" : "",
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

    for raw in raw_cards:
        text = clean_text(raw.get("text", ""))
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        numbers = extract_live_numbers_from_text(text)

        product_name = ""
        store_name = lines[0] if lines else ""

        stop_index = None
        for i, line in enumerate(lines):
            if line.lower() in ["cost", "p/c", "growth"]:
                stop_index = i
                break

        if stop_index and stop_index > 1:
            product_name = " ".join(lines[1:stop_index]).strip()
        elif len(lines) >= 2:
            product_name = lines[1].strip()

        cards.append(
            {
                "live_name": product_name,
                "live_store_name": store_name,
                "live_image_url": clean_text(raw.get("image_url", "")),
                "live_product_url": clean_text(raw.get("href", "")),
                "live_text": text[:1000],
                **numbers,
            }
        )

    return cards


# ============================================================
# MATCHING LOGIC
# ============================================================

def score_image_match(expected_url: str, live_url: str, expected_hash: str = "") -> dict:
    if not expected_url or not live_url:
        return {
            "image_score": 0,
            "image_match_method": "",
            "image_hash_distance": "",
        }

    expected_clean = expected_url.split("?")[0]
    live_clean = live_url.split("?")[0]

    if expected_clean == live_clean:
        return {
            "image_score": 100,
            "image_match_method": "exact_image_url",
            "image_hash_distance": 0,
        }

    if image_filename(expected_url) and image_filename(expected_url) == image_filename(live_url):
        return {
            "image_score": 90,
            "image_match_method": "same_image_filename",
            "image_hash_distance": "",
        }

    if quick_image_id(expected_url) == quick_image_id(live_url):
        return {
            "image_score": 90,
            "image_match_method": "same_normalized_image_url",
            "image_hash_distance": "",
        }

    if expected_hash:
        live_hash = image_hash_from_url(live_url)
        distance = hamming_distance(expected_hash, live_hash)

        if distance <= 5:
            return {
                "image_score": 85,
                "image_match_method": "perceptual_hash_strong",
                "image_hash_distance": distance,
            }

        if distance <= 10:
            return {
                "image_score": 70,
                "image_match_method": "perceptual_hash_possible",
                "image_hash_distance": distance,
            }

        return {
            "image_score": 0,
            "image_match_method": "image_hash_no_match",
            "image_hash_distance": distance,
        }

    return {
        "image_score": 0,
        "image_match_method": "no_image_match",
        "image_hash_distance": "",
    }


def score_live_candidate(row, candidate: dict, expected_hash: str = "") -> dict:
    expected_name = clean_text(row.get("product_name", ""))
    expected_cost = clean_money(row.get("product_cost", 0))
    expected_p_c = clean_float(row.get("p_c_ratio", 0))
    expected_growth = clean_float(row.get("growth_pct", 0))
    expected_image = safe_url(row.get("image_url", ""))

    live_name = clean_text(candidate.get("live_name", ""))
    live_cost = clean_money(candidate.get("live_cost", 0))
    live_p_c = clean_float(candidate.get("live_p_c_ratio", 0))
    live_growth = clean_float(candidate.get("live_growth_pct", 0))
    live_image = safe_url(candidate.get("live_image_url", ""))

    name_similarity = text_similarity(expected_name, live_name)
    overlap = token_overlap(expected_name, live_name)

    image_result = score_image_match(expected_image, live_image, expected_hash)

    price_score = 0
    if close_enough(expected_cost, live_cost, 15):
        price_score = 20
    elif close_enough(expected_cost, live_cost, 30):
        price_score = 10

    p_c_score = 0
    if expected_p_c > 0 and live_p_c > 0:
        if abs(expected_p_c - live_p_c) <= 0.2:
            p_c_score = 10
        elif abs(expected_p_c - live_p_c) <= 0.5:
            p_c_score = 5

    growth_score = 0
    if expected_growth != 0 and live_growth != 0:
        if abs(expected_growth - live_growth) <= 10:
            growth_score = 10
        elif abs(expected_growth - live_growth) <= 25:
            growth_score = 5

    name_score = name_similarity * 35
    overlap_score = overlap * 20
    image_score = image_result["image_score"] * 0.35

    total_score = round(name_score + overlap_score + image_score + price_score + p_c_score + growth_score, 2)

    return {
        "match_score": total_score,
        "name_similarity": name_similarity,
        "token_overlap": overlap,
        "price_score": price_score,
        "p_c_score": p_c_score,
        "growth_score": growth_score,
        **image_result,
    }


def verify_price_stats(row, candidate: dict) -> dict:
    expected_cost = clean_money(row.get("product_cost", 0))
    expected_p_c = clean_float(row.get("p_c_ratio", 0))
    expected_growth = clean_float(row.get("growth_pct", 0))

    live_cost = clean_money(candidate.get("live_cost", 0))
    live_p_c = clean_float(candidate.get("live_p_c_ratio", 0))
    live_growth = clean_float(candidate.get("live_growth_pct", 0))

    cost_diff_pct = percent_difference(expected_cost, live_cost)
    p_c_diff = round(abs(expected_p_c - live_p_c), 2) if expected_p_c and live_p_c else ""
    growth_diff = round(abs(expected_growth - live_growth), 2) if expected_growth and live_growth else ""

    return {
        "expected_cost": expected_cost,
        "verified_live_cost": live_cost,
        "price_verified": "YES" if close_enough(expected_cost, live_cost, 15) else "NO",
        "cost_difference_pct": cost_diff_pct,
        "expected_p_c_ratio": expected_p_c,
        "verified_live_p_c_ratio": live_p_c,
        "p_c_verified": "YES" if expected_p_c > 0 and live_p_c > 0 and abs(expected_p_c - live_p_c) <= 0.2 else "NO",
        "p_c_difference": p_c_diff,
        "expected_growth_pct": expected_growth,
        "verified_live_growth_pct": live_growth,
        "growth_verified": "YES" if expected_growth != 0 and live_growth != 0 and abs(expected_growth - live_growth) <= 10 else "UNKNOWN",
        "growth_difference": growth_diff,
    }


def final_status(score: float, url_worked: bool, image_score: float) -> tuple[str, str, str]:
    if score >= 85:
        return "VERIFIED", "YES", "High confidence match."

    if score >= 70:
        return "NEEDS CHECK", "MAYBE", "Possible match. Review manually."

    if url_worked and image_score >= 85:
        return "NEEDS CHECK", "MAYBE", "URL works and image looks strong, but other stats need review."

    return "NO MATCH", "NO", "Could not verify product from URL or image."


# ============================================================
# DIRECT URL VERIFICATION
# ============================================================

def get_candidate_from_current_page(page) -> dict:
    text = page_text(page)
    images = extract_page_images(page)
    numbers = extract_live_numbers_from_text(text)

    best_image = ""
    if images:
        sorted_images = sorted(
            images,
            key=lambda x: float(x.get("width", 0)) * float(x.get("height", 0)),
            reverse=True,
        )
        best_image = clean_text(sorted_images[0].get("src", ""))

    return {
        "live_name": "",
        "live_image_url": best_image,
        "live_product_url": page.url,
        "live_text": text[:1500],
        **numbers,
    }


def verify_by_direct_url(page, row, expected_hash: str) -> dict:
    url_candidates = [
        safe_url(row.get("exact_product_url", "")),
        safe_url(row.get("supplier_url", "")),
        safe_url(row.get("live_product_url", "")),
        safe_url(row.get("product_url", "")),
        safe_url(row.get("url", "")),
    ]

    url_candidates = [x for x in url_candidates if x]
    url_candidates = list(dict.fromkeys(url_candidates))

    if not url_candidates:
        return {
            "url_worked": "NO",
            "url_checked": "",
            "url_verification_status": "NO URL",
            "best_candidate": None,
            "best_score_data": None,
        }

    best_candidate = None
    best_score_data = None
    best_url = ""

    for url in url_candidates:
        print(f"Checking URL: {url}")

        try:
            page.goto(url, wait_until="commit", timeout=60000)
            page.wait_for_timeout(WAIT_MS)
            wait_if_security_check(page)

            if page_is_bad(page):
                continue

            cards = extract_product_cards(page)

            candidates = cards if cards else [get_candidate_from_current_page(page)]

            for candidate in candidates:
                if not candidate.get("live_product_url"):
                    candidate["live_product_url"] = page.url

                score_data = score_live_candidate(row, candidate, expected_hash)

                if best_score_data is None or score_data["match_score"] > best_score_data["match_score"]:
                    best_score_data = score_data
                    best_candidate = candidate
                    best_url = url

            if best_score_data and best_score_data["match_score"] >= 85:
                break

        except Exception as e:
            print(f"URL failed: {url} | {e}")
            continue

    if best_candidate is None:
        return {
            "url_worked": "NO",
            "url_checked": " | ".join(url_candidates),
            "url_verification_status": "URL FAILED",
            "best_candidate": None,
            "best_score_data": None,
        }

    return {
        "url_worked": "YES",
        "url_checked": best_url,
        "url_verification_status": "URL LOADED",
        "best_candidate": best_candidate,
        "best_score_data": best_score_data,
    }


# ============================================================
# IMAGE FALLBACK VERIFICATION
# ============================================================

def make_search_terms(product_name: str) -> list[str]:
    stop_words = {
        "for", "with", "and", "the", "from", "this", "that", "your",
        "men", "mens", "women", "womens", "unisex", "new", "hot",
        "premium", "creative", "fashion", "portable", "adjustable",
    }

    words = [
        word for word in normalize_text(product_name).split()
        if len(word) > 2 and word not in stop_words
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

    unique = []
    for term in terms:
        if term and term.lower() not in [x.lower() for x in unique]:
            unique.append(term)

    return unique[:5]


def open_search_url(page, query: str):
    search_url = f"https://app.zendrop.com/product?page=1&search={quote_plus(query)}"
    page.goto(search_url, wait_until="commit", timeout=60000)
    page.wait_for_timeout(WAIT_MS)
    wait_if_security_check(page)


def verify_by_image_fallback(page, row, expected_hash: str) -> dict:
    product_name = clean_text(row.get("product_name", ""))
    search_terms = make_search_terms(product_name)

    best_candidate = None
    best_score_data = None
    best_search = ""

    for term in search_terms:
        print(f"Image fallback search: {term}")

        try:
            open_search_url(page, term)

            cards = extract_product_cards(page)

            if not cards:
                page.wait_for_timeout(2500)
                cards = extract_product_cards(page)

            print(f"Live cards found: {len(cards)}")

            for card in cards:
                score_data = score_live_candidate(row, card, expected_hash)

                if best_score_data is None or score_data["match_score"] > best_score_data["match_score"]:
                    best_score_data = score_data
                    best_candidate = card
                    best_search = term

            if best_score_data and best_score_data["image_score"] >= 85:
                break

        except Exception as e:
            print(f"Image fallback failed for {term}: {e}")
            continue

    return {
        "image_fallback_search_used": best_search,
        "best_candidate": best_candidate,
        "best_score_data": best_score_data,
    }


# ============================================================
# VERIFY ONE PRODUCT
# ============================================================

def verify_one(page, row) -> dict:
    expected_image = safe_url(row.get("image_url", ""))
    expected_hash = image_hash_from_url(expected_image) if expected_image else ""

    url_result = verify_by_direct_url(page, row, expected_hash)

    source_method = "URL_DIRECT"
    best_candidate = url_result.get("best_candidate")
    best_score_data = url_result.get("best_score_data")
    image_search_used = ""

    if best_candidate is None or not best_score_data or best_score_data["match_score"] < 70:
        print("URL match weak or failed. Trying image fallback...")
        image_result = verify_by_image_fallback(page, row, expected_hash)

        if image_result.get("best_score_data") and (
            best_score_data is None
            or image_result["best_score_data"]["match_score"] > best_score_data["match_score"]
        ):
            source_method = "IMAGE_FALLBACK"
            best_candidate = image_result.get("best_candidate")
            best_score_data = image_result.get("best_score_data")
            image_search_used = image_result.get("image_fallback_search_used", "")

    if best_candidate is None or best_score_data is None:
        return {
            "real_item_verified": "NO",
            "verification_status": "NO MATCH",
            "exact_match_found": "NO",
            "verification_method": "URL_AND_IMAGE_FAILED",
            "url_checked": url_result.get("url_checked", ""),
            "url_worked": url_result.get("url_worked", "NO"),
            "url_verification_status": url_result.get("url_verification_status", ""),
            "image_fallback_search_used": image_search_used,
            "auto_match_score": 0,
            "image_score": 0,
            "image_match_method": "",
            "image_hash_distance": "",
            "auto_matched_name": "",
            "auto_matched_cost": "",
            "auto_matched_image_url": "",
            "exact_product_url": "",
            "price_verified": "NO",
            "p_c_verified": "NO",
            "growth_verified": "UNKNOWN",
            "auto_checked_at": now_text(),
            "verification_notes": "Could not verify by saved URL or image fallback.",
        }

    match_score = best_score_data["match_score"]
    image_score = best_score_data.get("image_score", 0)
    status, exact_match, notes = final_status(
        match_score,
        url_result.get("url_worked") == "YES",
        image_score,
    )

    stat_result = verify_price_stats(row, best_candidate)

    return {
        "real_item_verified": "YES" if status == "VERIFIED" else exact_match,
        "verification_status": status,
        "exact_match_found": exact_match,
        "verification_method": source_method,
        "url_checked": url_result.get("url_checked", ""),
        "url_worked": url_result.get("url_worked", "NO"),
        "url_verification_status": url_result.get("url_verification_status", ""),
        "image_fallback_search_used": image_search_used,
        "auto_match_score": match_score,
        "name_similarity": best_score_data.get("name_similarity", ""),
        "token_overlap": best_score_data.get("token_overlap", ""),
        "image_score": image_score,
        "image_match_method": best_score_data.get("image_match_method", ""),
        "image_hash_distance": best_score_data.get("image_hash_distance", ""),
        "auto_matched_name": best_candidate.get("live_name", ""),
        "auto_matched_cost": best_candidate.get("live_cost", ""),
        "auto_matched_image_url": best_candidate.get("live_image_url", ""),
        "exact_product_url": best_candidate.get("live_product_url", ""),
        "live_store_name": best_candidate.get("live_store_name", ""),
        "auto_checked_at": now_text(),
        "verification_notes": notes,
        **stat_result,
    }


# ============================================================
# MAIN
# ============================================================

def save_progress(df: pd.DataFrame, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    if DEFAULT_INPUT.exists():
        df.to_csv(DEFAULT_INPUT, index=False)

    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--include-verified", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Missing input CSV: {input_path}")

    df = pd.read_csv(input_path).fillna("").astype("object")

    result_columns = [
        "real_item_verified",
        "verification_status",
        "exact_match_found",
        "verification_method",
        "url_checked",
        "url_worked",
        "url_verification_status",
        "image_fallback_search_used",
        "auto_match_score",
        "name_similarity",
        "token_overlap",
        "image_score",
        "image_match_method",
        "image_hash_distance",
        "auto_matched_name",
        "auto_matched_cost",
        "auto_matched_image_url",
        "exact_product_url",
        "live_store_name",
        "expected_cost",
        "verified_live_cost",
        "price_verified",
        "cost_difference_pct",
        "expected_p_c_ratio",
        "verified_live_p_c_ratio",
        "p_c_verified",
        "p_c_difference",
        "expected_growth_pct",
        "verified_live_growth_pct",
        "growth_verified",
        "growth_difference",
        "auto_checked_at",
        "verification_notes",
    ]

    for col in result_columns:
        if col not in df.columns:
            df[col] = ""

    indexes = list(range(args.start, len(df)))

    if not args.include_verified and "verification_status" in df.columns:
        indexes = [
            idx for idx in indexes
            if clean_text(df.loc[idx, "verification_status"]).upper() != "VERIFIED"
        ]

    if args.limit > 0:
        indexes = indexes[: args.limit]

    print()
    print("=" * 72)
    print("ZENDROP URL + IMAGE + PRICE/STATS VERIFIER")
    print(f"Input CSV: {input_path}")
    print(f"Products in CSV: {len(df)}")
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
        page.goto(START_URL, wait_until="commit", timeout=60000)
        page.wait_for_timeout(WAIT_MS)
        wait_if_security_check(page)

        print("Log into Zendrop if needed.")
        print("Complete verification if it appears.")
        print("Then return here and press ENTER.")
        input("Press ENTER to begin verification... ")

        checked = 0

        try:
            for idx in indexes:
                product_name = clean_text(df.loc[idx, "product_name"])

                print()
                print("=" * 72)
                print(f"Checking row {idx + 1}/{len(df)}")
                print(f"Product: {product_name}")
                print("=" * 72)

                result = verify_one(page, df.loc[idx])

                for key, value in result.items():
                    if key not in df.columns:
                        df[key] = ""
                    df[key] = df[key].astype("object")
                    df.loc[idx, key] = value

                checked += 1

                print(f"Status: {result.get('verification_status')}")
                print(f"Method: {result.get('verification_method')}")
                print(f"Match score: {result.get('auto_match_score')}")
                print(f"Image score: {result.get('image_score')}")
                print(f"Image method: {result.get('image_match_method')}")
                print(f"Price verified: {result.get('price_verified')}")
                print(f"P/C verified: {result.get('p_c_verified')}")
                print(f"Growth verified: {result.get('growth_verified')}")

                if checked % SAVE_EVERY == 0:
                    save_progress(df, output_path)

        except KeyboardInterrupt:
            print("Stopped manually. Saving progress...")

        finally:
            save_progress(df, output_path)
            browser.close()

    print()
    print("Done.")
    print(f"Checked this run: {checked}")
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
