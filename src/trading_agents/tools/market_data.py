from typing import Type

import pandas as pd
import yfinance as yf
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from stockstats import StockDataFrame


ALLOWED_INDICATORS = {
    "close_50_sma",
    "close_200_sma",
    "close_10_ema",
    "macd",
    "macds",
    "macdh",
    "rsi",
    "boll",
    "boll_ub",
    "boll_lb",
    "atr",
    "vwma",
}


class StockDataInput(BaseModel):
    """Input schema for stock price history."""

    ticker: str = Field(..., description="Ticker symbol, for example AAPL.")
    start_date: str = Field(..., description="Inclusive start date in YYYY-MM-DD format.")
    end_date: str = Field(..., description="Exclusive end date in YYYY-MM-DD format.")


class IndicatorInput(BaseModel):
    """Input schema for technical indicator calculations."""

    ticker: str = Field(..., description="Ticker symbol, for example AAPL.")
    start_date: str = Field(..., description="Inclusive start date in YYYY-MM-DD format.")
    end_date: str = Field(..., description="Exclusive end date in YYYY-MM-DD format.")
    indicators: list[str] | str = Field(
        ...,
        description="Requested indicator names. May be a list or comma-separated string.",
    )


class GetStockDataTool(BaseTool):
    name: str = "get_stock_data"
    description: str = (
        "Fetches historical stock price data for a ticker over a date range. "
        "Returns compact CSV text with date, OHLC, adjusted close when available, and volume."
    )
    args_schema: Type[BaseModel] = StockDataInput

    def _run(self, ticker: str, start_date: str, end_date: str) -> str:
        return get_stock_data_text(ticker, start_date, end_date)


class GetIndicatorsTool(BaseTool):
    name: str = "get_indicators"
    description: str = (
        "Computes requested technical indicators for a ticker over a date range. "
        f"Allowed indicators: {', '.join(sorted(ALLOWED_INDICATORS))}."
    )
    args_schema: Type[BaseModel] = IndicatorInput

    def _run(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        indicators: list[str] | str,
    ) -> str:
        return get_indicators_text(ticker, start_date, end_date, indicators)


def get_stock_data_text(ticker: str, start_date: str, end_date: str) -> str:
    symbol = ticker.upper().strip()
    try:
        history = yf.download(
            symbol,
            start=start_date,
            end=end_date,
            progress=False,
            auto_adjust=False,
        )
    except Exception as exc:
        return (
            f"No price data available for {symbol} between {start_date} and {end_date}. "
            f"Upstream error: {exc}"
        )

    if history is None or history.empty:
        return f"No price data available for {symbol} between {start_date} and {end_date}."

    prices = _normalise_price_history(history, symbol)
    if prices.empty:
        return f"No price data available for {symbol} between {start_date} and {end_date}."

    columns = [
        column
        for column in ["date", "open", "high", "low", "close", "adj_close", "volume"]
        if column in prices.columns
    ]
    csv_text = _to_compact_csv(prices[columns])
    missing = sorted({"open", "high", "low", "close", "volume"} - set(prices.columns))
    warning = ""
    if missing:
        warning = f"\nWarning: missing columns: {', '.join(missing)}."

    return (
        f"Stock data for {symbol} from {start_date} to {end_date}.\n"
        f"Rows covered: {len(prices)}.\n"
        f"{csv_text.strip()}"
        f"{warning}"
    )


def get_indicators_text(
    ticker: str,
    start_date: str,
    end_date: str,
    indicators: list[str] | str,
) -> str:
    symbol = ticker.upper().strip()
    requested = _normalise_indicator_names(indicators)
    invalid = sorted(set(requested) - ALLOWED_INDICATORS)
    if invalid:
        return (
            "Validation error: unsupported indicators: "
            f"{', '.join(invalid)}. Allowed indicators: "
            f"{', '.join(sorted(ALLOWED_INDICATORS))}."
        )
    if not requested:
        return (
            "Validation error: no indicators requested. Allowed indicators: "
            f"{', '.join(sorted(ALLOWED_INDICATORS))}."
        )

    try:
        history = yf.download(
            symbol,
            start=start_date,
            end=end_date,
            progress=False,
            auto_adjust=False,
        )
    except Exception as exc:
        return (
            f"No price data available for {symbol} between {start_date} and {end_date}. "
            f"Upstream error: {exc}"
        )

    if history is None or history.empty:
        return f"No price data available for {symbol} between {start_date} and {end_date}."

    prices = _normalise_price_history(history, symbol)
    required = {"open", "high", "low", "close", "volume"}
    missing = sorted(required - set(prices.columns))
    if missing:
        return f"Cannot compute indicators for {symbol}: missing columns {', '.join(missing)}."

    stock_df = prices.set_index("date")[["open", "high", "low", "close", "volume"]].copy()
    stock_df = StockDataFrame.retype(stock_df)
    for indicator in requested:
        stock_df[indicator]

    output = pd.DataFrame(stock_df[["close", *requested]].copy()).reset_index()
    if "date" not in output.columns:
        output = output.rename(columns={output.columns[0]: "date"})
    output = output[["date", "close", *requested]]
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")

    return (
        f"Technical indicators for {symbol} from {start_date} to {end_date}.\n"
        f"Rows covered: {len(output)}.\n"
        f"Requested indicators: {', '.join(requested)}.\n"
        f"{_to_compact_csv(output).strip()}"
    )


def _normalise_indicator_names(indicators: list[str] | str) -> list[str]:
    if isinstance(indicators, str):
        names = indicators.replace(";", ",").split(",")
    else:
        names = indicators
    return [name.strip().lower() for name in names if name and name.strip()]


def _normalise_price_history(history: pd.DataFrame, ticker: str) -> pd.DataFrame:
    frame = history.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        upper_ticker = ticker.upper()
        last_level = [str(value).upper() for value in frame.columns.get_level_values(-1)]
        if upper_ticker in last_level:
            frame = frame.xs(upper_ticker, axis=1, level=-1, drop_level=True)
        elif len(set(last_level)) == 1:
            frame.columns = frame.columns.get_level_values(0)
        else:
            frame.columns = [
                "_".join(str(part) for part in column if part)
                for column in frame.columns.to_flat_index()
            ]

    frame = frame.rename(columns={column: _normalise_column_name(column) for column in frame.columns})
    frame = frame.reset_index()
    date_column = _find_date_column(frame.columns)
    frame = frame.rename(columns={date_column: "date"})
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    frame = frame.sort_values("date")
    return frame


def _normalise_column_name(column: object) -> str:
    return str(column).strip().lower().replace(" ", "_").replace("-", "_")


def _find_date_column(columns: pd.Index) -> str:
    for column in columns:
        if str(column).lower() in {"date", "datetime"}:
            return str(column)
    return str(columns[0])


def _to_compact_csv(frame: pd.DataFrame) -> str:
    formatted = frame.copy()
    for column in formatted.columns:
        if column == "date":
            continue
        formatted[column] = formatted[column].map(_format_value)
    return formatted.to_csv(index=False)


def _format_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:.4f}".rstrip("0").rstrip(".")
    return str(value)


get_stock_data = GetStockDataTool()
get_indicators = GetIndicatorsTool()
