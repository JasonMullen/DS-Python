from __future__ import annotations

from statistics import median, mean
from typing import Any

import requests

from .models import MarketSnapshot


class EbayBrowseClient:
    """Small wrapper around eBay's official Browse API.

    Requires EBAY_BEARER_TOKEN in .env. The tool intentionally uses the API instead
    of scraping eBay pages, which is more stable and cleaner for a real project.
    """

    BASE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

    def __init__(self, bearer_token: str | None, marketplace_id: str = "EBAY_US") -> None:
        self.bearer_token = bearer_token
        self.marketplace_id = marketplace_id

    @property
    def enabled(self) -> bool:
        return bool(self.bearer_token)

    def search_prices(self, keyword: str, limit: int = 50) -> MarketSnapshot:
        if not self.enabled:
            return MarketSnapshot(
                keyword=keyword,
                median_price=None,
                average_price=None,
                lowest_price=None,
                listing_count=0,
                source="ebay_disabled_no_token",
            )

        params = {
            "q": keyword,
            "limit": str(min(limit, 200)),
            "filter": "priceCurrency:USD,conditions:{NEW}",
        }
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
            "Accept": "application/json",
            "User-Agent": "dropship-trend-finder/0.1",
        }
        response = requests.get(self.BASE_URL, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        items = payload.get("itemSummaries", [])

        prices: list[float] = []
        for item in items:
            price = item.get("price") or {}
            value = price.get("value")
            if value is None:
                continue
            try:
                prices.append(float(value))
            except (TypeError, ValueError):
                continue

        if not prices:
            return MarketSnapshot(keyword, None, None, None, 0, "ebay_browse_api")

        return MarketSnapshot(
            keyword=keyword,
            median_price=round(median(prices), 2),
            average_price=round(mean(prices), 2),
            lowest_price=round(min(prices), 2),
            listing_count=int(payload.get("total", len(prices)) or len(prices)),
            source="ebay_browse_api",
        )
