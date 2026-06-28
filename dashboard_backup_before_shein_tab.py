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
        min-height: 44px !important;
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

    .tab-subtitle {
        color: #6b7280 !important;
        font-size: 0.95rem;
        margin-bottom: 1rem;
    }

    .block-container {
        padding-top: 1.5rem;
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


def safe_col(df: pd.DataFrame, col: str, default="") -> pd.Series:
    if col in df.columns:
        return df[col]

    return pd.Series([default] * len(df), index=df.index)


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


def show_missing_file(path: Path, command: str):
    st.warning(f"Missing `{path}`.")
    st.write("Run this first:")
    st.code(command, language="powershell")


def sort_numeric(df: pd.DataFrame, col: str, ascending: bool = False) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df

    df = df.copy()
    df[col] = clean_number_series(df[col])
    return df.sort_values(col, ascending=ascending)


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


def tab_header(icon: str, title: str, subtitle: str):
    st.header(f"{icon} {title}")
    st.markdown(f"<p class='tab-subtitle'>{subtitle}</p>", unsafe_allow_html=True)


def metric_row(metrics: list[tuple[str, str | int | float]]):
    cols = st.columns(len(metrics))

    for col, item in zip(cols, metrics):
        label, value = item

        with col:
            st.metric(label, value)


def download_current_view(df: pd.DataFrame, filename: str):
    if df.empty:
        return

    st.download_button(
        label="⬇️ Download Current View",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
    )


def render_table(df: pd.DataFrame, cols: list[str], height: int = 850):
    cols = [col for col in cols if col in df.columns]

    if not cols:
        st.warning("No display columns found.")
        return

    st.dataframe(
        df[cols],
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config=column_config(),
    )


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
        "shipping_risk",
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

    out = pd.DataFrame(index=df.index)

    out["source_site"] = "zendrop"
    out["marketplace_source"] = "ZENDROP"
    out["image_url"] = safe_col(df, "image_url")
    out["product_name"] = safe_col(df, "product_name")
    out["category"] = safe_col(df, "category")
    out["product_cost"] = clean_number_series(safe_col(df, "product_cost", 0))
    out["estimated_sale_price"] = clean_number_series(safe_col(df, "estimated_sale_price", 0))
    out["estimated_profit"] = clean_number_series(safe_col(df, "estimated_profit", 0))
    out["profit_margin_pct"] = clean_number_series(safe_col(df, "profit_margin_pct", 0))
    out["roi_pct"] = clean_number_series(safe_col(df, "roi_pct", 0))
    out["source_score"] = clean_number_series(safe_col(df, "final_score", 0))
    out["growth_pct"] = clean_number_series(safe_col(df, "growth_pct", 0))
    out["marketplace_score"] = clean_number_series(safe_col(df, "order_trend_score", 0))
    out["risk_level"] = safe_col(df, "risk_level")
    out["next_action"] = safe_col(df, "next_action")
    out["risk_notes"] = safe_col(df, "risk_notes")
    out["supplier_url"] = safe_col(df, "supplier_url")
    out["first_seen_at"] = safe_col(df, "first_seen_at")
    out["extra_signal"] = "Growth/P-C"
    out["source_detail"] = safe_col(df, "store_name")

    return out.fillna("")


def normalize_dhgate_for_combined(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = pd.DataFrame(index=df.index)

    out["source_site"] = "dhgate"
    out["marketplace_source"] = "DHGATE"
    out["image_url"] = safe_col(df, "image_url")
    out["product_name"] = safe_col(df, "product_name")
    out["category"] = safe_col(df, "category")
    out["product_cost"] = clean_number_series(safe_col(df, "product_cost", 0))
    out["estimated_sale_price"] = clean_number_series(safe_col(df, "estimated_sale_price", 0))
    out["estimated_profit"] = clean_number_series(safe_col(df, "estimated_profit", 0))
    out["profit_margin_pct"] = clean_number_series(safe_col(df, "profit_margin_pct", 0))
    out["roi_pct"] = clean_number_series(safe_col(df, "roi_pct", 0))
    out["source_score"] = clean_number_series(safe_col(df, "dhgate_opportunity_score", 0))
    out["growth_pct"] = 0
    out["marketplace_score"] = clean_number_series(safe_col(df, "marketplace_score", 0))
    out["risk_level"] = safe_col(df, "risk_level")
    out["next_action"] = safe_col(df, "next_action")
    out["risk_notes"] = safe_col(df, "risk_notes")
    out["supplier_url"] = safe_col(df, "supplier_url")
    out["first_seen_at"] = safe_col(df, "first_seen_at")
    out["extra_signal"] = "Reviews/Sold"
    out["source_detail"] = safe_col(df, "crawl_keyword")

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
st.sidebar.write("Clean layout across every tab.")

search_query = st.sidebar.text_input(
    "Search products",
    placeholder="soccer shirts, pet, home, beauty, car",
)

st.sidebar.divider()

st.sidebar.header("Update Workflow")
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

st.sidebar.header("Tab Layout")
st.sidebar.markdown("**1. Title**")
st.sidebar.markdown("**2. Filters**")
st.sidebar.markdown("**3. Metric cards**")
st.sidebar.markdown("**4. Product table**")


# ============================================================
# MAIN APP
# ============================================================

st.title("📦 Dropship Product Research Board")
st.caption("Zendrop and DHgate separated, with clean filters, metrics, and product tables on every tab.")

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
# TOP 50 TAB
# ============================================================

with tab_top50:
    tab_header(
        "🏆",
        "Top 50 Combined Products",
        "Best products from Zendrop and DHgate ranked together for quick review.",
    )

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

        f1, f2, f3 = st.columns(3)

        with f1:
            filtered = filter_selectbox(filtered, "source_site", "Source", "top50_source")

        with f2:
            filtered = filter_selectbox(filtered, "next_action", "Action", "top50_action")

        with f3:
            filtered = filter_selectbox(filtered, "risk_level", "Risk", "top50_risk")

        top50 = filtered.head(50).copy()

        metric_row(
            [
                ("Total Products", len(combined)),
                ("Top 50 View", len(top50)),
                ("Zendrop", int((top50["source_site"] == "zendrop").sum()) if not top50.empty else 0),
                ("DHgate", int((top50["source_site"] == "dhgate").sum()) if not top50.empty else 0),
                ("Avg Profit", f"${clean_number_series(top50['estimated_profit']).mean():.2f}" if not top50.empty else "$0.00"),
            ]
        )

        download_current_view(top50, "top_50_combined_products.csv")

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
            "extra_signal",
            "source_detail",
            "risk_notes",
            "supplier_url",
        ]

        render_table(top50, cols)


# ============================================================
# COMBINED BOARD TAB
# ============================================================

with tab_combined:
    tab_header(
        "📊",
        "Combined Product Board",
        "Full product board with both Zendrop and DHgate together.",
    )

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

        f1, f2, f3 = st.columns(3)

        with f1:
            combined = filter_selectbox(combined, "source_site", "Source", "combined_source")

        with f2:
            combined = filter_selectbox(combined, "next_action", "Action", "combined_action")

        with f3:
            combined = filter_selectbox(combined, "risk_level", "Risk", "combined_risk")

        metric_row(
            [
                ("Products", len(combined)),
                ("TEST", int((combined["next_action"].astype(str) == "TEST").sum())),
                ("WATCH", int((combined["next_action"].astype(str) == "WATCH").sum())),
                ("PASS", int((combined["next_action"].astype(str) == "PASS").sum())),
            ]
        )

        download_current_view(combined, "combined_product_board.csv")

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

        render_table(combined, cols)


# ============================================================
# ZENDROP TAB
# ============================================================

with tab_zendrop:
    tab_header(
        "🟣",
        "Zendrop Products",
        "Products captured from Zendrop, sorted by growth and opportunity signals.",
    )

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

        f1, f2 = st.columns(2)

        with f1:
            zendrop = filter_selectbox(zendrop, "category", "Category", "zendrop_category")

        with f2:
            zendrop = filter_selectbox(zendrop, "saturation", "Saturation", "zendrop_saturation")

        metric_row(
            [
                ("Zendrop Products", len(zendrop)),
                ("With Images", int(zendrop["image_url"].astype(str).str.startswith("http").sum())),
                ("Avg Cost", f"${clean_number_series(zendrop['product_cost']).mean():.2f}"),
                ("Avg Growth", f"{clean_number_series(zendrop['growth_pct']).mean():.1f}%"),
            ]
        )

        download_current_view(zendrop, "zendrop_products.csv")

        zendrop_sorted = sort_numeric(zendrop, "growth_pct", ascending=False)

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

        render_table(zendrop_sorted, cols)


# ============================================================
# DHGATE TAB
# ============================================================

with tab_dhgate:
    tab_header(
        "🟠",
        "DHgate Products",
        "Cleaned DHgate products with profit estimates, risk labels, reviews, and sold signals.",
    )

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

        f1, f2, f3 = st.columns(3)

        with f1:
            dhgate = filter_selectbox(dhgate, "next_action", "Action", "dhgate_action")

        with f2:
            dhgate = filter_selectbox(dhgate, "risk_level", "Risk", "dhgate_risk")

        with f3:
            dhgate = filter_selectbox(dhgate, "crawl_keyword", "Crawl Keyword", "dhgate_keyword")

        metric_row(
            [
                ("DHgate Products", len(dhgate)),
                ("TEST", int((dhgate["next_action"].astype(str) == "TEST").sum())),
                ("WATCH", int((dhgate["next_action"].astype(str) == "WATCH").sum())),
                ("PASS", int((dhgate["next_action"].astype(str) == "PASS").sum())),
            ]
        )

        download_current_view(dhgate, "dhgate_products.csv")

        dhgate_sorted = sort_numeric(dhgate, "dhgate_opportunity_score", ascending=False)

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

        render_table(dhgate_sorted, cols)


# ============================================================
# LAUNCH SHORTLIST TAB
# ============================================================

with tab_shortlist:
    tab_header(
        "🚀",
        "Launch Shortlist",
        "Products ranked for possible testing, with launch tier, angle, and next step.",
    )

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

        f1, f2, f3 = st.columns(3)

        with f1:
            shortlist = filter_selectbox(shortlist, "launch_tier", "Launch Tier", "shortlist_tier")

        with f2:
            shortlist = filter_selectbox(shortlist, "source_site", "Source", "shortlist_source")

        with f3:
            shortlist = filter_selectbox(shortlist, "risk_level", "Risk", "shortlist_risk")

        shortlist = sort_numeric(shortlist, "launch_score", ascending=False)

        metric_row(
            [
                ("Products", len(shortlist)),
                ("A - Test First", int((shortlist["launch_tier"].astype(str) == "A - Test First").sum())),
                ("B - Maybe Test", int((shortlist["launch_tier"].astype(str) == "B - Maybe Test").sum())),
                ("Avg Launch Score", f"{clean_number_series(shortlist['launch_score']).mean():.1f}"),
            ]
        )

        download_current_view(shortlist, "launch_shortlist.csv")

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

        render_table(shortlist, cols)


# ============================================================
# PRODUCT TESTING TAB
# ============================================================

with tab_testing:
    tab_header(
        "🧪",
        "Product Testing Dashboard",
        "Editable testing board for decisions, status, notes, page work, and ad creative.",
    )

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

        f1, f2, f3 = st.columns(3)

        with f1:
            decision_filter = st.selectbox(
                "Test Decision",
                ["All", "TEST", "MAYBE", "PASS", "SAMPLE FIRST", ""],
                key="testing_decision_filter",
            )

        with f2:
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

        with f3:
            test_plan = filter_selectbox(test_plan, "launch_tier", "Launch Tier", "testing_launch_tier")

        if decision_filter != "All":
            test_plan = test_plan[test_plan["test_decision"].astype(str) == decision_filter]

        if status_filter != "All":
            test_plan = test_plan[test_plan["test_status"].astype(str) == status_filter]

        metric_row(
            [
                ("Products", len(test_plan)),
                ("Marked TEST", int((test_plan["test_decision"].astype(str) == "TEST").sum())),
                ("Sample First", int((test_plan["test_decision"].astype(str) == "SAMPLE FIRST").sum())),
                ("Ready/Testing", int(test_plan["test_status"].astype(str).isin(["READY TO TEST", "TESTING"]).sum())),
            ]
        )

        test_plan = sort_numeric(test_plan, "test_rank", ascending=True)

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

        edited = st.data_editor(
            test_plan[cols],
            use_container_width=True,
            hide_index=True,
            height=850,
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
                col for col in [
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
                ] if col in cols
            ],
        )

        c1, c2 = st.columns([1, 4])

        with c1:
            save_clicked = st.button("💾 Save Decisions")

        with c2:
            download_current_view(edited, "product_testing_current_view.csv")

        if save_clicked:
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
