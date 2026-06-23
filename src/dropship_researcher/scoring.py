from __future__ import annotations

import math
from typing import Optional

from .models import MarketSnapshot, Opportunity, ProductCandidate, TrendSignal


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def choose_sale_price(candidate: ProductCandidate, market: MarketSnapshot) -> Optional[float]:
    # Prefer real marketplace median price. Fall back to your manually estimated sale price.
    if market.median_price and market.median_price > 0:
        return market.median_price
    return candidate.estimated_sale_price


def score_opportunity(
    candidate: ProductCandidate,
    market: MarketSnapshot,
    trend: TrendSignal | None,
    fee_rate: float,
    ad_cost_per_sale: float,
    min_profit_margin: float,
) -> Opportunity | None:
    sale_price = choose_sale_price(candidate, market)
    if sale_price is None or sale_price <= 0:
        return None

    landed_cost = candidate.product_cost + candidate.shipping_cost
    estimated_fees = sale_price * fee_rate
    profit = sale_price - landed_cost - estimated_fees - ad_cost_per_sale
    margin = profit / sale_price
    roi = profit / max(landed_cost + ad_cost_per_sale, 0.01)

    # Profit score favors products that still work after fees and ads.
    profit_score = clamp((margin / 0.45) * 100)
    # Listing count is not perfect demand, but it hints that buyers search this marketplace.
    market_score = clamp((math.log1p(market.listing_count) / math.log1p(300)) * 100)
    mentions = trend.mention_count if trend else 0
    # A few mentions across product subreddits is meaningful; don't let Reddit dominate.
    trend_score = clamp((mentions / 5) * 100)

    overall = round((0.55 * profit_score) + (0.25 * market_score) + (0.20 * trend_score), 2)

    if margin < min_profit_margin:
        decision = "PASS: margin too thin"
    elif profit < 8:
        decision = "WATCH: profit dollars low"
    elif overall >= 70:
        decision = "TEST: strong candidate"
    else:
        decision = "WATCH: needs validation"

    return Opportunity(
        product_name=candidate.product_name,
        keyword=candidate.keyword,
        category=candidate.category,
        supplier_url=candidate.supplier_url,
        product_cost=round(candidate.product_cost, 2),
        shipping_cost=round(candidate.shipping_cost, 2),
        estimated_sale_price=round(sale_price, 2),
        marketplace_median_price=market.median_price,
        listing_count=market.listing_count,
        reddit_mentions=mentions,
        estimated_fees=round(estimated_fees, 2),
        estimated_ad_cost=round(ad_cost_per_sale, 2),
        estimated_profit=round(profit, 2),
        profit_margin_pct=round(margin * 100, 2),
        roi_pct=round(roi * 100, 2),
        opportunity_score=overall,
        decision=decision,
    )
