# AI Expense Analyzer

A small portfolio project for asking questions about an expense CSV in plain English. Upload a file, then ask questions such as “What category did I spend the most on?”

## Features

- Upload an expense CSV and preview its data
- See total spending, transaction count, and average expense
- View spending by category as a bar chart and pie chart
- Request a filtered bar, pie, or line chart in natural language
- Support bank-statement CSVs that record expenses as negative values and Income separately
- Ask natural-language questions about totals, categories, and largest expenses
- Use an OpenAI model to choose MCP tools instead of asking the model to calculate values itself
- Show clear messages for missing files, bad CSV columns, invalid categories, and API problems

## Architecture

```text
Streamlit UI → OpenAI (selects a tool) → MCP client → MCP server → Pandas → result → OpenAI → answer
```

The Streamlit app starts `mcp_server.py` as a local MCP stdio subprocess for each question. It asks the server which tools exist, gives those tool definitions to OpenAI, and executes any requested tool through the MCP client. The server calls the Pandas functions in `expense_analyzer.py` using the uploaded CSV.

## Tech stack

Python, Streamlit, Pandas, the OpenAI Python SDK, and the MCP Python SDK.

> The project pins the MCP SDK to version 1.x because it uses that version's
> straightforward `FastMCP` API. MCP 2.x renamed this API and requires a
> migration.

## What MCP means here

MCP (Model Context Protocol) is a standard way for an AI application to offer tools to a model. Here, the MCP server offers tools such as `total_spending` and `largest_expenses`. OpenAI decides which tool fits the question; the MCP server performs the calculation with Pandas; the tool result is passed back to OpenAI to turn into a readable response. The model does not invent or manually calculate expense totals.

## Project structure

```text
ai-expense-analyzer/
├── app.py                 # Streamlit user interface and MCP client
├── mcp_server.py          # MCP tools exposed over stdio
├── expense_analyzer.py    # Simple Pandas analysis functions
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── sample_expenses.csv
```

## Installation

1. Open a terminal in this folder.
2. Create and activate a virtual environment (recommended):

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

## Configure OpenAI

Copy `.env.example` to `.env`, then replace the placeholder with your API key:

```env
OPENAI_API_KEY=your_api_key_here
```

Never commit `.env`; it is already listed in `.gitignore`.

## Run the project

```powershell
streamlit run app.py
```

Upload `sample_expenses.csv` in the browser, or upload a file with exactly these columns:

```text
date,category,description,amount
```

## Example questions

- How much did I spend in total?
- How much did I spend on food?
- What category did I spend the most on?
- Show my expenses by category.
- What are my 5 biggest expenses?
- Show Bills and Food only as a line chart.
- Create a pie chart for Food, Transport, and Entertainment.

## Example output

For a total question, the assistant might respond: “You spent $1,xxx.xx across 30 transactions.” Exact values depend on the uploaded CSV.

## Future improvements

- Add date-range tools and monthly summaries
- Let users download a filtered result
- Add charts after the core tool flow is established
