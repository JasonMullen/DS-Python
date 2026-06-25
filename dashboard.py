
from pathlib import Path

import pandas as pd
import streamlit as st


APP_CONFIG = {
    "title": "?? Dropship Product Research Board",
    "subtitle": "A clean product research dashboard for finding products worth deeper research, testing, or avoiding.",
    "csv_path": "output/opportunities.csv",
    "supplier_path": "data/supplier_products.csv",
    "top_product_count": 5,
    "top_chart_count": 15,
}


DISPLAY_COLUMNS = [
    "image_url",
    "product_name",
    "source_guess",
    "store_name",
    "category",
    "product_cost",
    "estimated_sale_price",
    "estimated_profit",
    "profit_margin_pct",
    "roi_pct",
    "p_c_ratio",
    "growth_pct",
    "order_trend_score",
    "saturation",
    "top_country",
    "opportunity_score",
    "final_score",
    "risk_level",
    "next_action",
    "risk_notes",
    "supplier_url",
]


TERM_DEFINITIONS = {
    "Estimated Sale Price": "Projected selling price based on cost and pricing ratio.",
    "Product Cost": "Supplier cost captured from Zendrop.",
    "Shipping Cost": "Shipping fee if available. If missing, risk notes will warn you.",
    "Estimated Profit": "Estimated sale price minus product cost and shipping.",
    "Profit Margin": "How much of the sale price is profit.",
    "ROI": "Profit compared to product cost.",
    "P/C": "Zendrop product card ratio. Higher can mean more markup potential.",
    "Growth": "Zendrop product card growth percentage.",
    "Opportunity Score": "Base score from your product scoring program.",
    "Final Score": "Score after risk penalties.",
    "Risk Level": "LOW, MEDIUM, or HIGH risk.",
    "Risk Notes": "Why the product was flagged.",
    "Next Action": "TEST, WATCH, or PASS.",
    "Source Guess": "Where the product came from.",
}


st.set_page_config(
    page_title="Dropship Product Research Board",
    page_icon="??",
    layout="wide",
)


st.markdown(
    """
    <style>
    .stApp {
        background-color: #f3f4f6 !important;
        color: #111827 !important;
    }

    h1, h2, h3, h4, h5, h6, p, label, span, div {
        color: #111827 !important;
    }

    section[data-testid="stSidebar"] {
        background-color: #e5e7eb !important;
    }

    section[data-testid="stSidebar"] * {
        color: #111827 !important;
    }

    div[data-baseweb="select"] > div {
        background-color: #111827 !important;
        color: white !important;
        border-color: #374151 !important;
    }

    div[data-baseweb="select"] span {
        color: white !important;
    }

    div[data-baseweb="popover"] {
        background-color: #111827 !important;
    }

    div[data-baseweb="popover"] * {
        color: white !important;
    }

    ul[role="listbox"] {
        background-color: #111827 !important;
    }

    li[role="option"] {
        background-color: #111827 !important;
        color: white !important;
    }

    li[role="option"] div {
        color: white !important;
    }

    li[role="option"]:hover {
        background-color: #374151 !important;
    }

    input {
        color: #111827 !important;
    }

    .stMetric {
        background: white !important;
        border: 1px solid #d1d5db !important;
        border-radius: 14px !important;
        padding: 14px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data() -> pd.DataFrame:
    csv_path = Path(APP_CONFIG["csv_path"])
    supplier_path = Path(APP_CONFIG["supplier_path"])

    if not csv_path.exists():
        st.error("Missing output/opportunities.csv. Run: python -m dropship_researcher.main")
        st.stop()

    df = pd.read_csv(csv_path).fillna("")

    if supplier_path.exists():
        supplier_df = pd.read_csv(supplier_path).fillna("")

        supplier_cols = [
            "product_name",
            "image_url",
            "store_name",
            "p_c_ratio",
            "growth_pct",
            "order_trend_score",
            "saturation",
            "top_country",
        ]

        supplier_cols = [col for col in supplier_cols if col in supplier_df.columns]

        if "product_name" in supplier_cols:
            supplier_small = supplier_df[supplier_cols].drop_duplicates(subset=["product_name"])

            df = df.merge(
                supplier_small,
                on="product_name",
                how="left",
                suffixes=("", "_supplier"),
            )

            for col in [
                "image_url",
                "store_name",
                "p_c_ratio",
                "growth_pct",
                "order_trend_score",
                "saturation",
                "top_country",
            ]:
                supplier_col = f"{col}_supplier"

                if col not in df.columns and supplier_col in df.columns:
                    df[col] = df[supplier_col]

                elif col in df.columns and supplier_col in df.columns:
                    df[col] = df[col].where(
                        df[col].astype(str).str.len() > 0,
                        df[supplier_col],
                    )

    if "image_url" not in df.columns:
        df["image_url"] = ""

    return df.fillna("")


def apply_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query.strip():
        return df

    query = query.lower().strip()

    searchable_columns = [
        "product_name",
        "category",
        "source_guess",
        "store_name",
        "risk_level",
        "next_action",
        "risk_notes",
        "saturation",
        "top_country",
    ]

    available = [col for col in searchable_columns if col in df.columns]

    mask = pd.Series(False, index=df.index)

    for col in available:
        mask = mask | df[col].astype(str).str.lower().str.contains(query, na=False)

    return df[mask]


def column_config():
    return {
        "image_url": st.column_config.ImageColumn(
            "Image",
            width="small",
            help="Product image captured from Zendrop.",
        ),
        "product_name": st.column_config.TextColumn("Product Name", width="large"),
        "supplier_url": st.column_config.LinkColumn("Supplier Link", display_text="Open"),
        "product_cost": st.column_config.NumberColumn("Cost", format="$%.2f"),
        "estimated_sale_price": st.column_config.NumberColumn("Est. Sale Price", format="$%.2f"),
        "estimated_profit": st.column_config.NumberColumn("Est. Profit", format="$%.2f"),
        "profit_margin_pct": st.column_config.NumberColumn("Margin %", format="%.2f%%"),
        "roi_pct": st.column_config.NumberColumn("ROI %", format="%.2f%%"),
        "p_c_ratio": st.column_config.NumberColumn("P/C", format="%.2fx"),
        "growth_pct": st.column_config.NumberColumn("Growth %", format="%.2f%%"),
    }


df = load_data()

st.title(APP_CONFIG["title"])
st.write(APP_CONFIG["subtitle"])

st.sidebar.header("Filters")

search_query = st.sidebar.text_input(
    "Search products",
    placeholder="speaker, shirt, pet, beauty, garden flag",
)

category_options = ["All"]
if "category" in df.columns:
    category_options += sorted([x for x in df["category"].astype(str).unique() if x])

selected_category = st.sidebar.selectbox("Category", category_options)

risk_options = ["All"]
if "risk_level" in df.columns:
    risk_options += sorted([x for x in df["risk_level"].astype(str).unique() if x])

selected_risk = st.sidebar.selectbox("Risk Level", risk_options)

action_options = ["All"]
if "next_action" in df.columns:
    action_options += sorted([x for x in df["next_action"].astype(str).unique() if x])

selected_action = st.sidebar.selectbox("Next Action", action_options)


filtered = apply_search(df, search_query)

if selected_category != "All" and "category" in filtered.columns:
    filtered = filtered[filtered["category"].astype(str) == selected_category]

if selected_risk != "All" and "risk_level" in filtered.columns:
    filtered = filtered[filtered["risk_level"].astype(str) == selected_risk]

if selected_action != "All" and "next_action" in filtered.columns:
    filtered = filtered[filtered["next_action"].astype(str) == selected_action]


total_products = len(df)
matching_products = len(filtered)
products_with_images = int(df["image_url"].astype(str).str.startswith("http").sum())

metric1, metric2, metric3 = st.columns(3)

with metric1:
    st.metric("Total Products", total_products)

with metric2:
    st.metric("Matching Products", matching_products)

with metric3:
    st.metric("Products With Images", products_with_images)


st.divider()

st.header("?? Best Products")

best_available = [col for col in DISPLAY_COLUMNS if col in filtered.columns]

if "final_score" in filtered.columns:
    best_products = filtered.sort_values("final_score", ascending=False).head(APP_CONFIG["top_product_count"])
else:
    best_products = filtered.head(APP_CONFIG["top_product_count"])

st.dataframe(
    best_products[best_available],
    use_container_width=True,
    hide_index=True,
    height=350,
    column_config=column_config(),
)

st.divider()

st.header("?? Full Product Ranking Table")

st.write(
    f"Showing **all {len(df)} products** from `output/opportunities.csv`. "
    "Sidebar filters only affect the Best Products section and search results, not this full table."
)

available_columns = [col for col in DISPLAY_COLUMNS if col in df.columns]

if "final_score" in df.columns:
    full_table = df.sort_values("final_score", ascending=False)
else:
    full_table = df.copy()

st.dataframe(
    full_table[available_columns],
    use_container_width=True,
    hide_index=True,
    height=1000,
    column_config=column_config(),
)

st.divider()

st.header("?? Search Results With Images")

st.write(f"Showing **{len(filtered)}** matching products.")

if "final_score" in filtered.columns:
    search_table = filtered.sort_values("final_score", ascending=False)
else:
    search_table = filtered.copy()

st.dataframe(
    search_table[best_available],
    use_container_width=True,
    hide_index=True,
    height=700,
    column_config=column_config(),
)


st.sidebar.divider()
st.sidebar.header("Terminology Guide")

for term, definition in TERM_DEFINITIONS.items():
    st.sidebar.markdown(f"**{term}:** {definition}")

st.sidebar.divider()
st.sidebar.header("How to Update")

st.sidebar.write(
    """
    1. Run `zendrop_smart_capture.py`.
    2. Stop with `Ctrl+C`.
    3. Copy smart capture to supplier file.
    4. Run scoring.
    5. Refresh dashboard.
    """
)
