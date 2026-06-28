from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st


# ============================================================
# FILE PATHS
# ============================================================

ZENDROP_PATH = Path("data/zendrop_smart_capture.csv")
DHGATE_CLEAN_PATH = Path("data/dhgate_clean_user_friendly.csv")
DHGATE_RAW_PATH = Path("data/dhgate_large_capture.csv")

OPPORTUNITIES_PATH = Path("output/opportunities.csv")
LAUNCH_SHORTLIST_PATH = Path("output/launch_shortlist.csv")
PRODUCT_TEST_PLAN_PATH = Path("output/product_test_plan.csv")
TEST_DECISIONS_PATH = Path("output/product_test_decisions.csv")


# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Dropship Product Research Board",
    page_icon="📦",
    layout="wide",
)


st.markdown(
    """
    <style>
    .stApp {
        background-color: #f5f6f8 !important;
        color: #111827 !important;
    }

    h1, h2, h3, h4, h5, h6, p, label, span, div {
        color: #111827 !important;
    }

    section[data-testid="stSidebar"] {
        background-color: #e5e7eb !important;
        border-right: 1px solid #d1d5db;
    }

    section[data-testid="stSidebar"] * {
        color: #111827 !important;
    }

    .stMetric {
        background: white !important;
        border: 1px solid #d1d5db !important;
        border-radius: 16px !important;
        padding: 14px !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }

    div[data-baseweb="select"] > div {
        background-color: #111827 !important;
        color: white !important;
        border-color: #374151 !important;
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

    input {
        color: #111827 !important;
    }

    .section-card {
        background: white;
        border: 1px solid #d1d5db;
        border-radius: 16px;
        padding: 16px;
        margin-bottom: 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }

    .small-muted {
        color: #6b7280 !important;
        font-size: 0.92rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# HELPERS
# ============================================================

def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path).fillna("").astype("object")


def clean_text(value) -> str:
    return str(value or "").strip()


def clean_number(value) -> float:
    text = str(value or "").replace("$", "").replace("%", "").replace(",", "").strip()

    try:
        return float(text)
    except Exception:
        return 0.0


def clean_number_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)


def add_missing_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        if col not in df.columns:
            df[col] = ""

    return df.fillna("")


def apply_search(df: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    if df.empty or not query.strip():
        return df

    query = query.lower().strip()
    mask = pd.Series(False, index=df.index)

    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.lower().str.contains(query, na=False)

    return df[mask]


def filter_selectbox(df: pd.DataFrame, col: str, label: str, key: str) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df

    options = ["All"] + sorted([x for x in df[col].astype(str).unique() if x])
    selected = st.selectbox(label, options, key=key)

    if selected == "All":
        return df

    return df[df[col].astype(str) == selected]


def column_config():
    return {
        "image_url": st.column_config.ImageColumn("Image", width="small"),
        "supplier_url": st.column_config.LinkColumn("Supplier Link", display_text="Open"),
        "clean_supplier_url": st.column_config.LinkColumn("Clean Link", display_text="Open"),
        "product_cost": st.column_config.NumberColumn("Cost", format="$%.2f"),
        "price_min": st.column_config.NumberColumn("Min Price", format="$%.2f"),
        "price_max": st.column_config.NumberColumn("Max Price", format="$%.2f"),
        "shipping_cost": st.column_config.NumberColumn("Shipping", format="$%.2f"),
        "estimated_sale_price": st.column_config.NumberColumn("Est. Sale Price", format="$%.2f"),
        "recommended_test_price": st.column_config.NumberColumn("Test Price", format="$%.2f"),
        "estimated_profit": st.column_config.NumberColumn("Est. Profit", format="$%.2f"),
        "profit_margin_pct": st.column_config.NumberColumn("Margin %", format="%.2f%%"),
        "roi_pct": st.column_config.NumberColumn("ROI %", format="%.2f%%"),
        "p_c_ratio": st.column_config.NumberColumn("P/C", format="%.2fx"),
        "growth_pct": st.column_config.NumberColumn("Growth %", format="%.2f%%"),
        "opportunity_score": st.column_config.NumberColumn("Opportunity Score", format="%.2f"),
        "final_score": st.column_config.NumberColumn("Final Score", format="%.2f"),
        "launch_score": st.column_config.NumberColumn("Launch Score", format="%.2f"),
        "dhgate_opportunity_score": st.column_config.NumberColumn("DHgate Score", format="%.2f"),
        "marketplace_score": st.column_config.NumberColumn("Marketplace Score", format="%.2f"),
        "combined_rank_score": st.column_config.NumberColumn("Combined Rank Score", format="%.2f"),
        "rating": st.column_config.NumberColumn("Rating", format="%.2f"),
        "reviews_count": st.column_config.NumberColumn("Reviews"),
        "sold_count": st.column_config.NumberColumn("Sold"),
    }


def sort_numeric(df: pd.DataFrame, col: str, ascending: bool = False) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df

    df = df.copy()
    df[col] = clean_number_series(df[col])
    return df.sort_values(col, ascending=ascending)


def show_missing_file(path: Path, command: str):
    st.warning(f"Missing `{path}`.")
    st.write("Run this first:")
    st.code(command, language="powershell")


# ============================================================
# LOAD DATA
# ============================================================

def load_opportunities() -> pd.DataFrame:
    return read_csv_safe(OPPORTUNITIES_PATH)


def load_zendrop() -> pd.DataFrame:
    df = read_csv_safe(ZENDROP_PATH)

    if df.empty:
        return df

    needed = [
        "source_site",
        "marketplace_source",
        "image_url",
        "product_name",
        "store_name",
        "category",
        "keyword",
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
        "first_seen_at",
        "last_seen_at",
        "supplier_url",
        "risk_level",
        "next_action",
        "risk_notes",
        "opportunity_score",
        "final_score",
    ]

    df = add_missing_columns(df, needed)

    df["source_site"] = "zendrop"
    df["marketplace_source"] = "ZENDROP"

    opp = load_opportunities()

    if not opp.empty and "product_name" in opp.columns:
        useful = [
            "product_name",
            "estimated_sale_price",
            "estimated_profit",
            "profit_margin_pct",
            "roi_pct",
            "opportunity_score",
            "final_score",
            "risk_level",
            "next_action",
            "risk_notes",
        ]

        useful = [col for col in useful if col in opp.columns]

        opp = opp[useful].drop_duplicates(subset=["product_name"])

        df = df.merge(opp, on="product_name", how="left", suffixes=("", "_opp"))

        for col in useful:
            extra = f"{col}_opp"

            if col != "product_name" and extra in df.columns:
                df[col] = df[col].where(df[col].astype(str).str.len() > 0, df[extra])

        df = df.drop(columns=[col for col in df.columns if col.endswith("_opp")])

    numeric_cols = [
        "product_cost",
        "estimated_sale_price",
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "p_c_ratio",
        "growth_pct",
        "order_trend_score",
        "opportunity_score",
        "final_score",
    ]

    for col in numeric_cols:
        df[col] = clean_number_series(df[col])

    return df.fillna("")


def load_dhgate() -> pd.DataFrame:
    if DHGATE_CLEAN_PATH.exists():
        df = read_csv_safe(DHGATE_CLEAN_PATH)
    else:
        df = read_csv_safe(DHGATE_RAW_PATH)

    if df.empty:
        return df

    needed = [
        "source_site",
        "marketplace_source",
        "next_action",
        "risk_level",
        "dhgate_opportunity_score",
        "marketplace_score",
        "image_url",
        "product_name",
        "category",
        "keyword",
        "product_cost",
        "price_min",
        "price_max",
        "shipping_cost",
        "estimated_sale_price",
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "rating",
        "reviews_count",
        "sold_count",
        "brand_risk",
        "brand_risk_notes",
        "shipping_risk",
        "shipping_risk_notes",
        "risk_notes",
        "supplier_url",
        "clean_supplier_url",
        "dhgate_product_id",
        "crawl_page",
        "crawl_keyword",
        "first_seen_at",
        "last_seen_at",
    ]

    df = add_missing_columns(df, needed)

    df["source_site"] = "dhgate"
    df["marketplace_source"] = "DHGATE"

    numeric_cols = [
        "dhgate_opportunity_score",
        "marketplace_score",
        "product_cost",
        "price_min",
        "price_max",
        "shipping_cost",
        "estimated_sale_price",
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "rating",
        "reviews_count",
        "sold_count",
        "crawl_page",
    ]

    for col in numeric_cols:
        df[col] = clean_number_series(df[col])

    return df.fillna("")


def normalize_zendrop_for_combined(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = pd.DataFrame()

    out["source_site"] = "zendrop"
    out["marketplace_source"] = "ZENDROP"
    out["image_url"] = df.get("image_url", "")
    out["product_name"] = df.get("product_name", "")
    out["category"] = df.get("category", "")
    out["product_cost"] = clean_number_series(df.get("product_cost", pd.Series([0] * len(df))))
    out["estimated_sale_price"] = clean_number_series(df.get("estimated_sale_price", pd.Series([0] * len(df))))
    out["estimated_profit"] = clean_number_series(df.get("estimated_profit", pd.Series([0] * len(df))))
    out["profit_margin_pct"] = clean_number_series(df.get("profit_margin_pct", pd.Series([0] * len(df))))
    out["roi_pct"] = clean_number_series(df.get("roi_pct", pd.Series([0] * len(df))))
    out["source_score"] = clean_number_series(df.get("final_score", pd.Series([0] * len(df))))
    out["growth_pct"] = clean_number_series(df.get("growth_pct", pd.Series([0] * len(df))))
    out["marketplace_score"] = clean_number_series(df.get("order_trend_score", pd.Series([0] * len(df))))
    out["risk_level"] = df.get("risk_level", "")
    out["next_action"] = df.get("next_action", "")
    out["risk_notes"] = df.get("risk_notes", "")
    out["supplier_url"] = df.get("supplier_url", "")
    out["first_seen_at"] = df.get("first_seen_at", "")
    out["extra_signal"] = "Growth/P/C"
    out["source_detail"] = df.get("store_name", "")

    return out.fillna("")


def normalize_dhgate_for_combined(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = pd.DataFrame()

    out["source_site"] = "dhgate"
    out["marketplace_source"] = "DHGATE"
    out["image_url"] = df.get("image_url", "")
    out["product_name"] = df.get("product_name", "")
    out["category"] = df.get("category", "")
    out["product_cost"] = clean_number_series(df.get("product_cost", pd.Series([0] * len(df))))
    out["estimated_sale_price"] = clean_number_series(df.get("estimated_sale_price", pd.Series([0] * len(df))))
    out["estimated_profit"] = clean_number_series(df.get("estimated_profit", pd.Series([0] * len(df))))
    out["profit_margin_pct"] = clean_number_series(df.get("profit_margin_pct", pd.Series([0] * len(df))))
    out["roi_pct"] = clean_number_series(df.get("roi_pct", pd.Series([0] * len(df))))
    out["source_score"] = clean_number_series(df.get("dhgate_opportunity_score", pd.Series([0] * len(df))))
    out["growth_pct"] = 0
    out["marketplace_score"] = clean_number_series(df.get("marketplace_score", pd.Series([0] * len(df))))
    out["risk_level"] = df.get("risk_level", "")
    out["next_action"] = df.get("next_action", "")
    out["risk_notes"] = df.get("risk_notes", "")
    out["supplier_url"] = df.get("supplier_url", "")
    out["first_seen_at"] = df.get("first_seen_at", "")
    out["extra_signal"] = "Reviews/Sold"
    out["source_detail"] = df.get("crawl_keyword", "")

    return out.fillna("")


def combined_rank_score(row) -> float:
    source_score = clean_number(row.get("source_score", 0))
    profit = clean_number(row.get("estimated_profit", 0))
    margin = clean_number(row.get("profit_margin_pct", 0))
    roi = clean_number(row.get("roi_pct", 0))
    cost = clean_number(row.get("product_cost", 0))
    marketplace = clean_number(row.get("marketplace_score", 0))
    action = clean_text(row.get("next_action", "")).upper()
    risk = clean_text(row.get("risk_level", "")).upper()
    image = clean_text(row.get("image_url", ""))
    url = clean_text(row.get("supplier_url", ""))

    score = 0.0

    score += min(max(source_score, 0), 100) * 0.40
    score += min(max(marketplace, 0), 100) * 0.15
    score += min(max(margin, 0), 80) * 0.15
    score += min(max(roi, 0), 200) * 0.05

    if profit >= 25:
        score += 15
    elif profit >= 15:
        score += 10
    elif profit >= 10:
        score += 7
    elif profit >= 5:
        score += 3

    if 5 <= cost <= 35:
        score += 8
    elif cost > 60:
        score -= 10

    if action == "TEST":
        score += 10
    elif action == "WATCH":
        score += 4
    elif action == "PASS":
        score -= 12

    if risk == "LOW":
        score += 8
    elif risk == "MEDIUM":
        score -= 2
    elif risk == "HIGH":
        score -= 25

    if image.startswith("http"):
        score += 4

    if url.startswith("http"):
        score += 4

    return round(max(min(score, 100), 0), 2)


def load_combined_products() -> pd.DataFrame:
    zendrop = normalize_zendrop_for_combined(load_zendrop())
    dhgate = normalize_dhgate_for_combined(load_dhgate())

    frames = [df for df in [zendrop, dhgate] if not df.empty]

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True).fillna("").astype("object")

    combined["combined_rank_score"] = combined.apply(combined_rank_score, axis=1)

    combined = combined.sort_values(
        by=["combined_rank_score", "estimated_profit", "profit_margin_pct"],
        ascending=[False, False, False],
    )

    return combined.fillna("")


def load_launch_shortlist() -> pd.DataFrame:
    return read_csv_safe(LAUNCH_SHORTLIST_PATH)


def load_test_plan() -> pd.DataFrame:
    plan = read_csv_safe(PRODUCT_TEST_PLAN_PATH)

    if plan.empty:
        return plan

    decisions = read_csv_safe(TEST_DECISIONS_PATH)

    if not decisions.empty and "product_name" in decisions.columns:
        plan = plan.merge(
            decisions,
            on="product_name",
            how="left",
            suffixes=("", "_saved"),
        )

        for col in [
            "test_decision",
            "test_status",
            "manual_priority",
            "chosen_niche",
            "competitor_notes",
            "page_notes",
            "creative_notes",
            "final_notes",
            "last_updated",
        ]:
            saved = f"{col}_saved"

            if saved in plan.columns:
                if col not in plan.columns:
                    plan[col] = plan[saved]
                else:
                    plan[col] = plan[col].where(plan[col].astype(str).str.len() > 0, plan[saved])

        plan = plan.drop(columns=[col for col in plan.columns if col.endswith("_saved")])

    needed = [
        "test_rank",
        "image_url",
        "product_name",
        "launch_tier",
        "launch_score",
        "product_cost",
        "recommended_test_price",
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "ideal_customer",
        "customer_pain_point",
        "product_page_angle",
        "ad_hook_1",
        "ad_hook_2",
        "ad_hook_3",
        "short_video_script",
        "test_budget",
        "pass_fail_rule",
        "risk_level",
        "risk_notes",
        "supplier_url",
        "test_decision",
        "test_status",
        "manual_priority",
        "chosen_niche",
        "competitor_notes",
        "page_notes",
        "creative_notes",
        "final_notes",
        "last_updated",
    ]

    return add_missing_columns(plan, needed)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("📦 Product Board")
st.sidebar.write("Clean view for ranking, comparing, and choosing products from Zendrop and DHgate.")

search_query = st.sidebar.text_input(
    "Search products",
    placeholder="soccer shirts, pet, home, beauty, car",
)

st.sidebar.divider()

st.sidebar.header("Quick Workflow")
st.sidebar.code(
    """
python .\\clean_dhgate_csv.py
python .\\combine_supplier_sources.py
python -m dropship_researcher.main
python .\\make_launch_shortlist.py
python .\\make_product_test_plan.py
streamlit run dashboard.py
""",
    language="powershell",
)

st.sidebar.divider()

st.sidebar.header("Decision Rules")
st.sidebar.markdown("**TEST:** Worth serious review.")
st.sidebar.markdown("**WATCH:** Possible, but needs manual checking.")
st.sidebar.markdown("**PASS:** Risky, weak profit, or bad signal.")
st.sidebar.markdown("**Top 50 Combined:** Best products from both sources ranked together.")


# ============================================================
# MAIN
# ============================================================

st.title("📦 Dropship Product Research Board")
st.caption("Zendrop and DHgate separated, with a clean Top 50 Combined section for quick decision-making.")

tab_top50, tab_combined, tab_zendrop, tab_dhgate, tab_shortlist, tab_testing = st.tabs(
    [
        "🏆 Top 50 Combined",
        "📊 Combined Board",
        "🟣 Zendrop",
        "🟠 DHgate",
        "🚀 Launch Shortlist",
        "🧪 Product Testing",
    ]
)


# ============================================================
# TOP 50 COMBINED
# ============================================================

with tab_top50:
    st.header("🏆 Top 50 Products Combined From Zendrop + DHgate")
    st.write("This is the main decision view. It ranks products from both sources using profit, margin, score, risk, image/link quality, and source-specific signals.")

    combined = load_combined_products()

    if combined.empty:
        show_missing_file(
            OPPORTUNITIES_PATH,
            "python .\\clean_dhgate_csv.py\npython -m dropship_researcher.main",
        )
    else:
        filtered = apply_search(
            combined,
            search_query,
            [
                "product_name",
                "category",
                "source_site",
                "marketplace_source",
                "risk_level",
                "next_action",
                "risk_notes",
                "source_detail",
            ],
        )

        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            st.metric("Combined Products", len(combined))

        with c2:
            st.metric("Top 50 View", min(50, len(filtered)))

        with c3:
            st.metric("Zendrop", int((combined["source_site"] == "zendrop").sum()))

        with c4:
            st.metric("DHgate", int((combined["source_site"] == "dhgate").sum()))

        with c5:
            avg_profit = clean_number_series(filtered["estimated_profit"]).head(50).mean()
            st.metric("Avg Top Profit", f"${avg_profit:.2f}")

        source_filter = st.selectbox(
            "Source filter",
            ["All", "zendrop", "dhgate"],
            key="top50_source_filter",
        )

        action_filter = st.selectbox(
            "Action filter",
            ["All", "TEST", "WATCH", "PASS", ""],
            key="top50_action_filter",
        )

        risk_filter = st.selectbox(
            "Risk filter",
            ["All", "LOW", "MEDIUM", "HIGH", ""],
            key="top50_risk_filter",
        )

        if source_filter != "All":
            filtered = filtered[filtered["source_site"].astype(str) == source_filter]

        if action_filter != "All":
            filtered = filtered[filtered["next_action"].astype(str) == action_filter]

        if risk_filter != "All":
            filtered = filtered[filtered["risk_level"].astype(str) == risk_filter]

        top50 = filtered.head(50).copy()

        top_cols = [
            "image_url",
            "combined_rank_score",
            "product_name",
            "source_site",
            "category",
            "next_action",
            "risk_level",
            "product_cost",
            "estimated_sale_price",
            "estimated_profit",
            "profit_margin_pct",
            "roi_pct",
            "source_score",
            "marketplace_score",
            "extra_signal",
            "source_detail",
            "risk_notes",
            "supplier_url",
        ]

        top_cols = [col for col in top_cols if col in top50.columns]

        st.subheader("Best 50 Products To Review First")

        st.dataframe(
            top50[top_cols],
            use_container_width=True,
            hide_index=True,
            height=900,
            column_config=column_config(),
        )

        st.subheader("Quick Review: Top 5")

        for i, row in top50.head(5).iterrows():
            with st.expander(f"#{len(top50.loc[:i])} — {row.get('product_name', '')}"):
                col_img, col_info = st.columns([1, 3])

                with col_img:
                    image_url = clean_text(row.get("image_url", ""))

                    if image_url.startswith("http"):
                        st.image(image_url, use_container_width=True)
                    else:
                        st.write("No image")

                with col_info:
                    st.markdown(f"**Source:** {row.get('marketplace_source', '')}")
                    st.markdown(f"**Action:** {row.get('next_action', '')}")
                    st.markdown(f"**Risk:** {row.get('risk_level', '')}")
                    st.markdown(f"**Score:** {row.get('combined_rank_score', '')}")
                    st.markdown(f"**Cost:** ${clean_number(row.get('product_cost', 0)):.2f}")
                    st.markdown(f"**Estimated Sale Price:** ${clean_number(row.get('estimated_sale_price', 0)):.2f}")
                    st.markdown(f"**Estimated Profit:** ${clean_number(row.get('estimated_profit', 0)):.2f}")
                    st.markdown(f"**Margin:** {clean_number(row.get('profit_margin_pct', 0)):.2f}%")
                    st.markdown(f"**Notes:** {row.get('risk_notes', '')}")
                    st.markdown(f"**Supplier URL:** {row.get('supplier_url', '')}")


# ============================================================
# COMBINED BOARD
# ============================================================

with tab_combined:
    st.header("📊 Full Combined Board")

    combined = load_combined_products()

    if combined.empty:
        show_missing_file(
            OPPORTUNITIES_PATH,
            "python .\\clean_dhgate_csv.py\npython -m dropship_researcher.main",
        )
    else:
        combined = apply_search(
            combined,
            search_query,
            [
                "product_name",
                "category",
                "source_site",
                "marketplace_source",
                "risk_level",
                "next_action",
                "risk_notes",
                "source_detail",
            ],
        )

        combined = filter_selectbox(combined, "source_site", "Source", "combined_source")
        combined = filter_selectbox(combined, "next_action", "Action", "combined_action")
        combined = filter_selectbox(combined, "risk_level", "Risk", "combined_risk")

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Products", len(combined))

        with c2:
            st.metric("TEST", int((combined["next_action"].astype(str) == "TEST").sum()))

        with c3:
            st.metric("WATCH", int((combined["next_action"].astype(str) == "WATCH").sum()))

        with c4:
            st.metric("PASS", int((combined["next_action"].astype(str) == "PASS").sum()))

        cols = [
            "image_url",
            "combined_rank_score",
            "product_name",
            "source_site",
            "category",
            "next_action",
            "risk_level",
            "product_cost",
            "estimated_sale_price",
            "estimated_profit",
            "profit_margin_pct",
            "roi_pct",
            "source_score",
            "marketplace_score",
            "risk_notes",
            "supplier_url",
        ]

        cols = [col for col in cols if col in combined.columns]

        st.dataframe(
            combined[cols],
            use_container_width=True,
            hide_index=True,
            height=950,
            column_config=column_config(),
        )


# ============================================================
# ZENDROP TAB
# ============================================================

with tab_zendrop:
    st.header("🟣 Zendrop Products")

    zendrop = load_zendrop()

    if zendrop.empty:
        show_missing_file(
            ZENDROP_PATH,
            "python .\\zendrop_smart_capture.py",
        )
    else:
        zendrop = apply_search(
            zendrop,
            search_query,
            [
                "product_name",
                "store_name",
                "category",
                "keyword",
                "saturation",
                "top_country",
            ],
        )

        zendrop = filter_selectbox(zendrop, "category", "Category", "zendrop_category")
        zendrop = filter_selectbox(zendrop, "saturation", "Saturation", "zendrop_saturation")

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Zendrop Products", len(zendrop))

        with c2:
            st.metric("With Images", int(zendrop["image_url"].astype(str).str.startswith("http").sum()))

        with c3:
            st.metric("Avg Cost", f"${clean_number_series(zendrop['product_cost']).mean():.2f}")

        with c4:
            st.metric("Avg Growth", f"{clean_number_series(zendrop['growth_pct']).mean():.1f}%")

        cols = [
            "image_url",
            "product_name",
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
            "first_seen_at",
            "last_seen_at",
            "supplier_url",
        ]

        cols = [col for col in cols if col in zendrop.columns]

        zendrop_sorted = sort_numeric(zendrop, "growth_pct", ascending=False)

        st.dataframe(
            zendrop_sorted[cols],
            use_container_width=True,
            hide_index=True,
            height=950,
            column_config=column_config(),
        )


# ============================================================
# DHGATE TAB
# ============================================================

with tab_dhgate:
    st.header("🟠 DHgate Products")

    dhgate = load_dhgate()

    if dhgate.empty:
        show_missing_file(
            DHGATE_CLEAN_PATH,
            "python .\\clean_dhgate_csv.py",
        )
    else:
        dhgate = apply_search(
            dhgate,
            search_query,
            [
                "product_name",
                "category",
                "keyword",
                "crawl_keyword",
                "next_action",
                "risk_level",
                "risk_notes",
                "brand_risk",
                "shipping_risk",
            ],
        )

        dhgate = filter_selectbox(dhgate, "next_action", "Action", "dhgate_action")
        dhgate = filter_selectbox(dhgate, "risk_level", "Risk", "dhgate_risk")
        dhgate = filter_selectbox(dhgate, "crawl_keyword", "Crawl Keyword", "dhgate_keyword")

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("DHgate Products", len(dhgate))

        with c2:
            st.metric("TEST", int((dhgate["next_action"].astype(str) == "TEST").sum()))

        with c3:
            st.metric("WATCH", int((dhgate["next_action"].astype(str) == "WATCH").sum()))

        with c4:
            st.metric("PASS", int((dhgate["next_action"].astype(str) == "PASS").sum()))

        cols = [
            "image_url",
            "next_action",
            "risk_level",
            "dhgate_opportunity_score",
            "marketplace_score",
            "product_name",
            "category",
            "keyword",
            "product_cost",
            "price_min",
            "price_max",
            "shipping_cost",
            "estimated_sale_price",
            "estimated_profit",
            "profit_margin_pct",
            "roi_pct",
            "rating",
            "reviews_count",
            "sold_count",
            "brand_risk",
            "shipping_risk",
            "risk_notes",
            "supplier_url",
            "dhgate_product_id",
            "crawl_page",
            "crawl_keyword",
        ]

        cols = [col for col in cols if col in dhgate.columns]

        dhgate_sorted = sort_numeric(dhgate, "dhgate_opportunity_score", ascending=False)

        st.dataframe(
            dhgate_sorted[cols],
            use_container_width=True,
            hide_index=True,
            height=950,
            column_config=column_config(),
        )


# ============================================================
# LAUNCH SHORTLIST TAB
# ============================================================

with tab_shortlist:
    st.header("🚀 Launch Shortlist")

    shortlist = load_launch_shortlist()

    if shortlist.empty:
        show_missing_file(
            LAUNCH_SHORTLIST_PATH,
            "python .\\make_launch_shortlist.py",
        )
    else:
        shortlist = apply_search(
            shortlist,
            search_query,
            [
                "product_name",
                "launch_tier",
                "category",
                "ad_angle",
                "launch_next_step",
                "risk_level",
                "risk_notes",
                "source_site",
                "marketplace_source",
            ],
        )

        shortlist = filter_selectbox(shortlist, "launch_tier", "Launch Tier", "shortlist_tier")
        shortlist = filter_selectbox(shortlist, "source_site", "Source", "shortlist_source")

        shortlist = sort_numeric(shortlist, "launch_score", ascending=False)

        cols = [
            "image_url",
            "product_name",
            "source_site",
            "marketplace_source",
            "launch_tier",
            "launch_score",
            "ad_angle",
            "launch_next_step",
            "category",
            "product_cost",
            "estimated_sale_price",
            "estimated_profit",
            "profit_margin_pct",
            "roi_pct",
            "risk_level",
            "risk_notes",
            "supplier_url",
        ]

        cols = [col for col in cols if col in shortlist.columns]

        st.dataframe(
            shortlist[cols],
            use_container_width=True,
            hide_index=True,
            height=950,
            column_config=column_config(),
        )


# ============================================================
# PRODUCT TESTING TAB
# ============================================================

with tab_testing:
    st.header("🧪 Product Testing Dashboard")

    test_plan = load_test_plan()

    if test_plan.empty:
        show_missing_file(
            PRODUCT_TEST_PLAN_PATH,
            "python .\\make_product_test_plan.py",
        )
    else:
        test_plan = apply_search(
            test_plan,
            search_query,
            [
                "product_name",
                "launch_tier",
                "ideal_customer",
                "customer_pain_point",
                "product_page_angle",
                "ad_hook_1",
                "ad_hook_2",
                "ad_hook_3",
                "risk_level",
                "risk_notes",
                "test_decision",
                "test_status",
                "chosen_niche",
            ],
        )

        decision_filter = st.selectbox(
            "Test Decision",
            ["All", "TEST", "MAYBE", "PASS", "SAMPLE FIRST", ""],
            key="testing_decision_filter",
        )

        status_filter = st.selectbox(
            "Test Status",
            [
                "All",
                "NOT STARTED",
                "PAGE NEEDED",
                "CREATIVE NEEDED",
                "READY TO TEST",
                "TESTING",
                "KILL",
                "IMPROVE",
                "SCALE CAREFULLY",
                "",
            ],
            key="testing_status_filter",
        )

        if decision_filter != "All":
            test_plan = test_plan[test_plan["test_decision"].astype(str) == decision_filter]

        if status_filter != "All":
            test_plan = test_plan[test_plan["test_status"].astype(str) == status_filter]

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Products", len(test_plan))

        with c2:
            st.metric("Marked TEST", int((test_plan["test_decision"].astype(str) == "TEST").sum()))

        with c3:
            st.metric("Sample First", int((test_plan["test_decision"].astype(str) == "SAMPLE FIRST").sum()))

        with c4:
            st.metric(
                "Ready/Testing",
                int(test_plan["test_status"].astype(str).isin(["READY TO TEST", "TESTING"]).sum()),
            )

        cols = [
            "test_rank",
            "image_url",
            "product_name",
            "launch_tier",
            "launch_score",
            "product_cost",
            "recommended_test_price",
            "estimated_profit",
            "profit_margin_pct",
            "roi_pct",
            "ideal_customer",
            "customer_pain_point",
            "product_page_angle",
            "ad_hook_1",
            "ad_hook_2",
            "ad_hook_3",
            "short_video_script",
            "test_budget",
            "pass_fail_rule",
            "risk_level",
            "risk_notes",
            "test_decision",
            "test_status",
            "manual_priority",
            "chosen_niche",
            "competitor_notes",
            "page_notes",
            "creative_notes",
            "final_notes",
            "supplier_url",
        ]

        cols = [col for col in cols if col in test_plan.columns]

        test_plan = sort_numeric(test_plan, "test_rank", ascending=True)

        edited = st.data_editor(
            test_plan[cols],
            use_container_width=True,
            hide_index=True,
            height=950,
            column_config={
                **column_config(),
                "test_decision": st.column_config.SelectboxColumn(
                    "Test Decision",
                    options=["", "TEST", "MAYBE", "PASS", "SAMPLE FIRST"],
                ),
                "test_status": st.column_config.SelectboxColumn(
                    "Test Status",
                    options=[
                        "",
                        "NOT STARTED",
                        "PAGE NEEDED",
                        "CREATIVE NEEDED",
                        "READY TO TEST",
                        "TESTING",
                        "KILL",
                        "IMPROVE",
                        "SCALE CAREFULLY",
                    ],
                ),
                "manual_priority": st.column_config.SelectboxColumn(
                    "Manual Priority",
                    options=["", "1 - Highest", "2 - Strong", "3 - Maybe", "4 - Low"],
                ),
            },
            disabled=[
                "test_rank",
                "image_url",
                "product_name",
                "launch_tier",
                "launch_score",
                "product_cost",
                "recommended_test_price",
                "estimated_profit",
                "profit_margin_pct",
                "roi_pct",
                "ideal_customer",
                "customer_pain_point",
                "product_page_angle",
                "ad_hook_1",
                "ad_hook_2",
                "ad_hook_3",
                "short_video_script",
                "test_budget",
                "pass_fail_rule",
                "risk_level",
                "risk_notes",
                "supplier_url",
            ],
        )

        if st.button("💾 Save Product Testing Decisions"):
            save_cols = [
                "product_name",
                "test_decision",
                "test_status",
                "manual_priority",
                "chosen_niche",
                "competitor_notes",
                "page_notes",
                "creative_notes",
                "final_notes",
            ]

            save_df = edited.copy()
            save_df["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            save_cols = [col for col in save_cols if col in save_df.columns] + ["last_updated"]

            TEST_DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
            save_df[save_cols].to_csv(TEST_DECISIONS_PATH, index=False)

            st.success(f"Saved decisions to `{TEST_DECISIONS_PATH}`.")
