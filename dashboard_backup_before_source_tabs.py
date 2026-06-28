from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st


OPPORTUNITIES_PATH = Path("output/opportunities.csv")
SUPPLIER_PATH = Path("data/supplier_products.csv")
LAUNCH_SHORTLIST_PATH = Path("output/launch_shortlist.csv")
TOP_25_PATH = Path("output/top_25_launch_shortlist.csv")
PRODUCT_TEST_PLAN_PATH = Path("output/product_test_plan.csv")
TEST_DECISIONS_PATH = Path("output/product_test_decisions.csv")


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


def clean_number(series):
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


def merge_by_product_name(base_df: pd.DataFrame, extra_df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if base_df.empty or extra_df.empty:
        return base_df

    if "product_name" not in base_df.columns or "product_name" not in extra_df.columns:
        return base_df

    keep_cols = ["product_name"] + [col for col in columns if col in extra_df.columns]
    extra_df = extra_df[keep_cols].drop_duplicates(subset=["product_name"])

    merged = base_df.merge(extra_df, on="product_name", how="left", suffixes=("", "_extra"))

    for col in columns:
        extra_col = f"{col}_extra"

        if extra_col in merged.columns:
            if col not in merged.columns:
                merged[col] = merged[extra_col]
            else:
                merged[col] = merged[col].where(
                    merged[col].astype(str).str.len() > 0,
                    merged[extra_col],
                )

    drop_cols = [col for col in merged.columns if col.endswith("_extra")]
    merged = merged.drop(columns=drop_cols)

    return merged.fillna("")


def apply_search(df: pd.DataFrame, query: str, columns: list[str]) -> pd.DataFrame:
    if df.empty or not query.strip():
        return df

    query = query.lower().strip()
    mask = pd.Series(False, index=df.index)

    for col in columns:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.lower().str.contains(query, na=False)

    return df[mask]


def basic_column_config():
    return {
        "image_url": st.column_config.ImageColumn("Image", width="small"),
        "supplier_url": st.column_config.LinkColumn("Supplier Link", display_text="Open"),
        "exact_product_url": st.column_config.LinkColumn("Exact Product URL", display_text="Open"),
        "product_cost": st.column_config.NumberColumn("Cost", format="$%.2f"),
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
    }


def show_missing_file_message(path: Path, command: str):
    st.warning(f"Missing `{path}`.")
    st.code(command, language="powershell")


# ============================================================
# LOAD DATA
# ============================================================

def load_product_board() -> pd.DataFrame:
    df = read_csv_safe(OPPORTUNITIES_PATH)

    if df.empty:
        return df

    supplier = read_csv_safe(SUPPLIER_PATH)

    supplier_cols = [
        "image_url",
        "source_site",
        "marketplace_source",
        "store_name",
        "rating",
        "reviews_count",
        "sold_count",
        "shipping_text",
        "p_c_ratio",
        "growth_pct",
        "order_trend_score",
        "saturation",
        "top_country",
        "first_seen_at",
        "last_seen_at",
        "supplier_url",
    ]

    df = merge_by_product_name(df, supplier, supplier_cols)

    needed = [
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
        "first_seen_at",
        "last_seen_at",
        "supplier_url",
    ]

    df = add_missing_columns(df, needed)

    return df


def load_test_plan() -> pd.DataFrame:
    plan = read_csv_safe(PRODUCT_TEST_PLAN_PATH)

    if plan.empty:
        return plan

    decisions = read_csv_safe(TEST_DECISIONS_PATH)

    decision_cols = [
        "product_name",
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

    if not decisions.empty:
        plan = merge_by_product_name(plan, decisions, decision_cols[1:])

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

st.sidebar.title("📦 Dropship Board")
st.sidebar.write("Use this dashboard to review products, shortlist winners, and plan product tests.")

st.sidebar.divider()

st.sidebar.header("Main Filters")
search_query = st.sidebar.text_input("Search products", placeholder="pet, shirt, beauty, home, car")

st.sidebar.divider()

st.sidebar.header("Workflow")
st.sidebar.code(
    """
python -m dropship_researcher.main
python .\\make_launch_shortlist.py
python .\\make_product_test_plan.py
streamlit run dashboard.py
""",
    language="powershell",
)

st.sidebar.divider()

st.sidebar.header("Meaning")
st.sidebar.markdown("**A - Test First:** Best products to seriously review.")
st.sidebar.markdown("**B - Maybe Test:** Possible products, but review manually.")
st.sidebar.markdown("**C - Skip For Now:** Weak, risky, or not worth testing yet.")
st.sidebar.markdown("**Product Testing Dashboard:** Where you choose the best 3–5 products.")


# ============================================================
# MAIN APP
# ============================================================

st.title("📦 Dropship Product Research Board")

tab_board, tab_recent, tab_shortlist, tab_testing = st.tabs(
    [
        "📊 Product Board",
        "🆕 Recently Added",
        "🚀 Launch Shortlist",
        "🧪 Product Testing Dashboard",
    ]
)


# ============================================================
# TAB 1: PRODUCT BOARD
# ============================================================

with tab_board:
    st.header("📊 Product Board")

    df = load_product_board()

    if df.empty:
        show_missing_file_message(
            OPPORTUNITIES_PATH,
            "python -m dropship_researcher.main",
        )
    else:
        board_search_cols = [
            "product_name",
            "source_site",
            "marketplace_source",
            "category",
            "source_guess",
            "store_name",
            "risk_level",
            "next_action",
            "risk_notes",
            "saturation",
            "top_country",
        ]

        filtered = apply_search(df, search_query, board_search_cols)

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Total Products", len(df))

        with c2:
            st.metric("Matching Products", len(filtered))

        with c3:
            st.metric("With Images", int(df["image_url"].astype(str).str.startswith("http").sum()))

        with c4:
            test_count = int(df["next_action"].astype(str).str.lower().str.contains("test", na=False).sum())
            st.metric("Marked TEST", test_count)

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
            "p_c_ratio",
            "growth_pct",
            "opportunity_score",
            "final_score",
            "risk_level",
            "next_action",
            "risk_notes",
            "supplier_url",
        ]

        display_cols = [col for col in display_cols if col in filtered.columns]

        st.subheader("🏆 Best Products")

        best = filtered.copy()

        if "final_score" in best.columns:
            best["final_score"] = clean_number(best["final_score"])
            best = best.sort_values("final_score", ascending=False)

        st.dataframe(
            best[display_cols].head(25),
            use_container_width=True,
            hide_index=True,
            height=500,
            column_config=basic_column_config(),
        )

        st.subheader("📋 Full Product Ranking Table")

        full = df.copy()

        if "final_score" in full.columns:
            full["final_score"] = clean_number(full["final_score"])
            full = full.sort_values("final_score", ascending=False)

        st.dataframe(
            full[display_cols],
            use_container_width=True,
            hide_index=True,
            height=800,
            column_config=basic_column_config(),
        )


# ============================================================
# TAB 2: RECENTLY ADDED
# ============================================================

with tab_recent:
    st.header("🆕 Recently Added Products")

    df = load_product_board()

    if df.empty:
        show_missing_file_message(
            OPPORTUNITIES_PATH,
            "python -m dropship_researcher.main",
        )
    else:
        recent = df.copy()

        if "first_seen_at" in recent.columns:
            recent["_first_seen_dt"] = pd.to_datetime(recent["first_seen_at"], errors="coerce")
            recent = recent.sort_values("_first_seen_dt", ascending=False)

        recent_cols = [
            "image_url",
            "product_name",
            "source_site",
            "marketplace_source",
            "store_name",
            "category",
            "product_cost",
            "p_c_ratio",
            "growth_pct",
            "first_seen_at",
            "last_seen_at",
            "next_action",
            "risk_level",
            "supplier_url",
        ]

        recent_cols = [col for col in recent_cols if col in recent.columns]

        st.write("Newest products based on the `first_seen_at` date from your product capture.")

        st.dataframe(
            recent[recent_cols].head(100),
            use_container_width=True,
            hide_index=True,
            height=800,
            column_config=basic_column_config(),
        )


# ============================================================
# TAB 3: LAUNCH SHORTLIST
# ============================================================

with tab_shortlist:
    st.header("🚀 Launch Shortlist")

    shortlist = read_csv_safe(LAUNCH_SHORTLIST_PATH)

    if shortlist.empty:
        show_missing_file_message(
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
                "store_name",
            ],
        )

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Shortlist Products", len(shortlist))

        with c2:
            st.metric("A - Test First", int((shortlist["launch_tier"].astype(str) == "A - Test First").sum()))

        with c3:
            st.metric("B - Maybe Test", int((shortlist["launch_tier"].astype(str) == "B - Maybe Test").sum()))

        with c4:
            st.metric("C - Skip", int((shortlist["launch_tier"].astype(str) == "C - Skip For Now").sum()))

        tier_filter = st.selectbox(
            "Launch Tier",
            ["All", "A - Test First", "B - Maybe Test", "C - Skip For Now"],
            key="launch_tier_filter",
        )

        if tier_filter != "All":
            shortlist = shortlist[shortlist["launch_tier"].astype(str) == tier_filter]

        shortlist_cols = [
            "image_url",
            "product_name",
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
            "p_c_ratio",
            "growth_pct",
            "risk_level",
            "risk_notes",
            "supplier_url",
        ]

        shortlist_cols = [col for col in shortlist_cols if col in shortlist.columns]

        if "launch_score" in shortlist.columns:
            shortlist["launch_score"] = clean_number(shortlist["launch_score"])
            shortlist = shortlist.sort_values("launch_score", ascending=False)

        st.dataframe(
            shortlist[shortlist_cols],
            use_container_width=True,
            hide_index=True,
            height=900,
            column_config=basic_column_config(),
        )


# ============================================================
# TAB 4: PRODUCT TESTING DASHBOARD
# ============================================================

with tab_testing:
    st.header("🧪 Product Testing Dashboard")

    test_plan = load_test_plan()

    if test_plan.empty:
        show_missing_file_message(
            PRODUCT_TEST_PLAN_PATH,
            "python .\\make_product_test_plan.py",
        )
    else:
        st.write("Use this tab to choose the best **3–5 products** to test first.")

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
            key="test_decision_filter",
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
            key="test_status_filter",
        )

        if decision_filter != "All":
            test_plan = test_plan[test_plan["test_decision"].astype(str) == decision_filter]

        if status_filter != "All":
            test_plan = test_plan[test_plan["test_status"].astype(str) == status_filter]

        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("Products in Test Plan", len(test_plan))

        with c2:
            st.metric("Marked TEST", int((test_plan["test_decision"].astype(str) == "TEST").sum()))

        with c3:
            st.metric("Sample First", int((test_plan["test_decision"].astype(str) == "SAMPLE FIRST").sum()))

        with c4:
            st.metric("Ready/Testing", int(test_plan["test_status"].astype(str).isin(["READY TO TEST", "TESTING"]).sum()))

        st.subheader("🎯 Top Product Testing Plan")

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

        if "test_rank" in test_plan.columns:
            test_plan["test_rank"] = clean_number(test_plan["test_rank"])
            test_plan = test_plan.sort_values("test_rank", ascending=True)

        edited = st.data_editor(
            test_plan[test_cols],
            use_container_width=True,
            hide_index=True,
            height=950,
            column_config={
                **basic_column_config(),
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

            st.success(f"Saved product testing decisions to `{TEST_DECISIONS_PATH}`.")

        st.subheader("✅ Your Current Testing Shortlist")

        chosen = test_plan[
            test_plan["test_decision"].astype(str).isin(["TEST", "SAMPLE FIRST"])
        ].copy()

        chosen_cols = [
            "image_url",
            "product_name",
            "test_decision",
            "test_status",
            "manual_priority",
            "recommended_test_price",
            "estimated_profit",
            "ideal_customer",
            "customer_pain_point",
            "ad_hook_1",
            "risk_notes",
            "supplier_url",
        ]

        chosen_cols = [col for col in chosen_cols if col in chosen.columns]

        st.dataframe(
            chosen[chosen_cols],
            use_container_width=True,
            hide_index=True,
            height=450,
            column_config=basic_column_config(),
        )
