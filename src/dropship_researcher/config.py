from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    ebay_bearer_token: str | None
    ebay_marketplace_id: str
    fee_rate: float
    ad_cost_per_sale: float
    min_profit_margin: float


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        ebay_bearer_token=os.getenv("EBAY_BEARER_TOKEN") or None,
        ebay_marketplace_id=os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US"),
        fee_rate=float(os.getenv("ESTIMATED_PAYMENT_AND_PLATFORM_FEE_RATE", "0.15")),
        ad_cost_per_sale=float(os.getenv("ESTIMATED_AD_COST_PER_SALE", "5.00")),
        min_profit_margin=float(os.getenv("MIN_PROFIT_MARGIN", "0.25")),
    )
