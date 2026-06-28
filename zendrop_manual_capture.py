from pathlib import Path
import re
import time
import pandas as pd
from playwright.sync_api import sync_playwright

USER_DATA_DIR = ".browser/zendrop_profile"
OUTPUT_PATH = Path("data/zendrop_manual_capture.csv")


def clean_money(value):
    if not value:
        return 0.0

    value = str(value).replace(",", "")
    match = re.search(r"\$?\s?(\d+(?:\.\d+)?)", value)
    return float(match.group(1)) if match else 0.0


def guess_category(text):
    text = text.lower()

    if any(w in text for w in ["pet", "dog", "cat"]):
        return "pets"
    if any(w in text for w in ["kitchen", "bottle", "cup", "cooking"]):
        return "kitchen"
    if any(w in text for w in ["beauty", "hair", "skin"]):
        return "beauty"
    if any(w in text for w in ["fitness", "gym", "yoga"]):
        return "fitness"
    if any(w in text for w in ["phone", "charger", "usb", "led"]):
        return "tech"
    if any(w in text for w in ["car", "auto"]):
        return "car"
    if any(w in text for w in ["shirt", "shoes", "dress", "jacket"]):
        return "clothing"

    return "general"


def extract_products_from_visible_text(page):
    products = []
    seen = set()

    cards = page.locator("div").all()

    for card in cards:
        try:
            text = card.inner_text(timeout=300).strip()
        except Exception:
            continue

        if not text:
            continue

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        money_values = re.findall(r"\$\s?\d+(?:\.\d+)?", text)

        if len(lines) < 2 or not money_values:
            continue

        name = lines[0]

        if len(name) < 4 or len(name) > 120:
            continue

        if name.lower() in seen:
            continue

        seen.add(name.lower())

        product_cost = clean_money(money_values[0])
        estimated_sale_price = clean_money(money_values[-1])

        if product_cost <= 0:
            continue

        if estimated_sale_price <= product_cost:
            estimated_sale_price = round(product_cost * 2.5, 2)

        products.append(
            {
                "product_name": name,
                "keyword": name.lower(),
                "product_cost": product_cost,
                "shipping_cost": 0.00,
                "estimated_sale_price": estimated_sale_price,
                "supplier_url": page.url,
                "category": guess_category(text),
                "source": "Zendrop Manual Capture",
                "supplier": "Zendrop",
            }
        )

    return products


def save_products(products):
    if not products:
        print("No products found.")
        return

    df = pd.DataFrame(products)
    df = df.drop_duplicates(subset=["product_name"])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)

    print(f"Saved {len(df)} products to {OUTPUT_PATH}")


def main():
    all_products = []
    seen = set()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1500, "height": 950},
        )

        page = browser.new_page()
        page.goto("https://app.zendrop.com/product?page=1", wait_until="commit")

        print()
        print("Manual capture mode")
        print("=" * 60)
        print("1. Log into Zendrop if needed.")
        print("2. Complete verification manually.")
        print("3. Go to the Find Products page.")
        print("4. Scroll down manually until many products are visible.")
        print("5. Come back here and press ENTER.")
        print("=" * 60)

        while True:
            input("Press ENTER to capture visible products, or type Ctrl+C to stop... ")

            products = extract_products_from_visible_text(page)

            added = 0
            for product in products:
                name = product["product_name"].lower()

                if name not in seen:
                    seen.add(name)
                    all_products.append(product)
                    added += 1

            print(f"Captured this round: {added}")
            print(f"Total products captured: {len(all_products)}")

            save_products(all_products)

            print()
            print("Now scroll further manually in Chrome, then press ENTER again.")
            time.sleep(1)


if __name__ == "__main__":
    main()
