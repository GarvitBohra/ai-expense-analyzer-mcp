"""Streamlit interface for asking questions about an uploaded expense CSV."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI, OpenAIError

from expense_analyzer import get_expense_summary, group_by_category, load_expenses

load_dotenv()

st.set_page_config(page_title="AI Expense Analyzer", page_icon="💸")
st.title("AI Expense Analyzer")
st.caption("Ask questions about your expenses using natural language.")


def readable_error(error: BaseException) -> str:
    """Show the useful child error hidden inside Python 3.11 task groups."""
    if isinstance(error, BaseExceptionGroup):
        messages = [readable_error(item) for item in error.exceptions]
        return " | ".join(message for message in messages if message)
    return str(error)


def save_upload(uploaded_file) -> str:
    """Save Streamlit's in-memory upload so the MCP subprocess can read it."""
    suffix = Path(uploaded_file.name).suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        return temp_file.name


def show_chart_from_question(question: str, expenses: pd.DataFrame) -> bool:
    """Render a requested chart using any category names found in the question."""
    question_lower = question.lower()
    if not any(word in question_lower for word in ("chart", "graph", "plot")):
        return False

    categories = expenses["category"].dropna().astype(str).unique().tolist()
    selected_categories = [
        category
        for category in categories
        if re.search(rf"\b{re.escape(category.lower())}\b", question_lower)
    ]
    chart_expenses = expenses[expenses["category"].isin(selected_categories or categories)].copy()
    selected_label = ", ".join(selected_categories) if selected_categories else "all categories"

    if "line" in question_lower:
        chart_expenses["date"] = pd.to_datetime(chart_expenses["date"], errors="coerce")
        chart_expenses = chart_expenses.dropna(subset=["date"])
        if chart_expenses.empty:
            st.warning("A line chart needs valid dates in the uploaded CSV.")
            return True
        line_data = (
            chart_expenses.groupby(["date", "category"])["amount"]
            .sum()
            .unstack(fill_value=0)
            .sort_index()
        )
        st.caption(f"Line chart: daily spending for {selected_label}")
        st.line_chart(line_data)
    else:
        totals = chart_expenses.groupby("category", as_index=False)["amount"].sum()
        if "pie" in question_lower:
            pie_totals = totals[totals["amount"] > 0]
            if pie_totals.empty:
                st.warning("A pie chart needs at least one category with positive spending.")
                return True
            if len(pie_totals) != len(totals):
                st.info("Categories with zero or negative net spending are not shown in pie charts.")
            figure, axis = plt.subplots()
            axis.pie(
                pie_totals["amount"],
                labels=pie_totals["category"],
                autopct="%1.1f%%",
                startangle=90,
            )
            axis.axis("equal")
            st.caption(f"Pie chart: spending for {selected_label}")
            st.pyplot(figure, use_container_width=True)
            plt.close(figure)
        else:
            st.caption(f"Bar chart: spending for {selected_label}")
            st.bar_chart(totals, x="category", y="amount", color="#4F46E5")
    return True


def ask_with_mcp(question: str, csv_path: str) -> str:
    """Let OpenAI choose MCP tools, execute them via stdio, then write an answer."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY. Add it to a .env file and restart Streamlit.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".log") as log_file:
        error_log = log_file.name
    try:
        return asyncio.run(_ask_with_mcp(question, csv_path, api_key, error_log))
    except Exception as error:
        log_contents = Path(error_log).read_text(encoding="utf-8") if Path(error_log).exists() else ""
        if log_contents:
            raise RuntimeError(f"The MCP server stopped. Details:\n{log_contents}") from error
        raise
    finally:
        Path(error_log).unlink(missing_ok=True)


async def _ask_with_mcp(question: str, csv_path: str, api_key: str, error_log: str) -> str:
    server_file = Path(__file__).with_name("mcp_server.py")
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(server_file)],
        env={**os.environ, "EXPENSE_CSV_PATH": csv_path, "MCP_ERROR_LOG": error_log},
    )

    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            openai_tools = [
                {"type": "function", "name": tool.name, "description": tool.description,
                 "parameters": tool.inputSchema}
                for tool in mcp_tools
            ]
            client = OpenAI(api_key=api_key)
            instructions = (
                "You are an expense-analysis assistant. Use the provided tools for every "
                "calculation or expense-data claim. Do not calculate from memory. Give a "
                "short, clear answer and format currency with $."
            )
            response = client.responses.create(
                model="gpt-4.1-mini",
                instructions=instructions,
                input=question,
                tools=openai_tools,
            )
            tool_outputs = []
            for item in response.output:
                if item.type == "function_call":
                    arguments = json.loads(item.arguments)
                    result = await session.call_tool(item.name, arguments)
                    if result.isError:
                        message = result.content[0].text if result.content else "The expense tool failed."
                        raise ValueError(message)
                    tool_outputs.append({
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": result.content[0].text if result.content else "No result returned.",
                    })
            if not tool_outputs:
                return response.output_text
            final_response = client.responses.create(
                model="gpt-4.1-mini",
                instructions=instructions,
                previous_response_id=response.id,
                input=tool_outputs,
            )
            return final_response.output_text


uploaded_file = st.file_uploader("Upload an expense CSV", type="csv")

if uploaded_file is None:
    st.info("Upload a CSV with date, category, description, and amount columns to begin.")
    st.stop()

try:
    if st.session_state.get("uploaded_name") != uploaded_file.name:
        st.session_state.csv_path = save_upload(uploaded_file)
        st.session_state.uploaded_name = uploaded_file.name
    load_expenses(st.session_state.csv_path)
    from expense_analyzer import _data  # Used only to display the validated preview.

    expenses = _data()
except ValueError as error:
    st.error(str(error))
    st.stop()

st.subheader("Preview")
st.dataframe(expenses.head(), use_container_width=True)

summary = get_expense_summary()
col1, col2, col3 = st.columns(3)
col1.metric("Total Spending", f"${summary['total_expenses']:,.2f}")
col2.metric("Number of Transactions", summary["transaction_count"])
col3.metric("Average Expense", f"${summary['average_expense']:,.2f}")

st.subheader("Spending by Category")
category_totals = pd.DataFrame(group_by_category())
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.caption("Bar chart")
    st.bar_chart(category_totals, x="category", y="amount", color="#4F46E5")

with chart_col2:
    st.caption("Pie chart")
    pie_totals = category_totals[category_totals["amount"] > 0]
    if pie_totals.empty:
        st.info("A pie chart needs at least one category with positive spending.")
    else:
        if len(pie_totals) != len(category_totals):
            st.info("Categories with zero or negative net spending are not shown in pie charts.")
        figure, axis = plt.subplots()
        axis.pie(
            pie_totals["amount"],
            labels=pie_totals["category"],
            autopct="%1.1f%%",
            startangle=90,
        )
        axis.axis("equal")
        st.pyplot(figure, use_container_width=True)
        plt.close(figure)

question = st.chat_input("Ask a question about your expenses")
if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Analyzing your expenses..."):
            try:
                answer = ask_with_mcp(question, st.session_state.csv_path)
                st.write(answer)
                show_chart_from_question(question, expenses)
            except (ValueError, OpenAIError, json.JSONDecodeError) as error:
                st.error(f"Could not answer the question: {error}")
            except Exception as error:
                st.error(f"Unexpected error while using the expense tools: {readable_error(error)}")
