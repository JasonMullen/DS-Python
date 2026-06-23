from dropship_researcher.models import ProductCandidate, MarketSnapshot, TrendSignal
from dropship_researcher.scoring import score_opportunity


def test_score_opportunity_calculates_profit():
    candidate = ProductCandidate(
        product_name="Test Product",
        keyword="test product",
        product_cost=5,
        shipping_cost=2,
        estimated_sale_price=25,
    )
    market = MarketSnapshot("test product", median_price=25, average_price=25, lowest_price=20, listing_count=100, source="test")
    trend = TrendSignal("test product", mention_count=3, source="test")

    result = score_opportunity(candidate, market, trend, fee_rate=0.15, ad_cost_per_sale=5, min_profit_margin=0.25)

    assert result is not None
    assert result.estimated_profit == 8.25
    assert result.profit_margin_pct == 33.0
