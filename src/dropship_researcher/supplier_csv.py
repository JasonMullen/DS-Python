from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .models import ProductCandidate


def _to_float(value: str | None, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    return float(str(value).replace("$", "").strip())


def load_supplier_products(path: str | Path) -> list[ProductCandidate]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Supplier CSV not found: {path}")

    candidates: list[ProductCandidate] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"product_name", "keyword", "product_cost", "shipping_cost"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required CSV columns: {sorted(missing)}")

        for row in reader:
            name = (row.get("product_name") or "").strip()
            keyword = (row.get("keyword") or name).strip().lower()
            if not name or not keyword:
                continue
            est_raw = (row.get("estimated_sale_price") or "").strip()
            candidates.append(
                ProductCandidate(
                    product_name=name,
                    keyword=keyword,
                    product_cost=_to_float(row.get("product_cost")),
                    shipping_cost=_to_float(row.get("shipping_cost")),
                    estimated_sale_price=_to_float(est_raw) if est_raw else None,
                    supplier_url=(row.get("supplier_url") or "").strip(),
                    category=(row.get("category") or "").strip(),
                )
            )
    return candidates


def load_seed_keywords(path: str | Path) -> list[str]:
    path = Path(path)
    if not path.exists():
        return []
    return [line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
