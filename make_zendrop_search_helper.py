from pathlib import Path
import re
import pandas as pd

INPUT_PATH = Path("output/opportunities.csv")
OUTPUT_PATH = Path("output/zendrop_search_helper.csv")

STOP_WORDS = {
    "for", "with", "and", "the", "a", "an", "of", "to", "in", "on",
    "new", "hot", "best", "fashion", "trend", "premium", "portable",
    "comfortable", "adjustable", "creative", "stylish", "oversized",
    "men", "mens", "women", "womens", "unisex"
}

def clean_name(name):
    name = str(name)
    name = re.sub(r"\|.*$", "", name)
    name = re.sub(r"[-–—]", " ", name)
    name = re.sub(r"\b\d+(\.\d+)?\s?(inch|in|cm|mm|oz|lb|lbs|pcs|pack|x)\b", " ", name, flags=re.I)
    name = re.sub(r"[^a-zA-Z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def make_search_terms(name):
    cleaned = clean_name(name)
    words = [w for w in cleaned.split() if len(w) > 2 and w.lower() not in STOP_WORDS]

    # Main search: first strong 3–5 words
    search_1 = " ".join(words[:5])

    # Shorter fallback
    search_2 = " ".join(words[:3])

    # Last fallback: most product-like nouns from the end
    search_3 = " ".join(words[-4:]) if len(words) >= 4 else search_2

    return search_1, search_2, search_3

df = pd.read_csv(INPUT_PATH)

search_1 = []
search_2 = []
search_3 = []

for name in df["product_name"]:
    s1, s2, s3 = make_search_terms(name)
    search_1.append(s1)
    search_2.append(s2)
    search_3.append(s3)

df["zendrop_search_1"] = search_1
df["zendrop_search_2"] = search_2
df["zendrop_search_3"] = search_3

columns = [
    "product_name",
    "zendrop_search_1",
    "zendrop_search_2",
    "zendrop_search_3",
    "source_guess",
    "category",
    "estimated_sale_price",
    "estimated_profit",
    "profit_margin_pct",
    "roi_pct",
    "final_score",
    "risk_level",
    "next_action",
    "risk_notes",
]

available = [col for col in columns if col in df.columns]

OUTPUT_PATH.parent.mkdir(exist_ok=True)
df[available].to_csv(OUTPUT_PATH, index=False)

print(f"Created search helper file: {OUTPUT_PATH}")
print(df[available].head(20))
