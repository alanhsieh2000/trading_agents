import math
from typing import Any, Type

import pandas as pd
import yfinance as yf
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class TickerInput(BaseModel):
    """Input schema for ticker-only financial tools."""

    ticker: str = Field(..., description="Ticker symbol, for example AAPL.")


class GetFundamentalsTool(BaseTool):
    name: str = "get_fundamentals"
    description: str = (
        "Fetches a concise company profile, sector, industry, market capitalization, "
        "and common valuation fields for a ticker."
    )
    args_schema: Type[BaseModel] = TickerInput

    def _run(self, ticker: str) -> str:
        return get_fundamentals_text(ticker)


class StatementTool(BaseTool):
    args_schema: Type[BaseModel] = TickerInput
    statement_name: str
    statement_attr: str

    def _run(self, ticker: str) -> str:
        return get_statement_text(ticker, self.statement_name, self.statement_attr)


class GetBalanceSheetTool(StatementTool):
    name: str = "get_balance_sheet"
    description: str = "Fetches the most recent balance sheet statement for a ticker."
    statement_name: str = "Balance sheet"
    statement_attr: str = "balance_sheet"


class GetCashflowTool(StatementTool):
    name: str = "get_cashflow"
    description: str = "Fetches the most recent cash flow statement for a ticker."
    statement_name: str = "Cash flow statement"
    statement_attr: str = "cashflow"


class GetIncomeStatementTool(StatementTool):
    name: str = "get_income_statement"
    description: str = "Fetches the most recent income statement for a ticker."
    statement_name: str = "Income statement"
    statement_attr: str = "income_stmt"


def get_fundamentals_text(ticker: str) -> str:
    symbol = ticker.upper().strip()
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception as exc:
        return f"No fundamentals data available for {symbol}. Upstream error: {exc}"

    if not info:
        return f"No fundamentals data available for {symbol}."

    fields = [
        ("Company", _first_available(info, "longName", "shortName", "displayName")),
        ("Ticker", info.get("symbol") or symbol),
        ("Sector", info.get("sector")),
        ("Industry", info.get("industry")),
        ("Market capitalization", _format_number(info.get("marketCap"))),
        ("Currency", info.get("currency")),
        ("Current price", _format_number(info.get("currentPrice"))),
        ("Trailing PE", _format_number(info.get("trailingPE"))),
        ("Forward PE", _format_number(info.get("forwardPE"))),
        ("Price to book", _format_number(info.get("priceToBook"))),
        ("Enterprise value", _format_number(info.get("enterpriseValue"))),
        ("Trailing EPS", _format_number(info.get("trailingEps"))),
        ("Forward EPS", _format_number(info.get("forwardEps"))),
        ("Dividend yield", _format_dividend_yield(info)),
        ("Beta", _format_number(info.get("beta"))),
    ]
    present = [(label, value) for label, value in fields if value not in (None, "")]
    missing = [label for label, value in fields if value in (None, "")]
    lines = [f"Fundamentals for {symbol}."]
    lines.extend(f"{label}: {value}" for label, value in present)
    if missing:
        lines.append(f"Missing fields: {', '.join(missing)}.")
    return "\n".join(lines)


def get_statement_text(ticker: str, statement_name: str, statement_attr: str) -> str:
    symbol = ticker.upper().strip()
    try:
        ticker_obj = yf.Ticker(symbol)
        statement = getattr(ticker_obj, statement_attr)
    except Exception as exc:
        return f"No {statement_name.lower()} data available for {symbol}. Upstream error: {exc}"

    if statement is None or statement.empty:
        return f"No {statement_name.lower()} data available for {symbol}."

    table = _normalise_statement(statement)
    return (
        f"{statement_name} for {symbol}.\n"
        f"Rows covered: {len(table)}. Periods covered: {max(len(table.columns) - 1, 0)}.\n"
        f"{table.to_csv(index=False).strip()}"
    )


def _normalise_statement(statement: pd.DataFrame) -> pd.DataFrame:
    table = statement.copy()
    table.columns = [_format_period(column) for column in table.columns]
    table.index = [_humanise_label(index) for index in table.index]
    ordered_columns = sorted(table.columns, reverse=True)
    table = table[ordered_columns[:4]]
    table = table.reset_index(names="line_item")
    for column in table.columns:
        if column == "line_item":
            continue
        table[column] = table[column].map(_format_number)
    return table


def _first_available(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _format_period(value: object) -> str:
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def _humanise_label(value: object) -> str:
    text = str(value).replace("_", " ").strip()
    return " ".join(text.split())


def _format_dividend_yield(info: dict[str, Any]) -> str | None:
    """Return dividend yield in the percentage-point units used by Yahoo."""
    for key, multiplier in (
        ("dividendYield", 1.0),
        ("trailingAnnualDividendYield", 100.0),
    ):
        value = info.get(key)
        if value in (None, ""):
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            return _format_number(numeric * multiplier)
    return None


def _format_number(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:.4f}".rstrip("0").rstrip(".")
    return str(value)


get_fundamentals = GetFundamentalsTool()
get_balance_sheet = GetBalanceSheetTool()
get_cashflow = GetCashflowTool()
get_income_statement = GetIncomeStatementTool()
