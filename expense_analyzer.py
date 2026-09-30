"""Small Pandas helpers used by the MCP expense tools."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"date", "category", "description", "amount"}
CATEGORY_ALIASES = {
    "food": {"dining out", "groceries"},
    "transport": {"gas"},
    "bills": {"utilities", "subscriptions"},
}
_expenses: pd.DataFrame | None = None


def load_expenses(csv_path: str | None = None) -> None:
    """Load and validate the current CSV file for the functions below."""
    global _expenses

    path = csv_path or os.getenv("EXPENSE_CSV_PATH")
    if not path:
        raise ValueError("No CSV file was provided.")
    if not Path(path).is_file():
        raise ValueError("The selected CSV file could not be found.")

    try:
        expenses = pd.read_csv(path)
    except (pd.errors.EmptyDataError, UnicodeDecodeError) as error:
        raise ValueError("The CSV file is empty or cannot be read.") from error

    if expenses.empty:
        raise ValueError("The CSV file has no expense rows.")
    missing_columns = REQUIRED_COLUMNS - set(expenses.columns)
    if missing_columns:
        raise ValueError(
            "CSV is missing required columns: " + ", ".join(sorted(missing_columns))
        )

    expenses = expenses.copy()
    expenses["amount"] = pd.to_numeric(expenses["amount"], errors="coerce")
    if expenses["amount"].isna().any():
        raise ValueError("Every amount in the CSV must be a number.")
    _expenses = expenses


def _data() -> pd.DataFrame:
    if _expenses is None:
        load_expenses()
    assert _expenses is not None
    return _expenses


def _expense_data() -> pd.DataFrame:
    """Use positive values for spending and leave Income out of expense results."""
    expenses = _data().copy()
    expenses = expenses[expenses["category"].astype(str).str.lower() != "income"]
    expenses["amount"] = expenses["amount"].abs()
    return expenses


def get_matching_categories(category: str) -> list[str]:
    """Match an exact category or a beginner-friendly category alias."""
    categories = _expense_data()["category"].dropna().astype(str).unique().tolist()
    exact_match = next((item for item in categories if item.lower() == category.lower()), None)
    if exact_match:
        return [exact_match]

    aliases = CATEGORY_ALIASES.get(category.lower(), set())
    matches = [item for item in categories if item.lower() in aliases]
    if not matches:
        raise ValueError(
            f"Invalid category '{category}'. Available categories: {', '.join(sorted(categories))}."
        )
    return matches


def get_expense_summary() -> dict:
    """Return the core expense metrics."""
    expenses = _expense_data()
    return {
        "total_expenses": round(float(expenses["amount"].sum()), 2),
        "transaction_count": int(len(expenses)),
        "average_expense": round(float(expenses["amount"].mean()), 2),
    }


def calculate_total(category: str | None = None) -> dict:
    """Calculate all spending, or spending in one category."""
    expenses = _expense_data()
    if category:
        matching_categories = get_matching_categories(category)
        expenses = expenses[expenses["category"].isin(matching_categories)]
    return {"category": category or "All categories", "total": round(float(expenses["amount"].sum()), 2)}


def filter_expenses(category: str | None = None) -> list[dict]:
    """Return expenses, optionally filtered to one category."""
    expenses = _expense_data()
    if category:
        matching_categories = get_matching_categories(category)
        expenses = expenses[expenses["category"].isin(matching_categories)]
    return expenses.to_dict(orient="records")


def group_by_category() -> list[dict]:
    """Return total spending in each category, highest first."""
    totals = (
        _expense_data()
        .groupby("category", as_index=False)["amount"]
        .sum()
        .sort_values("amount", ascending=False)
    )
    totals["amount"] = totals["amount"].round(2)
    return totals.to_dict(orient="records")


def top_expenses(n: int = 5) -> list[dict]:
    """Return the largest individual expenses."""
    if n < 1:
        raise ValueError("The number of expenses must be at least 1.")
    return _expense_data().nlargest(n, "amount").to_dict(orient="records")
