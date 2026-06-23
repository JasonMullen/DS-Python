from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .config import get_settings
from .ebay import EbayBrowseClient
from .models import ProductCandidate, MarketSnapshot
from .reddit_rss import collect_reddit_text, count_keyword_mentions, discover_candidate_keywords
from .scoring import score_opportunity
from .supplier_csv import load_seed_keywords, load_supplier_products
from .product_rules import add_validation_columns
from .product_rules import add_validation_columns


def build_candidates(supplier_csv: Path, keywords_file: Path) -> list[ProductCandidate]:
    candidates = load_supplier_products(supplier_csv)
    existing = {c.keyword for c in candidates}
    for keyword in load_seed_keywords(keywords_file):
        if keyword not in existing:
            # Seed-only ideas need costs before they can be fully scored.
            candidates.append(ProductCandidate(product_name=keyword.title(), keyword=keyword, source="seed_keyword"))
    return candidates


def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    candidates = build_candidates(Path(args.supplier_csv), Path(args.keywords_file))

    print("Collecting Reddit trend signals...")
    reddit_text = collect_reddit_text(limit=args.reddit_limit)
    discovered = discover_candidate_keywords(reddit_text, top_n=15)
    print("Possible discovered phrases:", ", ".join(discovered[:10]) if discovered else "none")

    keywords = sorted({candidate.keyword for candidate in candidates})
    trends = count_keyword_mentions(keywords, reddit_text)

    ebay = EbayBrowseClient(settings.ebay_bearer_token, settings.ebay_marketplace_id)
    if not ebay.enabled:
        print("No EBAY_BEARER_TOKEN found. Using supplier CSV estimated_sale_price where available.")

    opportunities = []
    for candidate in candidates:
        market = ebay.search_prices(candidate.keyword, limit=args.ebay_limit) if ebay.enabled else MarketSnapshot(
            keyword=candidate.keyword,
            median_price=None,
            average_price=None,
            lowest_price=None,
            listing_count=0,
            source="manual_estimate",
        )
        opportunity = score_opportunity(
            candidate=candidate,
            market=market,
            trend=trends.get(candidate.keyword),
            fee_rate=settings.fee_rate,
            ad_cost_per_sale=settings.ad_cost_per_sale,
            min_profit_margin=settings.min_profit_margin,
        )
        if opportunity:
            opportunities.append(opportunity.to_dict())

    if not opportunities:
        print("No opportunities scored. Add product_cost, shipping_cost, and estimated_sale_price to the supplier CSV or add an eBay token.")
        return

    df = add_validation_columns(pd.DataFrame(opportunities))
    df = df.sort_values("final_score", ascending=False)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"Saved: {output_path}")
    print(df[["product_name", "estimated_profit", "profit_margin_pct", "opportunity_score", "final_score", "risk_level", "next_action", "decision"]].head(args.show).to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find and score dropshipping product opportunities.")
    parser.add_argument("--supplier-csv", default="data/supplier_products.csv")
    parser.add_argument("--keywords-file", default="data/seed_keywords.txt")
    parser.add_argument("--output", default="output/opportunities.csv")
    parser.add_argument("--ebay-limit", type=int, default=50)
    parser.add_argument("--reddit-limit", type=int, default=25)
    parser.add_argument("--show", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
