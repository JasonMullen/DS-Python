from __future__ import annotations

import argparse
import io
import re
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd
from PIL import Image
from playwright.sync_api import sync_playwright


INPUT_PATH = Path("output/all_products_verification.csv")
OUTPUT_PATH = Path("output/manual_live_verification_results.csv")
SAVE_EVERY = 1


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize(value: Any) -> str:
    text = clean(value).lower()
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_money(value: Any) -> float:
    text = clean(value).replace(",", "")
    match = re.search(r"\$?\s?(\d+(?:\.\d+)?)", text)
    return round(float(match.group(1)), 2) if match else 0.0


def clean_float(value: Any) -> float:
    text = clean(value).replace(",", "")
    match = re.search(r"([+-]?\d+(?:\.\d+)?)", text)
    return round(float(match.group(1)), 2) if match else 0.0


def text_similarity(a: Any, b: Any) -> float:
    a = normalize(a)
    b = normalize(b)

    if not a or not b:
        return 0.0

    return round(SequenceMatcher(None, a, b).ratio(), 4)


def token_overlap(a: Any, b: Any) -> float:
    a_tokens = {x for x in normalize(a).split() if len(x) > 2}
    b_tokens = {x for x in normalize(b).split() if len(x) > 2}

    if not a_tokens or not b_tokens:
        return 0.0

    return round(len(a_tokens & b_tokens) / len(a_tokens), 4)


def safe_url(value: Any) -> str:
    url = clean(value)
    if not url or url.lower() in {"nan", "none", "null"}:
        return ""
    return url if url.startswith("http") else ""


def image_filename(url: Any) -> str:
    url = clean(url).split("?")[0].strip("/")
    if not url:
        return ""
    return url.split("/")[-1].lower()


def download_image(url: str) -> bytes | None:
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

        with urlopen(req, timeout=12) as response:
            data = response.read()

        return data if data else None

    except Exception:
        return None


def average_hash(data: bytes, hash_size: int = 8) -> str:
    image = Image.open(io.BytesIO(data)).convert("L").resize((hash_size, hash_size))
    pixels = list(image.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel > avg else "0" for pixel in pixels)
    width = int(len(bits) / 4)
    return f"{int(bits, 2):0{width}x}"


def image_hash(url: str) -> str:
    data = download_image(url)
    if not data:
        return ""

    try:
        return average_hash(data)
    except Exception:
        return ""


def hash_distance(a: str, b: str) -> int:
    if not a or not b:
        return 999

    try:
        aa = bin(int(a, 16))[2:].zfill(64)
        bb = bin(int(b, 16))[2:].zfill(64)
        return sum(x != y for x, y in zip(aa, bb))
    except Exception:
        return 999


def pct_difference(expected: float, actual: float) -> float:
    if expected <= 0 or actual <= 0:
        return 999.0

    return round(abs(expected - actual) / expected * 100, 2)


def close_enough(expected: float, actual: float, tolerance_pct: float) -> bool:
    if expected <= 0 or actual <= 0:
        return False

    return pct_difference(expected, actual) <= tolerance_pct


def extract_numbers(text: str) -> dict:
    money_values = re.findall(r"\$\s?\d+(?:\.\d+)?", text)
    ratios = re.findall(r"(\d+(?:\.\d+)?)\s*x", text.lower())
    percents = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%", text)

    cost = 0.0
    p_c_ratio = 0.0
    growth = 0.0

    cost_patterns = [
        r"cost\s*\$?\s?(\d+(?:\.\d+)?)",
        r"product cost\s*\$?\s?(\d+(?:\.\d+)?)",
        r"price\s*\$?\s?(\d+(?:\.\d+)?)",
    ]

    for pattern in cost_patterns:
        match = re.search(pattern, text.lower())
        if match:
            cost = clean_money(match.group(1))
            break

    if not cost and money_values:
        cost = clean_money(money_values[0])

    pc_patterns = [
        r"p/c\s*(\d+(?:\.\d+)?)\s*x",
        r"p/c\s*[:\n ]+\s*(\d+(?:\.\d+)?)",
    ]

    for pattern in pc_patterns:
        match = re.search(pattern, text.lower())
        if match:
            p_c_ratio = clean_float(match.group(1))
            break

    if not p_c_ratio and ratios:
        p_c_ratio = clean_float(ratios[0])

    growth_patterns = [
        r"growth\s*([+-]?\d+(?:\.\d+)?)\s*%",
        r"growth\s*[:\n ]+\s*([+-]?\d+(?:\.\d+)?)",
    ]

    for pattern in growth_patterns:
        match = re.search(pattern, text.lower())
        if match:
            growth = clean_float(match.group(1))
            break

    if not growth and percents:
        growth = clean_float(percents[0])

    return {
        "live_cost": cost,
        "live_p_c_ratio": p_c_ratio,
        "live_growth_pct": growth,
        "money_values_seen": " | ".join(money_values[:8]),
        "ratio_values_seen": " | ".join(ratios[:8]),
        "percent_values_seen": " | ".join(percents[:8]),
    }


def get_active_page(context):
    pages = [p for p in context.pages if not p.is_closed()]

    if not pages:
        raise RuntimeError("No open Chrome pages found.")

    zendrop_pages = [p for p in pages if "zendrop" in p.url.lower()]

    if zendrop_pages:
        return zendrop_pages[-1]

    return pages[-1]


def read_current_page(context) -> dict:
    page = get_active_page(context)

    data = page.evaluate(
        """
        () => {
            const bodyText = document.body ? document.body.innerText || "" : "";

            const headings = Array.from(
                document.querySelectorAll("h1,h2,h3,[class*='title'],[class*='name']")
            ).map(x => (x.innerText || "").trim()).filter(Boolean).slice(0, 30);

            const images = Array.from(document.querySelectorAll("img")).map((img) => {
                const rect = img.getBoundingClientRect();
                return {
                    src: img.src || "",
                    alt: img.alt || "",
                    width: rect.width || img.naturalWidth || 0,
                    height: rect.height || img.naturalHeight || 0,
                    visible: rect.width > 30 && rect.height > 30
                };
            }).filter(x => x.src && x.visible);

            return {
                url: window.location.href,
                title: document.title || "",
                text: bodyText,
                headings,
                images
            };
        }
        """
    )

    data["numbers"] = extract_numbers(data.get("text", ""))

    return data


def score_images(expected_image: str, live_images: list[dict], expected_hash: str) -> dict:
    best = {
        "image_score": 0,
        "image_match_method": "",
        "image_hash_distance": "",
        "matched_image_url": "",
        "matched_image_alt": "",
    }

    if not expected_image or not live_images:
        return best

    expected_clean = expected_image.split("?")[0]
    expected_file = image_filename(expected_image)

    for img in live_images:
        live_url = safe_url(img.get("src", ""))
        live_alt = clean(img.get("alt", ""))

        if not live_url:
            continue

        score = 0
        method = ""
        distance = ""

        live_clean = live_url.split("?")[0]
        live_file = image_filename(live_url)

        if expected_clean == live_clean:
            score = 100
            method = "exact_image_url"

        elif expected_file and expected_file == live_file:
            score = 90
            method = "same_image_filename"

        elif expected_hash:
            live_hash = image_hash(live_url)
            distance = hash_distance(expected_hash, live_hash)

            if distance <= 5:
                score = 88
                method = "perceptual_hash_strong"
            elif distance <= 10:
                score = 75
                method = "perceptual_hash_possible"
            elif distance <= 16:
                score = 55
                method = "perceptual_hash_weak"

        if score > best["image_score"]:
            best = {
                "image_score": score,
                "image_match_method": method,
                "image_hash_distance": distance,
                "matched_image_url": live_url,
                "matched_image_alt": live_alt,
            }

    return best


def score_name(expected_name: str, page_data: dict) -> dict:
    candidates = []

    candidates.append(page_data.get("title", ""))

    for heading in page_data.get("headings", []):
        candidates.append(heading)

    for img in page_data.get("images", []):
        alt = clean(img.get("alt", ""))
        if alt:
            candidates.append(alt)

    best_name = ""
    best_similarity = 0.0
    best_overlap = 0.0

    for candidate in candidates:
        similarity = text_similarity(expected_name, candidate)
        overlap = token_overlap(expected_name, candidate)

        combined = (similarity * 0.65) + (overlap * 0.35)

        if combined > ((best_similarity * 0.65) + (best_overlap * 0.35)):
            best_name = candidate
            best_similarity = similarity
            best_overlap = overlap

    body_overlap = token_overlap(expected_name, page_data.get("text", ""))

    name_score = round(max(best_similarity * 100, body_overlap * 80), 2)

    return {
        "name_score": name_score,
        "best_live_name": best_name,
        "name_similarity": best_similarity,
        "token_overlap": best_overlap,
        "body_token_overlap": body_overlap,
    }


def verify_row_against_page(row, page_data: dict, url_worked: str) -> dict:
    expected_name = clean(row.get("product_name", ""))
    expected_image = safe_url(row.get("image_url", ""))
    expected_cost = clean_money(row.get("product_cost", 0))
    expected_p_c = clean_float(row.get("p_c_ratio", 0))
    expected_growth = clean_float(row.get("growth_pct", 0))

    expected_hash = image_hash(expected_image) if expected_image else ""

    image_result = score_images(expected_image, page_data.get("images", []), expected_hash)
    name_result = score_name(expected_name, page_data)

    numbers = page_data.get("numbers", {})
    live_cost = clean_money(numbers.get("live_cost", 0))
    live_p_c = clean_float(numbers.get("live_p_c_ratio", 0))
    live_growth = clean_float(numbers.get("live_growth_pct", 0))

    price_verified = "YES" if close_enough(expected_cost, live_cost, 15) else "NO"

    p_c_verified = "UNKNOWN"
    if expected_p_c > 0 and live_p_c > 0:
        p_c_verified = "YES" if abs(expected_p_c - live_p_c) <= 0.2 else "NO"

    growth_verified = "UNKNOWN"
    if expected_growth != 0 and live_growth != 0:
        growth_verified = "YES" if abs(expected_growth - live_growth) <= 10 else "NO"

    price_score = 0
    if price_verified == "YES":
        price_score = 100
    elif close_enough(expected_cost, live_cost, 30):
        price_score = 60

    p_c_score = 50
    if p_c_verified == "YES":
        p_c_score = 100
    elif p_c_verified == "NO":
        p_c_score = 0

    growth_score = 50
    if growth_verified == "YES":
        growth_score = 100
    elif growth_verified == "NO":
        growth_score = 0

    total_score = round(
        image_result["image_score"] * 0.35
        + name_result["name_score"] * 0.30
        + price_score * 0.20
        + p_c_score * 0.075
        + growth_score * 0.075,
        2,
    )

    if total_score >= 85:
        status = "VERIFIED"
        exact_match = "YES"
        notes = "Strong match from current Zendrop page."
    elif total_score >= 65:
        status = "NEEDS CHECK"
        exact_match = "MAYBE"
        notes = "Possible match. Review image, name, price, and stats manually."
    else:
        status = "NO MATCH"
        exact_match = "NO"
        notes = "Current page does not confidently match the CSV product."

    method = "MANUAL_URL_CHECK" if url_worked == "YES" else "MANUAL_IMAGE_FALLBACK"

    return {
        "real_item_verified": "YES" if status == "VERIFIED" else exact_match,
        "verification_status": status,
        "exact_match_found": exact_match,
        "verification_method": method,
        "manual_url_worked": url_worked,
        "current_zendrop_url": page_data.get("url", ""),
        "auto_match_score": total_score,
        **name_result,
        "image_score": image_result["image_score"],
        "image_match_method": image_result["image_match_method"],
        "image_hash_distance": image_result["image_hash_distance"],
        "auto_matched_image_url": image_result["matched_image_url"],
        "auto_matched_name": name_result["best_live_name"],
        "expected_cost": expected_cost,
        "verified_live_cost": live_cost,
        "price_verified": price_verified,
        "cost_difference_pct": pct_difference(expected_cost, live_cost),
        "expected_p_c_ratio": expected_p_c,
        "verified_live_p_c_ratio": live_p_c,
        "p_c_verified": p_c_verified,
        "p_c_difference": round(abs(expected_p_c - live_p_c), 2) if expected_p_c and live_p_c else "",
        "expected_growth_pct": expected_growth,
        "verified_live_growth_pct": live_growth,
        "growth_verified": growth_verified,
        "growth_difference": round(abs(expected_growth - live_growth), 2) if expected_growth and live_growth else "",
        "money_values_seen": numbers.get("money_values_seen", ""),
        "ratio_values_seen": numbers.get("ratio_values_seen", ""),
        "percent_values_seen": numbers.get("percent_values_seen", ""),
        "auto_checked_at": now_text(),
        "verification_notes": notes,
    }


def get_url_candidates(row) -> list[str]:
    candidates = []

    for col in [
        "exact_product_url",
        "supplier_url",
        "product_url",
        "live_product_url",
        "url",
    ]:
        url = safe_url(row.get(col, ""))
        if url:
            candidates.append(url)

    return list(dict.fromkeys(candidates))


def save(df: pd.DataFrame):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(OUTPUT_PATH, index=False)
    df.to_csv(INPUT_PATH, index=False)

    print(f"Saved: {OUTPUT_PATH}")
    print(f"Updated: {INPUT_PATH}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--include-verified", action="store_true")
    args = parser.parse_args()

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing {INPUT_PATH}. Run make_full_verification_queue.py first.")

    df = pd.read_csv(INPUT_PATH).fillna("").astype("object")

    result_cols = [
        "real_item_verified",
        "verification_status",
        "exact_match_found",
        "verification_method",
        "manual_url_worked",
        "current_zendrop_url",
        "auto_match_score",
        "name_score",
        "best_live_name",
        "name_similarity",
        "token_overlap",
        "body_token_overlap",
        "image_score",
        "image_match_method",
        "image_hash_distance",
        "auto_matched_image_url",
        "auto_matched_name",
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
        "money_values_seen",
        "ratio_values_seen",
        "percent_values_seen",
        "auto_checked_at",
        "verification_notes",
    ]

    for col in result_cols:
        if col not in df.columns:
            df[col] = ""

    indexes = list(range(args.start, len(df)))

    if not args.include_verified:
        indexes = [
            idx for idx in indexes
            if clean(df.loc[idx, "verification_status"]).upper() != "VERIFIED"
        ]

    if args.limit > 0:
        indexes = indexes[: args.limit]

    print()
    print("=" * 72)
    print("MANUAL ZENDROP URL + IMAGE VERIFIER")
    print("This does NOT automate Zendrop searching or clicking.")
    print("You manually open the product. The script compares the visible page.")
    print(f"Products in CSV: {len(df)}")
    print(f"Products scheduled this run: {len(indexes)}")
    print("=" * 72)
    print()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")

        if not browser.contexts:
            raise RuntimeError("No Chrome context found. Start Chrome with remote debugging first.")

        context = browser.contexts[0]

        checked = 0

        try:
            for idx in indexes:
                row = df.loc[idx]
                product_name = clean(row.get("product_name", ""))
                expected_image = safe_url(row.get("image_url", ""))
                expected_cost = clean(row.get("product_cost", ""))
                expected_p_c = clean(row.get("p_c_ratio", ""))
                expected_growth = clean(row.get("growth_pct", ""))

                urls = get_url_candidates(row)

                print()
                print("=" * 72)
                print(f"ROW {idx + 1}/{len(df)}")
                print(f"PRODUCT: {product_name}")
                print(f"EXPECTED COST: {expected_cost}")
                print(f"EXPECTED P/C: {expected_p_c}")
                print(f"EXPECTED GROWTH: {expected_growth}")
                print(f"IMAGE: {expected_image}")
                print()
                print("URL CANDIDATES:")

                if urls:
                    for n, url in enumerate(urls, start=1):
                        print(f"{n}. {url}")
                else:
                    print("No saved URL found. Use the image/name to search manually.")

                print()
                print("Open the saved URL manually in Chrome.")
                print("If it fails, manually search Zendrop using the image/name.")
                print("When the matching product/page is visible, come back here.")

                command = input("Press ENTER to read current page, S to skip, or Q to save and quit: ").strip().lower()

                if command == "q":
                    break

                if command == "s":
                    continue

                url_worked = input("Did the saved CSV URL work? Type Y/N/UNKNOWN: ").strip().upper()

                if url_worked.startswith("Y"):
                    url_worked = "YES"
                elif url_worked.startswith("N"):
                    url_worked = "NO"
                else:
                    url_worked = "UNKNOWN"

                page_data = read_current_page(context)
                result = verify_row_against_page(row, page_data, url_worked)

                print()
                print("RESULT")
                print(f"Status: {result['verification_status']}")
                print(f"Method: {result['verification_method']}")
                print(f"Total score: {result['auto_match_score']}")
                print(f"Name score: {result['name_score']}")
                print(f"Best live name: {result['best_live_name']}")
                print(f"Image score: {result['image_score']}")
                print(f"Image method: {result['image_match_method']}")
                print(f"Price verified: {result['price_verified']}")
                print(f"Live cost found: {result['verified_live_cost']}")
                print(f"P/C verified: {result['p_c_verified']}")
                print(f"Live P/C found: {result['verified_live_p_c_ratio']}")
                print(f"Growth verified: {result['growth_verified']}")
                print(f"Live growth found: {result['verified_live_growth_pct']}")

                override = input("Accept? ENTER=yes, V=force VERIFIED, C=NEEDS CHECK, N=NO MATCH: ").strip().lower()

                if override == "v":
                    result["verification_status"] = "VERIFIED"
                    result["exact_match_found"] = "YES"
                    result["real_item_verified"] = "YES"
                    result["verification_notes"] = "Manually forced verified after review."
                elif override == "c":
                    result["verification_status"] = "NEEDS CHECK"
                    result["exact_match_found"] = "MAYBE"
                    result["real_item_verified"] = "MAYBE"
                    result["verification_notes"] = "Manually marked needs check after review."
                elif override == "n":
                    result["verification_status"] = "NO MATCH"
                    result["exact_match_found"] = "NO"
                    result["real_item_verified"] = "NO"
                    result["verification_notes"] = "Manually marked no match after review."

                for key, value in result.items():
                    if key not in df.columns:
                        df[key] = ""
                    df[key] = df[key].astype("object")
                    df.loc[idx, key] = value

                checked += 1

                if checked % SAVE_EVERY == 0:
                    save(df)

        except KeyboardInterrupt:
            print("Stopped manually. Saving progress...")

        finally:
            save(df)
            browser.close()

    print()
    print("Done.")
    print(f"Checked this run: {checked}")


if __name__ == "__main__":
    main()
