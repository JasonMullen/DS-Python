
from pathlib import Path

import pandas as pd
import streamlit as st


OPPORTUNITIES_PATH = Path("output/opportunities.csv")
SUPPLIER_PATH = Path("data/supplier_products.csv")


st.set_page_config(
    page_title="Dropship Product Research Board",
    page_icon="??",
    layout="wide",
)


st.markdown(
    """
    <style>
    .stApp {
        background-color: #f3f4f6;
        color: #111827;
    }

    h1, h2, h3, h4, h5, h6, p, label, span, div {
        color: #111827;
    }

    section[data-testid="stSidebar"] {
        background-color: #e5e7eb;
    }

    .metric-card {
        background: white;
        border: 1px solid #d1d5db;
        border-radius: 14px;
        padding: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_data() -> pd.DataFrame:
    if not OPPORTUNITIES_PATH.exists():
        st.error("Missing output/opportunities.csv. Run: python -m dropship_researcher.main")
        st.stop()

    df = pd.read_csv(OPPORTUNITIES_PATH).fillna("")

    # If image_url did not make it into output/opportunities.csv,
    # merge it back in from data/supplier_products.csv.
    if SUPPLIER_PATH.exists():
        supplier_df = pd.read_csv(SUPPLIER_PATH).fillna("")

        useful_supplier_cols = [
            "product_name",
            "image_url",
            "store_name",
            "p_c_ratio",
            "growth_pct",
            "order_trend_score",
            "saturation",
            "top_country",
        ]

        useful_supplier_cols = [
            col for col in useful_supplier_cols if col in supplier_df.columns
        ]

        if "product_name" in useful_supplier_cols:
            supplier_small = supplier_df[useful_supplier_cols].drop_duplicates(
                subset=["product_name"]
            )

            df = df.merge(
                supplier_small,
                on="product_name",
                how="left",
                suffixes=("", "_supplier"),
            )

            # Fill missing columns from supplier version.
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
                    df[col] = df[col].where(df[col].astype(str).str.len() > 0, df[supplier_col])

    if "image_url" not in df.columns:
        df["image_url"] = ""

    return df.fillna("")


def search_products(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query.strip():
        return df

    query = query.lower().strip()

    searchable_columns = [
        "product_name",
        "category",
        "source_guess",
        "risk_level",
        "next_action",
        "risk_notes",
        "store_name",
        "saturation",
        "top_country",
    ]

    available = [col for col in searchable_columns if col in df.columns]

    mask = pd.Series(False, index=df.index)

    for col in available:
        mask = mask | df[col].astype(str).str.lower().str.contains(query, na=False)

    return df[mask]


df = load_data()

st.title("?? Dropship Product Research Board")
st.write("Search products, view images, compare profit, and decide what to test next.")

st.sidebar.header("Filters")

search_query = st.sidebar.text_input(
    "Search product board",
    placeholder="Example: speaker, shirt, pet, beauty, garden flag",
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


filtered_df = search_products(df, search_query)

if selected_category != "All" and "category" in filtered_df.columns:
    filtered_df = filtered_df[filtered_df["category"].astype(str) == selected_category]

if selected_risk != "All" and "risk_level" in filtered_df.columns:
    filtered_df = filtered_df[filtered_df["risk_level"].astype(str) == selected_risk]

if selected_action != "All" and "next_action" in filtered_df.columns:
    filtered_df = filtered_df[filtered_df["next_action"].astype(str) == selected_action]


total_products = len(df)
visible_products = len(filtered_df)
products_with_images = int(df["image_url"].astype(str).str.startswith("http").sum())

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Total products saved", total_products)

with col2:
    st.metric("Products matching search", visible_products)

with col3:
    st.metric("Products with images", products_with_images)


st.divider()

st.header("?? Product Search Results")

st.write(
    f"Showing **{visible_products}** products. "
    "Use the sidebar search to find products by name, category, risk, action, or supplier."
)

display_columns = [
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

available_columns = [col for col in display_columns if col in filtered_df.columns]

sort_col = "final_score" if "final_score" in filtered_df.columns else None

if sort_col:
    shown_df = filtered_df.sort_values(sort_col, ascending=False)
else:
    shown_df = filtered_df.copy()

st.dataframe(
    shown_df[available_columns],
    use_container_width=True,
    hide_index=True,
    height=850,
    column_config={
        "image_url": st.column_config.ImageColumn(
            "Product Image",
            width="medium",
            help="Captured from Zendrop product card/detail page.",
        ),
        "product_name": st.column_config.TextColumn(
            "Product Name",
            width="large",
        ),
        "supplier_url": st.column_config.LinkColumn(
            "Zendrop/Search URL",
            display_text="Open",
        ),
        "product_cost": st.column_config.NumberColumn(
            "Cost",
            format="$%.2f",
        ),
        "estimated_sale_price": st.column_config.NumberColumn(
            "Est. Sale Price",
            format="$%.2f",
        ),
        "estimated_profit": st.column_config.NumberColumn(
            "Est. Profit",
            format="$%.2f",
        ),
        "profit_margin_pct": st.column_config.NumberColumn(
            "Margin %",
            format="%.2f%%",
        ),
        "roi_pct": st.column_config.NumberColumn(
            "ROI %",
            format="%.2f%%",
        ),
        "growth_pct": st.column_config.NumberColumn(
            "Growth %",
            format="%.2f%%",
        ),
        "p_c_ratio": st.column_config.NumberColumn(
            "P/C",
            format="%.2fx",
        ),
    },
)


st.divider()

st.header("?? Full Board")

st.write(f"Full board contains **{len(df)}** products.")

full_available_columns = [col for col in display_columns if col in df.columns]

if sort_col:
    full_df = df.sort_values(sort_col, ascending=False)
else:
    full_df = df.copy()

st.dataframe(
    full_df[full_available_columns],
    use_container_width=True,
    hide_index=True,
    height=1000,
    column_config={
        "image_url": st.column_config.ImageColumn("Product Image", width="medium"),
        "supplier_url": st.column_config.LinkColumn("Zendrop/Search URL", display_text="Open"),
        "product_cost": st.column_config.NumberColumn("Cost", format="$%.2f"),
        "estimated_sale_price": st.column_config.NumberColumn("Est. Sale Price", format="$%.2f"),
        "estimated_profit": st.column_config.NumberColumn("Est. Profit", format="$%.2f"),
        "profit_margin_pct": st.column_config.NumberColumn("Margin %", format="%.2f%%"),
        "roi_pct": st.column_config.NumberColumn("ROI %", format="%.2f%%"),
        "growth_pct": st.column_config.NumberColumn("Growth %", format="%.2f%%"),
        "p_c_ratio": st.column_config.NumberColumn("P/C", format="%.2fx"),
    },
)


st.sidebar.divider()
st.sidebar.header("How to Update")
st.sidebar.write(
    """
    1. Run `zendrop_smart_capture.py`.
    2. Stop with `Ctrl+C`.
    3. Copy smart capture to supplier file.
    4. Run scoring.
    5. Refresh this dashboard.
    """
)
