from pathlib import Path

import pandas as pd
import streamlit as st


# ============================================================
# EASY UPDATE SECTION
# ============================================================

APP_CONFIG = {
    "title": "📦 Dropship Product Research Board",
    "subtitle": "A clean product research dashboard for finding products worth deeper research, testing, or avoiding.",
    "csv_path": "output/opportunities.csv",
    "top_product_count": 5,
    "top_chart_count": 15,
}

DISPLAY_COLUMNS = [
    "product_name",
    "source_guess",
    "category",
    "estimated_sale_price",
    "estimated_profit",
    "profit_margin_pct",
    "roi_pct",
    "opportunity_score",
    "final_score",
    "risk_level",
    "next_action",
    "risk_notes",
    "supplier_url",
]

TERM_DEFINITIONS = {
    "Estimated Sale Price": "The price you expect to sell the product for.",
    "Product Cost": "The supplier cost before shipping, ads, and platform fees.",
    "Shipping Cost": "The estimated cost to ship the product to the customer.",
    "Estimated Profit": "Sale price minus product cost, shipping, fees, and estimated ad cost.",
    "Profit Margin": "The percent of the sale price that remains as profit.",
    "ROI": "Return on investment. Higher means more profit compared to cost.",
    "Opportunity Score": "The original score based on profit, margin, and demand signals.",
    "Final Score": "The adjusted score after subtracting product risk.",
    "Risk Level": "LOW, MEDIUM, HIGH, or UNKNOWN risk based on product problems.",
    "Risk Notes": "Warnings about shipping, missing cost, low margin, brand risk, or restricted product risk.",
    "Next Action": "What to do next: DEEP RESEARCH, WATCH, VERIFY FIRST, PASS, or AVOID.",
    "Source Guess": "The likely supplier source, such as Zendrop or DHgate.",
}


# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Dropship Product Board",
    page_icon="📦",
    layout="wide",
)


# ============================================================
# DESIGN
# ============================================================

st.markdown(
    """
    <style>
        .stApp {
            background-color: #f3f4f6 !important;
            color: #111827 !important;
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1450px;
        }

        h1, h2, h3, h4, h5, h6, p, label {
            color: #111827 !important;
        }

        section[data-testid="stSidebar"] {
            background-color: #e5e7eb !important;
            color: #111827 !important;
            border-right: 1px solid #d1d5db;
        }

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label {
            color: #111827 !important;
        }

        div[data-baseweb="select"] {
            background-color: #111827 !important;
            border-radius: 10px !important;
            border: 1px solid #374151 !important;
        }

        div[data-baseweb="select"] * {
            color: #ffffff !important;
        }

        div[data-baseweb="popover"] {
            background-color: #111827 !important;
        }

        div[data-baseweb="popover"] * {
            color: #ffffff !important;
            background-color: #111827 !important;
        }

        div[role="option"] {
            color: #ffffff !important;
            background-color: #111827 !important;
        }

        div[role="option"] * {
            color: #ffffff !important;
        }

        div[role="option"]:hover,
        div[role="option"]:hover * {
            background-color: #374151 !important;
            color: #ffffff !important;
        }

        [data-testid="stMetric"] {
            background-color: #ffffff !important;
            padding: 18px;
            border-radius: 14px;
            border: 1px solid #d1d5db;
            box-shadow: 0px 2px 8px rgba(0,0,0,0.04);
        }

        [data-testid="stMetricLabel"] {
            color: #374151 !important;
            font-weight: 700 !important;
        }

        [data-testid="stMetricValue"] {
            color: #111827 !important;
            font-weight: 900 !important;
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #ffffff !important;
            border: 1px solid #d1d5db !important;
            border-radius: 16px !important;
            box-shadow: 0px 2px 8px rgba(0,0,0,0.04);
        }

        [data-testid="stDataFrame"] {
            background-color: #ffffff !important;
        }

        a {
            color: #2563eb !important;
            font-weight: 700;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def money(value):
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "N/A"


def pct(value):
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "N/A"


def action_label(action):
    action = str(action).upper()

    if "DEEP" in action or "TEST" in action:
        return "✅ DEEP RESEARCH"
    if "WATCH" in action:
        return "👀 WATCH"
    if "VERIFY" in action:
        return "⚠️ VERIFY FIRST"
    if "AVOID" in action:
        return "🚫 AVOID"
    if "PASS" in action:
        return "❌ PASS"

    return action


def risk_label(risk):
    risk = str(risk).upper()

    if risk == "LOW":
        return "🟢 LOW RISK"
    if risk == "MEDIUM":
        return "🟡 MEDIUM RISK"
    if risk == "HIGH":
        return "🔴 HIGH RISK"

    return "⚪ UNKNOWN RISK"


def load_data(csv_path):
    path = Path(csv_path)

    if not path.exists():
        return None

    df = pd.read_csv(path)

    numeric_columns = [
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "opportunity_score",
        "final_score",
        "risk_points",
        "estimated_sale_price",
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "final_score" not in df.columns and "opportunity_score" in df.columns:
        df["final_score"] = df["opportunity_score"]

    if "next_action" not in df.columns:
        df["next_action"] = df.get("decision", "REVIEW")

    if "risk_level" not in df.columns:
        df["risk_level"] = "UNKNOWN"

    if "source_guess" not in df.columns:
        df["source_guess"] = "Unknown"

    if "category" not in df.columns:
        df["category"] = "Unknown"

    return df.sort_values("final_score", ascending=False)


# ============================================================
# LOAD DATA
# ============================================================

st.title(APP_CONFIG["title"])
st.write(APP_CONFIG["subtitle"])

df = load_data(APP_CONFIG["csv_path"])

if df is None:
    st.warning("No opportunities.csv file found yet.")
    st.code("python -m dropship_researcher.main")
    st.stop()

if df.empty:
    st.warning("Your opportunities.csv file is empty.")
    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("Filters")

    category_options = ["All"] + sorted(df["category"].fillna("Unknown").unique().tolist())
    source_options = ["All"] + sorted(df["source_guess"].fillna("Unknown").unique().tolist())
    risk_options = ["All"] + sorted(df["risk_level"].fillna("Unknown").unique().tolist())
    action_options = ["All"] + sorted(df["next_action"].fillna("Review").unique().tolist())

    selected_category = st.selectbox("Category", category_options)
    selected_source = st.selectbox("Supplier Source", source_options)
    selected_risk = st.selectbox("Risk Level", risk_options)
    selected_action = st.selectbox("Next Action", action_options)

    st.divider()

    min_profit = st.slider("Minimum Estimated Profit", 0, 100, 0)
    min_score = st.slider("Minimum Final Score", 0, 100, 0)

    st.divider()

    st.header("Terminology Guide")

    with st.expander("What the terms mean"):
        for term, definition in TERM_DEFINITIONS.items():
            st.markdown(f"**{term}:** {definition}")

    st.divider()

    st.header("How to Update")
    st.markdown(
        """
1. Add products to `data/supplier_products.csv`.
2. Run `python -m dropship_researcher.main`.
3. Restart or refresh this dashboard.
4. Review the products in the ranking table.
5. Commit updates to GitHub.
        """
    )


# ============================================================
# FILTER DATA
# ============================================================

filtered = df.copy()

if selected_category != "All":
    filtered = filtered[filtered["category"] == selected_category]

if selected_source != "All":
    filtered = filtered[filtered["source_guess"] == selected_source]

if selected_risk != "All":
    filtered = filtered[filtered["risk_level"] == selected_risk]

if selected_action != "All":
    filtered = filtered[filtered["next_action"] == selected_action]

filtered = filtered[filtered["estimated_profit"].fillna(0) >= min_profit]
filtered = filtered[filtered["final_score"].fillna(0) >= min_score]


# ============================================================
# METRICS
# ============================================================

total_products = len(df)
filtered_products = len(filtered)
deep_research_count = df["next_action"].astype(str).str.contains(
    "DEEP RESEARCH", case=False, na=False
).sum()
low_risk_count = df["risk_level"].astype(str).str.contains(
    "LOW", case=False, na=False
).sum()
best_score = df["final_score"].max() if "final_score" in df.columns else 0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Products", total_products)
col2.metric("Filtered View", filtered_products)
col3.metric("Deep Research", int(deep_research_count))
col4.metric("Low Risk", int(low_risk_count))
col5.metric("Best Score", round(best_score, 1))

st.divider()


# ============================================================
# TOP PRODUCTS SECTION
# ============================================================

st.header("🔥 Best Products to Look At First")

top_products = filtered.head(APP_CONFIG["top_product_count"])

if top_products.empty:
    st.info("No products match your filters.")
else:
    for _, row in top_products.iterrows():
        product_name = row.get("product_name", "Unnamed Product")
        category = row.get("category", "Unknown")
        source = row.get("source_guess", "Unknown")
        action = row.get("next_action", "Review")
        risk = row.get("risk_level", "Unknown")
        profit = row.get("estimated_profit", 0)
        margin = row.get("profit_margin_pct", 0)
        roi = row.get("roi_pct", 0)
        score = row.get("final_score", 0)
        notes = row.get("risk_notes", "No notes")
        supplier_url = row.get("supplier_url", "")

        with st.container(border=True):
            st.subheader(str(product_name))

            badge_col1, badge_col2, badge_col3 = st.columns([1, 1, 2])
            badge_col1.write(action_label(action))
            badge_col2.write(risk_label(risk))
            badge_col3.write(f"**Source:** {source}")

            metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
            metric_col1.metric("Estimated Profit", money(profit))
            metric_col2.metric("Margin", pct(margin))
            metric_col3.metric("ROI", pct(roi))
            metric_col4.metric(
                "Final Score",
                round(float(score), 1) if pd.notna(score) else "N/A",
            )

            st.write(f"**Category:** {category}")
            st.write(f"**Risk Notes:** {notes}")

            if supplier_url:
                st.write(f"**Supplier Link:** {supplier_url}")

st.divider()


# ============================================================
# FULL PRODUCT RANKING TABLE ? ALWAYS SHOW ALL CSV PRODUCTS
# ============================================================

st.header("?? Full Product Ranking Table")

st.write(
    f"Showing **all {len(df)} products** from `output/opportunities.csv`. "
    "Sidebar filters only affect the Best Products section, not this full table."
)

available_columns = [col for col in DISPLAY_COLUMNS if col in df.columns]

all_products_table = df.sort_values("final_score", ascending=False)

st.dataframe(
    all_products_table[available_columns],
    use_container_width=True,
    hide_index=True,
    height=1000,
)

st.divider()


# ============================================================
# CHART
# ============================================================

st.header("📈 Top Final Scores")

if "product_name" in filtered.columns and "final_score" in filtered.columns:
    chart_df = filtered.sort_values("final_score", ascending=False).head(
        APP_CONFIG["top_chart_count"]
    )
    st.bar_chart(chart_df.set_index("product_name")["final_score"])
else:
    st.info("Need product_name and final_score columns to show chart.")

st.divider()


# ============================================================
# NEXT STEPS
# ============================================================

st.header("✅ What to Do Next")

st.markdown(
    """
1. Use the **Best Products** section for your quick shortlist.
2. Use the **Full Product Ranking Table** to review every product.
3. Start with products marked **DEEP RESEARCH** or **WATCH**.
4. Avoid products marked **HIGH RISK**.
5. Manually check supplier reviews, shipping time, product photos, and real demand.
6. Pick only 5 products for serious store/ad testing.
    """
)
