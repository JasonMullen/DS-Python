from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st


VERIFICATION_PATH = Path("output/all_products_verification.csv")


st.set_page_config(
    page_title="Product Verification Board",
    page_icon="✅",
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

    div[data-baseweb="select"] > div {
        background-color: #111827 !important;
        color: white !important;
    }

    div[data-baseweb="select"] span {
        color: white !important;
    }

    div[data-baseweb="popover"] * {
        color: white !important;
    }

    ul[role="listbox"], li[role="option"] {
        background-color: #111827 !important;
        color: white !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data():
    if not VERIFICATION_PATH.exists():
        st.error("Missing output/all_products_verification.csv. Run make_full_verification_queue.py first.")
        st.stop()

    return pd.read_csv(VERIFICATION_PATH).fillna("")


def save_data(df):
    df.to_csv(VERIFICATION_PATH, index=False)


def apply_search(df, query):
    if not query.strip():
        return df

    query = query.lower().strip()

    searchable_cols = [
        "product_name",
        "category",
        "store_name",
        "risk_level",
        "next_action",
        "risk_notes",
        "zendrop_search_1",
        "zendrop_search_2",
        "zendrop_search_3",
        "verification_status",
        "verified_decision",
        "verification_notes",
    ]

    available = [col for col in searchable_cols if col in df.columns]

    mask = pd.Series(False, index=df.index)

    for col in available:
        mask = mask | df[col].astype(str).str.lower().str.contains(query, na=False)

    return df[mask]


df = load_data()

st.title("✅ Full Product Verification Board")
st.write("Verify every scraped product with images, Zendrop search terms, real costs, and final decision.")

st.sidebar.header("Filters")

search_query = st.sidebar.text_input(
    "Search products",
    placeholder="shirt, speaker, pet, beauty, garden flag",
)

status_options = ["All"]
if "verification_status" in df.columns:
    status_options += sorted([x for x in df["verification_status"].astype(str).unique() if x])

selected_status = st.sidebar.selectbox("Verification Status", status_options)

category_options = ["All"]
if "category" in df.columns:
    category_options += sorted([x for x in df["category"].astype(str).unique() if x])

selected_category = st.sidebar.selectbox("Category", category_options)

risk_options = ["All"]
if "risk_level" in df.columns:
    risk_options += sorted([x for x in df["risk_level"].astype(str).unique() if x])

selected_risk = st.sidebar.selectbox("Risk Level", risk_options)

decision_options = ["All"]
if "verified_decision" in df.columns:
    decision_options += sorted([x for x in df["verified_decision"].astype(str).unique() if x])

selected_decision = st.sidebar.selectbox("Verified Decision", decision_options)


filtered = apply_search(df, search_query)

 if_filter_status = selected_status != "All" and "verification_status" in filtered.columns
if if_filter_status:
    filtered = filtered[filtered["verification_status"].astype(str) == selected_status]

if selected_category != "All" and "category" in filtered.columns:
    filtered = filtered[filtered["category"].astype(str) == selected_category]

if selected_risk != "All" and "risk_level" in filtered.columns:
    filtered = filtered[filtered["risk_level"].astype(str) == selected_risk]

if selected_decision != "All" and "verified_decision" in filtered.columns:
    filtered = filtered[filtered["verified_decision"].astype(str) == selected_decision]


total = len(df)
verified = int((df["verification_status"].astype(str) == "VERIFIED").sum()) if "verification_status" in df.columns else 0
needs_check = int((df["verification_status"].astype(str) == "NEEDS CHECK").sum()) if "verification_status" in df.columns else 0
visible = len(filtered)

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("Total Products", total)

with c2:
    st.metric("Verified", verified)

with c3:
    st.metric("Needs Check", needs_check)

with c4:
    st.metric("Visible Now", visible)


st.divider()

st.header("Editable Verification Table")

st.write(
    "Edit the verification columns directly, then click **Save Verification Updates**."
)

display_cols = [
    "verification_id",
    "image_url",
    "product_name",
    "category",
    "product_cost",
    "p_c_ratio",
    "growth_pct",
    "estimated_sale_price",
    "estimated_profit",
    "profit_margin_pct",
    "roi_pct",
    "final_score",
    "risk_level",
    "next_action",
    "risk_notes",
    "supplier_url",
    "zendrop_search_1",
    "zendrop_search_2",
    "zendrop_search_3",
    "verification_status",
    "exact_match_found",
    "exact_product_url",
    "real_product_cost",
    "real_shipping_cost",
    "real_total_cost",
    "realistic_sale_price",
    "realistic_profit",
    "verified_decision",
    "verified_at",
    "verification_notes",
]

available_cols = [col for col in display_cols if col in filtered.columns]

if "final_score" in filtered.columns:
    filtered = filtered.sort_values("final_score", ascending=False)

edited = st.data_editor(
    filtered[available_cols],
    use_container_width=True,
    hide_index=True,
    height=850,
    column_config={
        "image_url": st.column_config.ImageColumn("Image", width="small"),
        "supplier_url": st.column_config.LinkColumn("Captured URL", display_text="Open"),
        "exact_product_url": st.column_config.LinkColumn("Exact Product URL", display_text="Open"),
        "verification_status": st.column_config.SelectboxColumn(
            "Verification Status",
            options=["NEEDS CHECK", "VERIFIED", "NO MATCH", "DUPLICATE", "REJECTED"],
        ),
        "exact_match_found": st.column_config.SelectboxColumn(
            "Exact Match?",
            options=["", "YES", "NO", "MAYBE"],
        ),
        "verified_decision": st.column_config.SelectboxColumn(
            "Verified Decision",
            options=["", "TEST", "WATCH", "PASS"],
        ),
        "product_cost": st.column_config.NumberColumn("Captured Cost", format="$%.2f"),
        "estimated_sale_price": st.column_config.NumberColumn("Est. Sale Price", format="$%.2f"),
        "estimated_profit": st.column_config.NumberColumn("Est. Profit", format="$%.2f"),
        "real_product_cost": st.column_config.NumberColumn("Real Product Cost", format="$%.2f"),
        "real_shipping_cost": st.column_config.NumberColumn("Real Shipping Cost", format="$%.2f"),
        "real_total_cost": st.column_config.NumberColumn("Real Total Cost", format="$%.2f"),
        "realistic_sale_price": st.column_config.NumberColumn("Realistic Sale Price", format="$%.2f"),
        "realistic_profit": st.column_config.NumberColumn("Realistic Profit", format="$%.2f"),
    },
    disabled=[
        "verification_id",
        "image_url",
        "product_name",
        "category",
        "product_cost",
        "p_c_ratio",
        "growth_pct",
        "estimated_sale_price",
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "final_score",
        "risk_level",
        "next_action",
        "risk_notes",
        "supplier_url",
        "zendrop_search_1",
        "zendrop_search_2",
        "zendrop_search_3",
    ],
)


if st.button("💾 Save Verification Updates"):
    full_df = df.copy()

    editable_cols = [
        "verification_status",
        "exact_match_found",
        "exact_product_url",
        "real_product_cost",
        "real_shipping_cost",
        "real_total_cost",
        "realistic_sale_price",
        "realistic_profit",
        "verified_decision",
        "verified_at",
        "verification_notes",
    ]

    for _, row in edited.iterrows():
        verification_id = row["verification_id"]

        mask = full_df["verification_id"].astype(str) == str(verification_id)

        for col in editable_cols:
            if col in full_df.columns and col in edited.columns:
                full_df.loc[mask, col] = row[col]

        if "verification_status" in edited.columns:
            if row["verification_status"] == "VERIFIED":
                full_df.loc[mask, "verified_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    save_data(full_df)
    st.cache_data.clear()
    st.success("Verification updates saved. Refresh the page to reload saved data.")


st.sidebar.divider()
st.sidebar.header("Verification Workflow")
st.sidebar.write(
    """
    1. Use the image and product name.
    2. Search Zendrop using Search 1, 2, then 3.
    3. Confirm if it is the exact product.
    4. Enter real product cost and shipping.
    5. Mark TEST, WATCH, or PASS.
    6. Save updates.
    """
)
