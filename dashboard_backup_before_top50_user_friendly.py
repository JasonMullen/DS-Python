from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st


# ============================================================
# FILE PATHS
# ============================================================

OPPORTUNITIES_PATH = Path("output/opportunities.csv")
SUPPLIER_PATH = Path("data/supplier_products.csv")

ZENDROP_PATH = Path("data/zendrop_smart_capture.csv")
DHGATE_CLEAN_PATH = Path("data/dhgate_clean_user_friendly.csv")
DHGATE_RAW_PATH = Path("data/dhgate_large_capture.csv")

LAUNCH_SHORTLIST_PATH = Path("output/launch_shortlist.csv")
PRODUCT_TEST_PLAN_PATH = Path("output/product_test_plan.csv")
TEST_DECISIONS_PATH = Path("output/product_test_decisions.csv")


# ============================================================
# APP SETUP
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


# ============================================================
# HELPERS
# ============================================================

def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path).fillna("").astype("object")


def clean_number(value):
    text = str(value).replace("$", "").replace("%", "").replace(",", "").strip()

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


def selectbox_filter(df: pd.DataFrame, col: str, label: str, key: str) -> pd.DataFrame:
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


def column_config():
    return {
        "image_url": st.column_config.ImageColumn("Image", width="small"),
        "supplier_url": st.column_config.LinkColumn("Supplier Link", display_text="Open"),
        "clean_supplier_url": st.column_config.LinkColumn("Clean Supplier Link", display_text="Open"),
        "product_cost": st.column_config.NumberColumn("Product Cost", format="$%.2f"),
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
        "rating": st.column_config.NumberColumn("Rating", format="%.2f"),
        "reviews_count": st.column_config.NumberColumn("Reviews"),
        "sold_count": st.column_config.NumberColumn("Sold"),
    }


def sort_by_numeric(df: pd.DataFrame, col: str, ascending: bool = False) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df

    df = df.copy()
    df[col] = clean_number_series(df[col])
    return df.sort_values(col, ascending=ascending)


# ============================================================
# LOAD SOURCE DATA
# ============================================================

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
    ]

    df = add_missing_columns(df, needed)

    df["source_site"] = "zendrop"
    df["marketplace_source"] = "ZENDROP"

    for col in [
        "product_cost",
        "estimated_sale_price",
        "estimated_profit",
        "profit_margin_pct",
        "roi_pct",
        "p_c_ratio",
        "growth_pct",
        "order_trend_score",
    ]:
        if col in df.columns:
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

    for col in [
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
    ]:
        if col in df.columns:
            df[col] = clean_number_series(df[col])

    return df.fillna("")


def load_combined_board() -> pd.DataFrame:
    df = read_csv_safe(OPPORTUNITIES_PATH)

    if df.empty:
        return df

    supplier = read_csv_safe(SUPPLIER_PATH)

    if not supplier.empty and "product_name" in supplier.columns:
        useful_cols = [
            "product_name",
            "source_site",
            "marketplace_source",
            "image_url",
            "store_name",
            "rating",
            "reviews_count",
            "sold_count",
            "shipping_text",
            "p_c_ratio",
            "growth_pct",
            "saturation",
            "top_country",
            "first_seen_at",
            "last_seen_at",
            "supplier_url",
        ]

        useful_cols = [col for col in useful_cols if col in supplier.columns]

        supplier = supplier[useful_cols].drop_duplicates(subset=["product_name"])

        df = df.merge(
            supplier,
            on="product_name",
            how="left",
            suffixes=("", "_source"),
        )

        for col in useful_cols:
            extra = f"{col}_source"

            if col != "product_name" and extra in df.columns:
                if col not in df.columns:
                    df[col] = df[extra]
                else:
                    df[col] = df[col].where(df[col].astype(str).str.len() > 0, df[extra])

        df = df.drop(columns=[col for col in df.columns if col.endswith("_source")])

    needed = [
        "source_site",
        "marketplace_source",
        "image_url",
        "product_name",
        "category",
        "product_cost",
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

    df = add_missing_columns(df, needed)

    return df.fillna("")


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

    plan = add_missing_columns(plan, needed)

    return plan


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("📦 Product Board")
st.sidebar.write("Zendrop and DHgate are now separated into their own tabs.")

search_query = st.sidebar.text_input(
    "Search all tabs",
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
st.sidebar.header("Main Files")
st.sidebar.markdown("**Zendrop:** `data/zendrop_smart_capture.csv`")
st.sidebar.markdown("**DHgate:** `data/dhgate_clean_user_friendly.csv`")
st.sidebar.markdown("**Combined:** `output/opportunities.csv`")


# ============================================================
# MAIN TABS
# ============================================================

st.title("📦 Dropship Product Research Board")

tab_combined, tab_zendrop, tab_dhgate, tab_shortlist, tab_testing = st.tabs(
    [
        "📊 Combined Board",
        "🟣 Zendrop Products",
        "🟠 DHgate Products",
        "🚀 Launch Shortlist",
        "🧪 Product Testing Dashboard",
    ]
)


# ============================================================
# COMBINED BOARD TAB
# ============================================================

with tab_combined:
    st.header("📊 Combined Product Board")

    combined = load_combined_board()

    if combined.empty:
        show_missing_file(
            OPPORTUNITIES_PATH,
            "python -m dropship_researcher.main",
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
            ],
        )

        combined = selectbox_filter(combined, "source_site", "Source", "combined_source_filter")
        combined = selectbox_filter(combined, "next_action", "Next Action", "combined_action_filter")
        combined = selectbox_filter(combined, "risk_level", "Risk Level", "combined_risk_filter")

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Products", len(combined))

        with c2:
            st.metric("TEST", int((combined["next_action"].astype(str) == "TEST").sum()))

        with c3:
            st.metric("WATCH", int((combined["next_action"].astype(str) == "WATCH").sum()))

        with c4:
            st.metric("PASS", int((combined["next_action"].astype(str) == "PASS").sum()))

        display_cols = [
            "image_url",
            "product_name",
            "source_site",
            "marketplace_source",
            "category",
            "product_cost",
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

        display_cols = [col for col in display_cols if col in combined.columns]

        combined = sort_by_numeric(combined, "final_score", ascending=False)

        st.subheader("Best Combined Products")

        st.dataframe(
            combined[display_cols].head(100),
            use_container_width=True,
            hide_index=True,
            height=700,
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

        zendrop = selectbox_filter(zendrop, "category", "Zendrop Category", "zendrop_category_filter")
        zendrop = selectbox_filter(zendrop, "saturation", "Zendrop Saturation", "zendrop_saturation_filter")

        total = len(zendrop)
        with_images = int(zendrop["image_url"].astype(str).str.startswith("http").sum())
        avg_cost = clean_number_series(zendrop["product_cost"]).mean() if "product_cost" in zendrop.columns else 0
        avg_growth = clean_number_series(zendrop["growth_pct"]).mean() if "growth_pct" in zendrop.columns else 0

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Zendrop Products", total)

        with c2:
            st.metric("With Images", with_images)

        with c3:
            st.metric("Avg Cost", f"${avg_cost:.2f}")

        with c4:
            st.metric("Avg Growth", f"{avg_growth:.1f}%")

        zendrop_cols = [
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

        zendrop_cols = [col for col in zendrop_cols if col in zendrop.columns]

        st.subheader("Newest Zendrop Products")

        recent_zendrop = zendrop.copy()

        if "first_seen_at" in recent_zendrop.columns:
            recent_zendrop["_date"] = pd.to_datetime(recent_zendrop["first_seen_at"], errors="coerce")
            recent_zendrop = recent_zendrop.sort_values("_date", ascending=False)

        st.dataframe(
            recent_zendrop[zendrop_cols].head(100),
            use_container_width=True,
            hide_index=True,
            height=650,
            column_config=column_config(),
        )

        st.subheader("Full Zendrop Table")

        zendrop_sorted = sort_by_numeric(zendrop, "growth_pct", ascending=False)

        st.dataframe(
            zendrop_sorted[zendrop_cols],
            use_container_width=True,
            hide_index=True,
            height=800,
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

        dhgate = selectbox_filter(dhgate, "next_action", "DHgate Action", "dhgate_action_filter")
        dhgate = selectbox_filter(dhgate, "risk_level", "DHgate Risk", "dhgate_risk_filter")
        dhgate = selectbox_filter(dhgate, "crawl_keyword", "Crawl Keyword", "dhgate_keyword_filter")

        total = len(dhgate)
        test_count = int((dhgate["next_action"].astype(str) == "TEST").sum())
        watch_count = int((dhgate["next_action"].astype(str) == "WATCH").sum())
        pass_count = int((dhgate["next_action"].astype(str) == "PASS").sum())

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("DHgate Products", total)

        with c2:
            st.metric("TEST", test_count)

        with c3:
            st.metric("WATCH", watch_count)

        with c4:
            st.metric("PASS", pass_count)

        dhgate_cols = [
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
            "first_seen_at",
            "last_seen_at",
        ]

        dhgate_cols = [col for col in dhgate_cols if col in dhgate.columns]

        dhgate_sorted = sort_by_numeric(dhgate, "dhgate_opportunity_score", ascending=False)

        st.subheader("Best DHgate Products")

        st.dataframe(
            dhgate_sorted[dhgate_cols].head(100),
            use_container_width=True,
            hide_index=True,
            height=750,
            column_config=column_config(),
        )

        st.subheader("Full DHgate Table")

        st.dataframe(
            dhgate_sorted[dhgate_cols],
            use_container_width=True,
            hide_index=True,
            height=900,
            column_config=column_config(),
        )


# ============================================================
# LAUNCH SHORTLIST TAB
# ============================================================

with tab_shortlist:
    st.header("🚀 Launch Shortlist")

    shortlist = read_csv_safe(LAUNCH_SHORTLIST_PATH)

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

        shortlist = selectbox_filter(shortlist, "launch_tier", "Launch Tier", "shortlist_tier_filter")
        shortlist = selectbox_filter(shortlist, "source_site", "Source", "shortlist_source_filter")

        shortlist = sort_by_numeric(shortlist, "launch_score", ascending=False)

        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric("Products", len(shortlist))

        with c2:
            st.metric("A - Test First", int((shortlist["launch_tier"].astype(str) == "A - Test First").sum()))

        with c3:
            st.metric("B - Maybe Test", int((shortlist["launch_tier"].astype(str) == "B - Maybe Test").sum()))

        shortlist_cols = [
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

        shortlist_cols = [col for col in shortlist_cols if col in shortlist.columns]

        st.dataframe(
            shortlist[shortlist_cols],
            use_container_width=True,
            hide_index=True,
            height=900,
            column_config=column_config(),
        )


# ============================================================
# PRODUCT TESTING DASHBOARD TAB
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

        test_cols = [
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

        test_cols = [col for col in test_cols if col in test_plan.columns]

        test_plan = sort_by_numeric(test_plan, "test_rank", ascending=True)

        edited = st.data_editor(
            test_plan[test_cols],
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
