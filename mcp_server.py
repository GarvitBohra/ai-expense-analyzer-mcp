"""MCP server that exposes Pandas expense analysis as tools."""

import os
import traceback
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from expense_analyzer import (
    calculate_total,
    filter_expenses,
    get_expense_summary,
    group_by_category,
    top_expenses,
)

mcp = FastMCP("Expense Analyzer")


@mcp.tool()
def expense_summary() -> dict:
    """Get total spending, transaction count, and average expense."""
    return get_expense_summary()


@mcp.tool()
def total_spending(category: str | None = None) -> dict:
    """Get total spending. Supply a category only for that category's total."""
    return calculate_total(category)


@mcp.tool()
def expenses_for_category(category: str | None = None) -> list[dict]:
    """List expenses, optionally only the expenses in a category."""
    return filter_expenses(category)


@mcp.tool()
def spending_by_category() -> list[dict]:
    """Get each category and its total spending, ordered highest first."""
    return group_by_category()


@mcp.tool()
def largest_expenses(n: int = 5) -> list[dict]:
    """Get the n largest individual expenses. Use this for biggest expenses questions."""
    return top_expenses(n)


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except BaseException:
        # Stdio hides server stderr from Streamlit. This temporary log makes
        # a startup problem visible in the Streamlit error message.
        error_log = os.getenv("MCP_ERROR_LOG")
        if error_log:
            Path(error_log).write_text(traceback.format_exc(), encoding="utf-8")
        raise
