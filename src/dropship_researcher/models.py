from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class ProductCandidate:
    product_name: str
    keyword: str
    product_cost: float = 0.0
    shipping_cost: float = 0.0
    estimated_sale_price: Optional[float] = None
    supplier_url: str = ""
    category: str = ""
    source: str = "supplier_csv"


@dataclass(frozen=True)
class MarketSnapshot:
    keyword: str
    median_price: Optional[float]
    average_price: Optional[float]
    lowest_price: Optional[float]
    listing_count: int
    source: str


@dataclass(frozen=True)
class TrendSignal:
    keyword: str
    mention_count: int
    source: str


@dataclass(frozen=True)
class Opportunity:
    product_name: str
    keyword: str
    category: str
    supplier_url: str
    product_cost: float
    shipping_cost: float
    estimated_sale_price: float
    marketplace_median_price: Optional[float]
    listing_count: int
    reddit_mentions: int
    estimated_fees: float
    estimated_ad_cost: float
    estimated_profit: float
    profit_margin_pct: float
    roi_pct: float
    opportunity_score: float
    decision: str

    def to_dict(self) -> dict:
        return asdict(self)
