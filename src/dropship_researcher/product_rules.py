from __future__ import annotations

import pandas as pd


RISKY_TERMS = {
    "supplement", "vitamin", "cbd", "thc", "nicotine", "vape", "weight loss",
    "diet", "medical", "diabetes", "blood pressure", "pain relief", "pregnancy",
    "baby", "infant", "gun", "knife", "tactical", "weapon", "laser"
}

BRAND_RISK_TERMS = {
    "nike", "adidas", "apple", "iphone", "samsung", "disney", "marvel",
    "pokemon", "nintendo", "lego", "stanley", "lululemon", "crocs"
}

FRAGILE_OR_BULKY_TERMS = {
    "glass", "mirror", "ceramic", "furniture", "chair", "table", "lamp",
    "backpack", "camera", "machine"
}


def _as_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _contains_any(text: str, terms: set[str]) -> list[str]:
    return sorted([term for term in terms if term in text])


def guess_source(url: str) -> str:
    url = str(url).lower()

    if "zendrop" in url:
        return "Zendrop"
    if "dhgate" in url:
        return "DHgate"
    if "aliexpress" in url:
        return "AliExpress"
    if "alibaba" in url:
        return "Alibaba"

    return "Unknown"


def analyze_product(row: pd.Series) -> pd.Series:
    product_name = str(row.get("product_name", ""))
    keyword = str(row.get("keyword", ""))
    category = str(row.get("category", ""))
    supplier_url = str(row.get("supplier_url", ""))

    text = f"{product_name} {keyword} {category} {supplier_url}".lower()

    estimated_profit = _as_float(row.get("estimated_profit"))
    profit_margin_pct = _as_float(row.get("profit_margin_pct"))
    roi_pct = _as_float(row.get("roi_pct"))
    shipping_cost = _as_float(row.get("shipping_cost"))
    opportunity_score = _as_float(row.get("opportunity_score"))

    notes = []
    risk_points = 0

    risky_matches = _contains_any(text, RISKY_TERMS)
    brand_matches = _contains_any(text, BRAND_RISK_TERMS)
    bulky_matches = _contains_any(text, FRAGILE_OR_BULKY_TERMS)

    if risky_matches:
        risk_points += 4
        notes.append(f"Restricted/compliance risk: {', '.join(risky_matches)}")

    if brand_matches:
        risk_points += 5
        notes.append(f"Brand/trademark risk: {', '.join(brand_matches)}")

    if bulky_matches:
        risk_points += 2
        notes.append(f"Fragile/bulky shipping risk: {', '.join(bulky_matches)}")

    if shipping_cost == 0:
        risk_points += 2
        notes.append("Shipping cost missing or unknown")

    if estimated_profit < 8:
        risk_points += 3
        notes.append("Low profit dollars")

    if profit_margin_pct < 30:
        risk_points += 3
        notes.append("Margin below 30%")

    if roi_pct < 100:
        risk_points += 2
        notes.append("ROI below 100%")

    if not supplier_url or supplier_url.lower() in {"nan", "none"}:
        risk_points += 2
        notes.append("Missing supplier URL")

    if risk_points >= 7:
        risk_level = "HIGH"
    elif risk_points >= 3:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    final_score = max(0, round(opportunity_score - (risk_points * 6), 2))

    decision_text = str(row.get("decision", "")).upper()

    if risk_level == "HIGH":
        next_action = "AVOID"
    elif "TEST" in decision_text and risk_level == "LOW":
        next_action = "DEEP RESEARCH"
    elif "TEST" in decision_text and risk_level == "MEDIUM":
        next_action = "VERIFY FIRST"
    elif "WATCH" in decision_text:
        next_action = "WATCH"
    else:
        next_action = "PASS"

    return pd.Series(
        {
            "source_guess": guess_source(supplier_url),
            "risk_level": risk_level,
            "risk_points": risk_points,
            "risk_notes": "; ".join(notes) if notes else "No major risk flags",
            "final_score": final_score,
            "next_action": next_action,
        }
    )


def add_validation_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    validation = df.apply(analyze_product, axis=1)
    return pd.concat([df, validation], axis=1)
