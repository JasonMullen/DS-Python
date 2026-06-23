# Dropship Trend Finder

A GitHub-ready Python starter project for finding and scoring dropshipping product opportunities.

The goal is **not** to magically create passive income. The goal is to build a repeatable research system that helps you pick better products, avoid bad margins, and test ideas faster.

## What this tool does

1. Reads product ideas and supplier costs from `data/supplier_products.csv`.
2. Pulls trend signals from public Reddit RSS feeds.
3. Optionally checks live eBay marketplace prices through the official eBay Browse API.
4. Estimates profit after product cost, shipping, platform/payment fees, and ad cost.
5. Ranks products into `TEST`, `WATCH`, or `PASS`.
6. Saves results to `output/opportunities.csv`.

## Why APIs/RSS instead of random scraping?

Randomly scraping TikTok, Google Trends, AliExpress, Amazon, or eBay pages can break quickly and may violate terms of service. This project starts with cleaner sources:

- Reddit RSS for trend chatter.
- eBay Browse API for market pricing.
- Your own supplier CSV for landed costs.

## Setup

```bash
cd dropship_trend_finder
python -m venv .venv
source .venv/Scripts/activate  # Git Bash on Windows
# or: .venv\Scripts\activate   # PowerShell
pip install -r requirements.txt
cp .env.example .env
```

The program can run without an eBay token by using the estimated sale prices in your supplier CSV. For better data, add an eBay OAuth bearer token to `.env`.

## Run it

Install the project locally once, then run the command:

```bash
pip install -e .
python -m dropship_researcher.main
```

For a quick run without installing:

```bash
PYTHONPATH=src python -m dropship_researcher.main
```

## Input file format

Edit `data/supplier_products.csv`:

```csv
product_name,keyword,product_cost,shipping_cost,estimated_sale_price,supplier_url,category
Resistance Band Set,resistance bands,6.50,2.50,24.99,https://example.com/resistance-band-set,fitness
```

Important columns:

- `product_name`: what you call the product.
- `keyword`: what buyers search.
- `product_cost`: supplier price.
- `shipping_cost`: shipping/handling cost.
- `estimated_sale_price`: fallback selling price if no eBay token is used.
- `supplier_url`: link to your supplier.
- `category`: niche/category.

## Scoring logic

The opportunity score weighs:

- 55% profit margin strength.
- 25% marketplace listing signal.
- 20% Reddit trend mentions.

A product is usually worth testing only if it still has margin after product cost, shipping, platform/payment fees, and ad cost.

## GitHub commands

Create a new GitHub repo first. Then run:

```bash
cd dropship_trend_finder
git init
git add .
git commit -m "Initial dropship trend finder"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/dropship-trend-finder.git
git push -u origin main
```

Future updates:

```bash
git status
git add .
git commit -m "Improve product scoring"
git push
```

## July build roadmap

### Week 1: Research engine

- Get this repo running.
- Add 30-50 supplier products to the CSV.
- Create your scoring assumptions in `.env`.
- Push to GitHub.

### Week 2: Validation dashboard

- Add a Streamlit dashboard.
- Track top 10 candidates daily.
- Add columns for customer pain point, TikTok angle, and competitor ads.

### Week 3: Store rebuild

- Pick one niche, not random products.
- Rewrite old gymwear store or start fresh with a clear offer.
- Build product page, FAQ, refund policy, shipping policy, and email capture.

### Week 4: Testing

- Test 3-5 products with small-budget creative.
- Track visitors, add-to-cart rate, checkout rate, profit, and refunds.
- Kill products with bad margins quickly.

## Next upgrades

- Add Shopify product upload through Shopify Admin API.
- Add Meta Ad Library research for competitor creatives where available.
- Add a Streamlit web UI.
- Add scheduled daily CSV reports.
