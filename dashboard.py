from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Dropship Trend Finder",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Dropship Trend Finder Dashboard")
st.write("Review product opportunities ranked by profit, margin, and opportunity score.")

csv_path = Path("output/opportunities.csv")

if not csv_path.exists():
    st.warning("No opportunities.csv file found. Run the research tool first.")
    st.code("python -m dropship_researcher.main")
    st.stop()

df = pd.read_csv(csv_path)

st.subheader("Overview")

total_products = len(df)

if "decision" in df.columns:
    test_count = df["decision"].astype(str).str.contains("TEST", case=False, na=False).sum()
    watch_count = df["decision"].astype(str).str.contains("WATCH", case=False, na=False).sum()
    pass_count = df["decision"].astype(str).str.contains("PASS", case=False, na=False).sum()
else:
    test_count = watch_count = pass_count = 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Products", total_products)
col2.metric("TEST", test_count)
col3.metric("WATCH", watch_count)
col4.metric("PASS", pass_count)

st.divider()

st.subheader("Product Opportunities")

sort_column = "opportunity_score" if "opportunity_score" in df.columns else df.columns[0]

df_sorted = df.sort_values(sort_column, ascending=False)

st.dataframe(df_sorted, use_container_width=True)

st.divider()

st.subheader("Top 10 Opportunity Scores")

if "product_name" in df.columns and "opportunity_score" in df.columns:
    chart_df = df.sort_values("opportunity_score", ascending=False).head(10)
    st.bar_chart(chart_df.set_index("product_name")["opportunity_score"])
else:
    st.info("Need product_name and opportunity_score columns to show chart.")

st.divider()

st.subheader("Best Candidates to Research Manually")

if "opportunity_score" in df.columns:
    best_candidates = df.sort_values("opportunity_score", ascending=False).head(5)
else:
    best_candidates = df.head(5)

for _, row in best_candidates.iterrows():
    product_name = row.get("product_name", "Unnamed Product")
    decision = row.get("decision", "No decision")
    estimated_profit = row.get("estimated_profit", "N/A")
    profit_margin = row.get("profit_margin_pct", "N/A")
    opportunity_score = row.get("opportunity_score", "N/A")
    supplier_url = row.get("supplier_url", "N/A")

    st.markdown(f"### {product_name}")
    st.write(f"**Decision:** {decision}")
    st.write(f"**Estimated Profit:** {estimated_profit}")
    st.write(f"**Profit Margin:** {profit_margin}")
    st.write(f"**Opportunity Score:** {opportunity_score}")
    st.write(f"**Supplier URL:** {supplier_url}")
