"""Point-in-time SEC sources for evaluation fundamentals payloads."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

import requests
from dotenv import load_dotenv


load_dotenv()

SEC_RAW_DIR = Path("data/raw-backtest/SEC")
SEC_USER_AGENT_ENV = "SEC_UA"
SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"
SEC_FORMS = frozenset({"10-K", "10-Q"})
SEC_REQUEST_DELAY_SECONDS = 0.2
SEC_REQUEST_TIMEOUT_SECONDS = 30
SEC_MAX_ATTEMPTS = 3
SEC_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
SEC_MANIFEST_VERSION = 1


@dataclass(frozen=True)
class SecFiling:
    ticker: str
    cik: str
    accession_number: str
    form: str
    filing_date: date
    report_date: date
    primary_document: str


@dataclass(frozen=True)
class SecArchive:
    raw_dir: Path
    filings_by_ticker: dict[str, tuple[SecFiling, ...]]
    company_facts_by_ticker: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class SecFact:
    concept: str
    value: float
    unit: str
    start_date: date | None
    end_date: date


@dataclass(frozen=True)
class BalanceSheetLine:
    label: str
    concepts: tuple[str, ...]
    required: bool = False


@dataclass(frozen=True)
class CashFlowLine:
    label: str
    concepts: tuple[str, ...]
    required: bool = False


@dataclass(frozen=True)
class CashFlowPeriod:
    start_date: date
    end_date: date


BALANCE_SHEET_LINES = (
    BalanceSheetLine(
        "Cash and cash equivalents", ("CashAndCashEquivalentsAtCarryingValue",)
    ),
    BalanceSheetLine(
        "Marketable securities",
        ("MarketableSecuritiesCurrent", "ShortTermInvestments"),
    ),
    BalanceSheetLine("Accounts receivable, net", ("AccountsReceivableNetCurrent",)),
    BalanceSheetLine("Inventories", ("InventoryNet",)),
    BalanceSheetLine("Total current assets", ("AssetsCurrent",)),
    BalanceSheetLine(
        "Property, plant and equipment, net",
        (
            "PropertyPlantAndEquipmentNet",
            "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
        ),
    ),
    BalanceSheetLine(
        "Operating lease right-of-use assets", ("OperatingLeaseRightOfUseAsset",)
    ),
    BalanceSheetLine("Goodwill", ("Goodwill",)),
    BalanceSheetLine(
        "Intangible assets, net",
        ("FiniteLivedIntangibleAssetsNet", "IntangibleAssetsNetExcludingGoodwill"),
    ),
    BalanceSheetLine("Total assets", ("Assets",), required=True),
    BalanceSheetLine("Accounts payable", ("AccountsPayableCurrent",)),
    BalanceSheetLine(
        "Short-term debt",
        ("ShortTermBorrowings", "ShortTermDebtCurrent", "LongTermDebtCurrent"),
    ),
    BalanceSheetLine(
        "Operating lease liabilities, current",
        ("OperatingLeaseLiabilityCurrent",),
    ),
    BalanceSheetLine("Total current liabilities", ("LiabilitiesCurrent",)),
    BalanceSheetLine("Long-term debt", ("LongTermDebtNoncurrent",)),
    BalanceSheetLine(
        "Operating lease liabilities, noncurrent",
        ("OperatingLeaseLiabilityNoncurrent",),
    ),
    BalanceSheetLine(
        "Common stock and additional paid-in capital",
        (
            "CommonStocksIncludingAdditionalPaidInCapital",
            "AdditionalPaidInCapital",
            "CommonStockValue",
        ),
    ),
    BalanceSheetLine(
        "Retained earnings (accumulated deficit)",
        ("RetainedEarningsAccumulatedDeficit",),
    ),
    BalanceSheetLine(
        "Accumulated other comprehensive income (loss)",
        ("AccumulatedOtherComprehensiveIncomeLossNetOfTax",),
    ),
    BalanceSheetLine("Stockholders' equity", ("StockholdersEquity",), required=True),
    BalanceSheetLine(
        "Total liabilities and stockholders' equity",
        ("LiabilitiesAndStockholdersEquity",),
        required=True,
    ),
)

CASH_FLOW_LINES = (
    CashFlowLine("Net income", ("NetIncomeLoss",), required=True),
    CashFlowLine(
        "Depreciation and amortization",
        ("DepreciationDepletionAndAmortization", "Depreciation"),
    ),
    CashFlowLine(
        "Share-based compensation",
        ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
    ),
    CashFlowLine(
        "Change in accounts receivable and other operating assets",
        (
            "IncreaseDecreaseInAccountsReceivable",
            "IncreaseDecreaseInAccountsReceivableAndOtherOperatingAssets",
        ),
    ),
    CashFlowLine("Change in inventories", ("IncreaseDecreaseInInventories",)),
    CashFlowLine(
        "Change in accounts payable", ("IncreaseDecreaseInAccountsPayable",)
    ),
    CashFlowLine(
        "Net cash provided by operating activities",
        ("NetCashProvidedByUsedInOperatingActivities",),
        required=True,
    ),
    CashFlowLine(
        "Capital expenditures",
        (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
        ),
        required=True,
    ),
    CashFlowLine(
        "Net cash provided by (used in) investing activities",
        ("NetCashProvidedByUsedInInvestingActivities",),
        required=True,
    ),
    CashFlowLine(
        "Common stock repurchases", ("PaymentsForRepurchaseOfCommonStock",)
    ),
    CashFlowLine("Dividends paid", ("PaymentsOfDividends",)),
    CashFlowLine(
        "Net cash provided by (used in) financing activities",
        ("NetCashProvidedByUsedInFinancingActivities",),
        required=True,
    ),
    CashFlowLine(
        "Effect of exchange rates",
        (
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations",
            "EffectOfExchangeRateOnCashAndCashEquivalents",
        ),
    ),
    CashFlowLine(
        "Net change in cash",
        (
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            "CashAndCashEquivalentsPeriodIncreaseDecrease",
        ),
        required=True,
    ),
)


class _SecClient:
    def __init__(
        self,
        user_agent: str,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        request_delay_seconds: float = SEC_REQUEST_DELAY_SECONDS,
    ) -> None:
        self._user_agent = user_agent
        self._session = session or requests.Session()
        self._sleep = sleep
        self._request_delay_seconds = max(request_delay_seconds, 0.0)
        self._made_request = False

    def get(self, url: str) -> bytes:
        for attempt in range(1, SEC_MAX_ATTEMPTS + 1):
            if self._made_request and self._request_delay_seconds:
                self._sleep(self._request_delay_seconds)
            self._made_request = True
            response = self._session.get(
                url,
                headers={"User-Agent": self._user_agent},
                timeout=SEC_REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code < 400:
                if not response.content:
                    raise RuntimeError(f"SEC returned an empty response for {url}.")
                return response.content
            if (
                response.status_code not in SEC_RETRY_STATUSES
                or attempt == SEC_MAX_ATTEMPTS
            ):
                raise RuntimeError(
                    f"SEC request failed with HTTP {response.status_code} for {url}."
                )
            retry_after = response.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after is not None else float(attempt)
            except ValueError:
                wait = float(attempt)
            self._sleep(max(wait, 0.0))
        raise AssertionError("unreachable")


def ensure_sec_archive(
    tickers: Sequence[str],
    trade_dates: Sequence[str],
    *,
    raw_dir: Path = SEC_RAW_DIR,
    session: requests.Session | None = None,
    sleep: Callable[[float], None] = time.sleep,
    request_delay_seconds: float = SEC_REQUEST_DELAY_SECONDS,
) -> SecArchive:
    """Load a valid SEC archive, downloading it atomically when absent."""
    symbols = _normalise_tickers(tickers)
    dates = _normalise_dates(trade_dates)
    if not symbols or not dates:
        raise ValueError("SEC archive requires at least one ticker and trade date.")
    if raw_dir.exists():
        return load_sec_archive(symbols, dates, raw_dir=raw_dir)

    user_agent = os.environ.get(SEC_USER_AGENT_ENV, "").strip()
    if not user_agent:
        raise RuntimeError(
            f"{SEC_USER_AGENT_ENV} is required to download SEC evaluation filings."
        )
    raw_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{raw_dir.name}-", dir=str(raw_dir.parent))
    )
    client = _SecClient(
        user_agent,
        session=session,
        sleep=sleep,
        request_delay_seconds=request_delay_seconds,
    )
    manifest_files: list[dict[str, Any]] = []
    try:
        ticker_payload = _download_json(
            client,
            SEC_TICKER_URL,
            staging / "company_tickers.json",
            staging,
            manifest_files,
        )
        cik_by_ticker = _ticker_cik_map(ticker_payload)
        for ticker in symbols:
            cik = cik_by_ticker.get(ticker)
            if cik is None:
                raise RuntimeError(f"SEC ticker mapping has no CIK for {ticker}.")
            ticker_dir = staging / ticker
            submissions_url = SEC_SUBMISSIONS_URL.format(cik=cik)
            facts_url = SEC_COMPANY_FACTS_URL.format(cik=cik)
            submissions = _download_json(
                client,
                submissions_url,
                ticker_dir / "submissions.json",
                staging,
                manifest_files,
            )
            _download_json(
                client,
                facts_url,
                ticker_dir / "companyfacts.json",
                staging,
                manifest_files,
            )
            filings = _active_filings(ticker, cik, submissions, dates)
            for filing in filings:
                _download_filing(client, filing, staging, manifest_files)

        manifest = {
            "version": SEC_MANIFEST_VERSION,
            "files": sorted(manifest_files, key=lambda item: item["path"]),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(staging, raw_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return load_sec_archive(symbols, dates, raw_dir=raw_dir)


def load_sec_archive(
    tickers: Sequence[str],
    trade_dates: Sequence[str],
    *,
    raw_dir: Path = SEC_RAW_DIR,
) -> SecArchive:
    """Validate and load a previously downloaded SEC archive."""
    symbols = _normalise_tickers(tickers)
    dates = _normalise_dates(trade_dates)
    manifest_path = raw_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"SEC archive manifest is missing: {manifest_path}")
    manifest = _read_json(manifest_path)
    if manifest.get("version") != SEC_MANIFEST_VERSION:
        raise RuntimeError(
            f"Unsupported SEC archive manifest version in {manifest_path}."
        )
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError(f"SEC archive manifest has no files: {manifest_path}")
    expected_paths: set[Path] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"Malformed SEC archive manifest entry in {manifest_path}."
            )
        relative = _safe_relative_path(entry.get("path"))
        expected_paths.add(relative)
        path = raw_dir / relative
        if not path.is_file():
            raise RuntimeError(f"SEC archive file is missing: {path}")
        content = path.read_bytes()
        if len(content) != entry.get("size") or _sha256(content) != entry.get("sha256"):
            raise RuntimeError(f"SEC archive file failed integrity validation: {path}")

    actual_paths = {
        path.relative_to(raw_dir)
        for path in raw_dir.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual_paths != expected_paths:
        raise RuntimeError("SEC archive contains unmanifested or missing files.")

    mapping = _ticker_cik_map(_read_json(raw_dir / "company_tickers.json"))
    filings_by_ticker: dict[str, tuple[SecFiling, ...]] = {}
    facts_by_ticker: dict[str, dict[str, Any]] = {}
    for ticker in symbols:
        cik = mapping.get(ticker)
        if cik is None:
            raise RuntimeError(f"SEC archive has no CIK for {ticker}.")
        submissions = _read_json(raw_dir / ticker / "submissions.json")
        if str(submissions.get("cik", "")).zfill(10) != cik:
            raise RuntimeError(f"SEC submissions CIK mismatch for {ticker}.")
        filings = _active_filings(ticker, cik, submissions, dates)
        for filing in filings:
            filing_dir = raw_dir / ticker / filing.accession_number
            _validate_filing_directory(filing, filing_dir)
        company_facts = _read_json(raw_dir / ticker / "companyfacts.json")
        if str(company_facts.get("cik", "")).zfill(10) != cik:
            raise RuntimeError(f"SEC Company Facts CIK mismatch for {ticker}.")
        filings_by_ticker[ticker] = filings
        facts_by_ticker[ticker] = company_facts
    return SecArchive(raw_dir, filings_by_ticker, facts_by_ticker)


def render_point_in_time_fundamentals(
    archive: SecArchive,
    ticker: str,
    as_of_date: str,
    prices: Sequence[tuple[str, float]],
) -> str:
    """Render fundamentals known strictly before one evaluation trade date."""
    symbol = ticker.upper().strip()
    cutoff = _parse_date(as_of_date)
    filing = _latest_filing_before(archive, symbol, cutoff)
    company_facts = archive.company_facts_by_ticker[symbol]

    price_rows = [
        (_parse_date(day), float(close))
        for day, close in prices
        if _parse_date(day) < cutoff
    ]
    if not price_rows:
        raise RuntimeError(f"No prior close for {symbol} before {as_of_date}.")
    price_date, prior_close = max(price_rows, key=lambda item: item[0])
    if not math.isfinite(prior_close) or prior_close <= 0:
        raise RuntimeError(f"Invalid prior close for {symbol} before {as_of_date}.")

    revenue = _duration_fact(
        company_facts,
        filing,
        ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"),
        "USD",
    )
    net_income = _duration_fact(company_facts, filing, ("NetIncomeLoss",), "USD")
    diluted_eps = _duration_fact(
        company_facts, filing, ("EarningsPerShareDiluted",), "USD/shares"
    )
    assets = _instant_fact(company_facts, filing, ("Assets",), "USD")
    equity = _instant_fact(
        company_facts,
        filing,
        (
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
        "USD",
    )
    cash = _instant_fact(
        company_facts,
        filing,
        ("CashAndCashEquivalentsAtCarryingValue",),
        "USD",
    )
    shares = _shares_fact(company_facts, filing)
    liabilities = _instant_fact(
        company_facts, filing, ("Liabilities",), "USD", required=False
    )
    liabilities_derived = liabilities is None
    if liabilities is None:
        liabilities = SecFact(
            concept="Assets minus StockholdersEquity",
            value=assets.value - equity.value,
            unit="USD",
            start_date=None,
            end_date=assets.end_date,
        )
    if liabilities.value < 0 or shares.value <= 0 or equity.value <= 0:
        raise RuntimeError(
            f"Invalid SEC fundamentals values for {symbol} on {as_of_date}."
        )

    market_cap = round(prior_close * shares.value)
    price_to_book = market_cap / equity.value
    period_label = "annual" if filing.form == "10-K" else "quarter"
    lines = [
        f"Point-in-time fundamentals for {symbol} as of {as_of_date}.",
        f"Ticker: {symbol}",
        f"CIK: {filing.cik}",
        "Source: SEC EDGAR Company Facts and archived filing package.",
        (
            f"Source filing: {filing.form} filed {filing.filing_date.isoformat()}, "
            f"period ended {filing.report_date.isoformat()}, accession "
            f"{filing.accession_number}."
        ),
        f"Prior close: {_format_number(prior_close)} USD on {price_date.isoformat()}.",
        f"Revenue ({period_label}): {_format_number(revenue.value)} USD.",
        f"Net income ({period_label}): {_format_number(net_income.value)} USD.",
        f"Diluted EPS ({period_label}): {_format_number(diluted_eps.value)} USD/share.",
        f"Assets: {_format_number(assets.value)} USD.",
        (
            f"Liabilities{' (derived as assets minus equity)' if liabilities_derived else ''}: "
            f"{_format_number(liabilities.value)} USD."
        ),
        f"Stockholders' equity: {_format_number(equity.value)} USD.",
        f"Cash and cash equivalents: {_format_number(cash.value)} USD.",
        (
            f"Shares outstanding: {_format_number(shares.value)} shares as of "
            f"{shares.end_date.isoformat()}."
        ),
        f"Estimated market capitalization: {_format_number(market_cap)} USD.",
        f"Estimated price to book: {_format_number(price_to_book)}.",
        (
            "Unavailable point-in-time fields: Company, Sector, Industry, Forward PE, "
            "Forward EPS, Trailing PE, Enterprise value, Beta, Dividend yield."
        ),
    ]
    return "\n".join(lines)


def render_point_in_time_balance_sheet(
    archive: SecArchive,
    ticker: str,
    as_of_date: str,
) -> str:
    """Render the latest balance sheet disclosed before one replay date."""
    symbol = ticker.upper().strip()
    cutoff = _parse_date(as_of_date)
    filing = _latest_filing_before(archive, symbol, cutoff)
    company_facts = archive.company_facts_by_ticker[symbol]

    asset_facts = [
        fact
        for fact in _fact_candidates(company_facts, filing, ("Assets",), "USD")
        if fact.start_date is None and fact.end_date <= filing.report_date
    ]
    periods = tuple(sorted({fact.end_date for fact in asset_facts}, reverse=True)[:2])
    if not periods or periods[0] != filing.report_date:
        raise RuntimeError(
            f"SEC filing {filing.accession_number} has no current balance-sheet period."
        )

    rendered_rows: list[tuple[str, list[str]]] = []
    facts_by_label: dict[str, list[SecFact | None]] = {}
    for line in BALANCE_SHEET_LINES:
        facts = [
            _instant_fact_for_period(
                company_facts,
                filing,
                line.concepts,
                period,
                required=line.required and period == periods[0],
            )
            for period in periods
        ]
        if any(fact is not None for fact in facts):
            facts_by_label[line.label] = facts
            rendered_rows.append(
                (
                    line.label,
                    [
                        "" if fact is None else _format_number(fact.value)
                        for fact in facts
                    ],
                )
            )

    assets = facts_by_label["Total assets"]
    equity = facts_by_label["Stockholders' equity"]
    liabilities_and_equity = facts_by_label[
        "Total liabilities and stockholders' equity"
    ]
    liabilities: list[SecFact | None] = [
        _instant_fact_for_period(
            company_facts,
            filing,
            ("Liabilities",),
            period,
            required=False,
        )
        for period in periods
    ]
    liabilities_derived = False
    for index, period in enumerate(periods):
        if (
            liabilities[index] is None
            and assets[index] is not None
            and equity[index] is not None
        ):
            liabilities[index] = SecFact(
                concept="Assets minus StockholdersEquity",
                value=assets[index].value - equity[index].value,
                unit="USD",
                start_date=None,
                end_date=period,
            )
            liabilities_derived = True
    if liabilities[0] is None:
        raise RuntimeError(
            f"SEC filing {filing.accession_number} has no usable total liabilities."
        )

    for index, period in enumerate(periods):
        period_assets = assets[index]
        period_equity = equity[index]
        period_liabilities = liabilities[index]
        period_total = liabilities_and_equity[index]
        if period_assets is None or period_total is None:
            continue
        tolerance = max(1.0, abs(period_assets.value) * 1e-9)
        if abs(period_assets.value - period_total.value) > tolerance:
            raise RuntimeError(
                f"SEC filing {filing.accession_number} has an unbalanced statement "
                f"for {period.isoformat()}."
            )
        if period_liabilities is not None and period_liabilities.value < 0:
            raise RuntimeError(
                f"SEC filing {filing.accession_number} has negative liabilities "
                f"for {period.isoformat()}."
            )
        if (
            period_liabilities is not None
            and period_equity is not None
            and abs(
                period_assets.value
                - period_liabilities.value
                - period_equity.value
            )
            > tolerance
        ):
            raise RuntimeError(
                f"SEC filing {filing.accession_number} has inconsistent accounting "
                f"totals for {period.isoformat()}."
            )

    liabilities_label = "Total liabilities"
    if liabilities_derived:
        liabilities_label += " (derived as assets minus equity where unavailable)"
    liability_row = (
        liabilities_label,
        ["" if fact is None else _format_number(fact.value) for fact in liabilities],
    )
    equity_index = next(
        index
        for index, (label, _) in enumerate(rendered_rows)
        if label == "Stockholders' equity"
    )
    rendered_rows.insert(equity_index, liability_row)

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("line_item", *(period.isoformat() for period in periods)))
    for label, values in rendered_rows:
        writer.writerow((label, *values))
    table = output.getvalue().strip()
    return "\n".join(
        (
            f"Point-in-time balance sheet for {symbol} as of {as_of_date}.",
            "Source: SEC EDGAR Company Facts and archived filing package.",
            (
                f"Source filing: {filing.form} filed {filing.filing_date.isoformat()}, "
                f"period ended {filing.report_date.isoformat()}, accession "
                f"{filing.accession_number}."
            ),
            (
                f"Rows covered: {len(rendered_rows)}. "
                f"Periods covered: {len(periods)}. Values are USD."
            ),
            table,
        )
    )


def render_point_in_time_cashflow(
    archive: SecArchive,
    ticker: str,
    as_of_date: str,
) -> str:
    """Render the latest cash-flow statement disclosed before one replay date."""
    symbol = ticker.upper().strip()
    cutoff = _parse_date(as_of_date)
    filing = _latest_filing_before(archive, symbol, cutoff)
    company_facts = archive.company_facts_by_ticker[symbol]
    periods = _cash_flow_periods(company_facts, filing)

    rendered_rows: list[tuple[str, list[str]]] = []
    facts_by_label: dict[str, list[SecFact | None]] = {}
    for line in CASH_FLOW_LINES:
        facts = [
            _duration_fact_for_period(
                company_facts,
                filing,
                line.concepts,
                period,
                required=line.required,
            )
            for period in periods
        ]
        if any(fact is not None for fact in facts):
            facts_by_label[line.label] = facts
            rendered_rows.append(
                (
                    line.label,
                    [
                        "" if fact is None else _format_number(fact.value)
                        for fact in facts
                    ],
                )
            )

    operating = facts_by_label["Net cash provided by operating activities"]
    capital_expenditures = facts_by_label["Capital expenditures"]
    free_cash_flow = [
        operating[index].value - capital_expenditures[index].value
        for index in range(len(periods))
    ]
    capital_expenditure_index = next(
        index
        for index, (label, _) in enumerate(rendered_rows)
        if label == "Capital expenditures"
    )
    rendered_rows.insert(
        capital_expenditure_index + 1,
        (
            "Free cash flow (derived as operating cash flow minus capital expenditures)",
            [_format_number(value) for value in free_cash_flow],
        ),
    )

    investing = facts_by_label[
        "Net cash provided by (used in) investing activities"
    ]
    financing = facts_by_label[
        "Net cash provided by (used in) financing activities"
    ]
    exchange_rates = facts_by_label.get("Effect of exchange rates")
    net_change = facts_by_label["Net change in cash"]
    for index, period in enumerate(periods):
        exchange_rate = (
            0.0
            if exchange_rates is None or exchange_rates[index] is None
            else exchange_rates[index].value
        )
        reconciled_change = (
            operating[index].value
            + investing[index].value
            + financing[index].value
            + exchange_rate
        )
        tolerance = max(1.0, abs(net_change[index].value) * 1e-9)
        if abs(reconciled_change - net_change[index].value) > tolerance:
            raise RuntimeError(
                f"SEC filing {filing.accession_number} has an unreconciled cash "
                f"change for {_format_cash_flow_period(period)}."
            )

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        ("line_item", *(_format_cash_flow_period(period) for period in periods))
    )
    for label, values in rendered_rows:
        writer.writerow((label, *values))
    table = output.getvalue().strip()
    return "\n".join(
        (
            f"Point-in-time cash flow statement for {symbol} as of {as_of_date}.",
            "Source: SEC EDGAR Company Facts and archived filing package.",
            (
                f"Source filing: {filing.form} filed {filing.filing_date.isoformat()}, "
                f"period ended {filing.report_date.isoformat()}, accession "
                f"{filing.accession_number}."
            ),
            (
                f"Rows covered: {len(rendered_rows)}. "
                f"Periods covered: {len(periods)}. Values are USD."
            ),
            "Cash-outflow payment lines are shown as positive amounts as reported by SEC.",
            table,
        )
    )


def _cash_flow_periods(
    company_facts: dict[str, Any], filing: SecFiling
) -> tuple[CashFlowPeriod, ...]:
    anchors = [
        fact
        for fact in _fact_candidates(
            company_facts,
            filing,
            ("NetCashProvidedByUsedInOperatingActivities",),
            "USD",
        )
        if fact.start_date is not None
    ]
    current_candidates = [
        fact
        for fact in anchors
        if fact.end_date == filing.report_date
        and (
            300 <= (fact.end_date - fact.start_date).days <= 400
            if filing.form == "10-K"
            else 60 <= (fact.end_date - fact.start_date).days <= 300
        )
    ]
    if not current_candidates:
        raise RuntimeError(
            f"SEC filing {filing.accession_number} has no current cash-flow period."
        )
    if filing.form == "10-K":
        current = min(
            current_candidates,
            key=lambda fact: abs((fact.end_date - fact.start_date).days - 365),
        )
    else:
        current = max(
            current_candidates,
            key=lambda fact: (fact.end_date - fact.start_date).days,
        )
    target_days = (current.end_date - current.start_date).days

    candidates: set[CashFlowPeriod] = set()
    for fact in anchors:
        duration_days = (fact.end_date - fact.start_date).days
        matching_duration = (
            300 <= duration_days <= 400
            if filing.form == "10-K"
            else abs(duration_days - target_days) <= 15
        )
        if matching_duration:
            candidates.add(CashFlowPeriod(fact.start_date, fact.end_date))
    limit = 3 if filing.form == "10-K" else 2
    periods = tuple(
        sorted(
            candidates,
            key=lambda period: (period.end_date, period.start_date),
            reverse=True,
        )[:limit]
    )
    if not periods or periods[0] != CashFlowPeriod(
        current.start_date, current.end_date
    ):
        raise RuntimeError(
            f"SEC filing {filing.accession_number} has ambiguous cash-flow periods."
        )
    return periods


def _format_cash_flow_period(period: CashFlowPeriod) -> str:
    return f"{period.start_date.isoformat()}..{period.end_date.isoformat()}"


def _latest_filing_before(archive: SecArchive, symbol: str, cutoff: date) -> SecFiling:
    filings = archive.filings_by_ticker.get(symbol, ())
    eligible = [filing for filing in filings if filing.filing_date < cutoff]
    if not eligible:
        raise RuntimeError(f"No SEC filing for {symbol} before {cutoff.isoformat()}.")
    return max(eligible, key=lambda item: (item.filing_date, item.accession_number))


def _download_json(
    client: _SecClient,
    url: str,
    path: Path,
    root: Path,
    manifest_files: list[dict[str, Any]],
) -> dict[str, Any]:
    content = client.get(url)
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"SEC returned malformed JSON for {url}.") from exc
    _write_download(path, content, url, root, manifest_files)
    if not isinstance(payload, dict):
        raise RuntimeError(f"SEC returned a non-object JSON payload for {url}.")
    return payload


def _download_filing(
    client: _SecClient,
    filing: SecFiling,
    root: Path,
    manifest_files: list[dict[str, Any]],
) -> None:
    accession_path = filing.accession_number.replace("-", "")
    base_url = SEC_ARCHIVE_URL.format(cik=int(filing.cik), accession=accession_path)
    filing_dir = root / filing.ticker / filing.accession_number
    index_url = f"{base_url}/index.json"
    index = _download_json(
        client, index_url, filing_dir / "index.json", root, manifest_files
    )
    directory = index.get("directory")
    items = directory.get("item") if isinstance(directory, dict) else None
    if not isinstance(items, list):
        raise RuntimeError(f"Malformed SEC filing index for {filing.accession_number}.")
    names = [item.get("name") for item in items if isinstance(item, dict)]
    artifact_names = sorted(
        {
            name
            for name in names
            if isinstance(name, str)
            and (
                name == filing.primary_document
                or name.lower().endswith(".xsd")
                or name.lower().endswith(
                    ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")
                )
            )
        }
    )
    required_suffixes = (".xsd", "_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")
    if filing.primary_document not in artifact_names or any(
        not any(name.lower().endswith(suffix) for name in artifact_names)
        for suffix in required_suffixes
    ):
        raise RuntimeError(
            f"SEC filing {filing.accession_number} lacks required inline-XBRL artifacts."
        )
    for name in artifact_names:
        if Path(name).name != name:
            raise RuntimeError(f"Unsafe SEC filing artifact name: {name}")
        url = f"{base_url}/{name}"
        content = client.get(url)
        _write_download(filing_dir / name, content, url, root, manifest_files)


def _write_download(
    path: Path,
    content: bytes,
    url: str,
    root: Path,
    manifest_files: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    manifest_files.append(
        {
            "path": path.relative_to(root).as_posix(),
            "url": url,
            "size": len(content),
            "sha256": _sha256(content),
        }
    )


def _ticker_cik_map(payload: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for record in payload.values():
        if not isinstance(record, dict):
            continue
        ticker = str(record.get("ticker", "")).upper().strip()
        cik = str(record.get("cik_str", "")).strip()
        if ticker and cik.isdigit():
            mapping[ticker] = cik.zfill(10)
    if not mapping:
        raise RuntimeError("SEC ticker mapping contains no valid records.")
    return mapping


def _active_filings(
    ticker: str,
    cik: str,
    submissions: dict[str, Any],
    trade_dates: Sequence[date],
) -> tuple[SecFiling, ...]:
    filings = _parse_filings(ticker, cik, submissions)
    selected: dict[str, SecFiling] = {}
    for trade_date in trade_dates:
        eligible = [filing for filing in filings if filing.filing_date < trade_date]
        if not eligible:
            raise RuntimeError(f"No SEC 10-K/10-Q for {ticker} before {trade_date}.")
        filing = max(
            eligible, key=lambda item: (item.filing_date, item.accession_number)
        )
        selected[filing.accession_number] = filing
    return tuple(
        sorted(
            selected.values(),
            key=lambda item: (item.filing_date, item.accession_number),
        )
    )


def _parse_filings(
    ticker: str, cik: str, submissions: dict[str, Any]
) -> tuple[SecFiling, ...]:
    recent = submissions.get("filings", {}).get("recent")
    if not isinstance(recent, dict):
        raise RuntimeError(f"Malformed SEC submissions payload for {ticker}.")
    required = (
        "form",
        "filingDate",
        "reportDate",
        "accessionNumber",
        "primaryDocument",
    )
    columns = [recent.get(name) for name in required]
    if any(not isinstance(column, list) for column in columns):
        raise RuntimeError(f"Malformed SEC submissions columns for {ticker}.")
    lengths = {len(column) for column in columns}
    if len(lengths) != 1:
        raise RuntimeError(f"Inconsistent SEC submissions columns for {ticker}.")
    filings: list[SecFiling] = []
    for form, filed, report, accession, primary in zip(*columns, strict=True):
        if form not in SEC_FORMS:
            continue
        try:
            filing_date = _parse_date(filed)
            report_date = _parse_date(report)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Invalid SEC filing dates for {ticker}.") from exc
        if not isinstance(accession, str) or not isinstance(primary, str):
            raise RuntimeError(f"Invalid SEC filing metadata for {ticker}.")
        filings.append(
            SecFiling(
                ticker=ticker,
                cik=cik,
                accession_number=accession,
                form=form,
                filing_date=filing_date,
                report_date=report_date,
                primary_document=primary,
            )
        )
    return tuple(filings)


def _validate_filing_directory(filing: SecFiling, filing_dir: Path) -> None:
    index = _read_json(filing_dir / "index.json")
    directory = index.get("directory")
    items = directory.get("item") if isinstance(directory, dict) else None
    names = {item.get("name") for item in items or [] if isinstance(item, dict)}
    required = {filing.primary_document}
    required.update(
        name
        for name in names
        if isinstance(name, str)
        and name.lower().endswith(
            (".xsd", "_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")
        )
    )
    missing = sorted(name for name in required if not (filing_dir / name).is_file())
    if missing:
        raise RuntimeError(
            f"SEC filing archive {filing.accession_number} is missing: {', '.join(missing)}."
        )


def _duration_fact(
    company_facts: dict[str, Any],
    filing: SecFiling,
    concepts: Sequence[str],
    unit: str,
) -> SecFact:
    candidates = _fact_candidates(company_facts, filing, concepts, unit)
    candidates = [
        fact
        for fact in candidates
        if fact.start_date is not None and fact.end_date == filing.report_date
    ]
    target_days = 365 if filing.form == "10-K" else 91
    ranges = (300, 400) if filing.form == "10-K" else (60, 120)
    candidates = [
        fact
        for fact in candidates
        if ranges[0] <= (fact.end_date - fact.start_date).days <= ranges[1]
    ]
    if not candidates:
        raise RuntimeError(
            f"SEC filing {filing.accession_number} has no usable {concepts[0]} fact."
        )
    return min(
        candidates,
        key=lambda fact: (
            abs((fact.end_date - fact.start_date).days - target_days),
            concepts.index(fact.concept),
        ),
    )


def _duration_fact_for_period(
    company_facts: dict[str, Any],
    filing: SecFiling,
    concepts: Sequence[str],
    period: CashFlowPeriod,
    *,
    required: bool = True,
) -> SecFact | None:
    candidates = [
        fact
        for fact in _fact_candidates(company_facts, filing, concepts, "USD")
        if fact.start_date == period.start_date and fact.end_date == period.end_date
    ]
    if not candidates:
        if not required:
            return None
        raise RuntimeError(
            f"SEC filing {filing.accession_number} has no usable {concepts[0]} fact "
            f"for {_format_cash_flow_period(period)}."
        )
    best_concept = min(concepts.index(fact.concept) for fact in candidates)
    preferred = [
        fact for fact in candidates if concepts.index(fact.concept) == best_concept
    ]
    values = {fact.value for fact in preferred}
    if len(values) != 1:
        raise RuntimeError(
            f"SEC filing {filing.accession_number} has conflicting "
            f"{concepts[best_concept]} facts for {_format_cash_flow_period(period)}."
        )
    return preferred[0]


def _instant_fact(
    company_facts: dict[str, Any],
    filing: SecFiling,
    concepts: Sequence[str],
    unit: str,
    *,
    required: bool = True,
) -> SecFact | None:
    return _instant_fact_for_period(
        company_facts,
        filing,
        concepts,
        filing.report_date,
        unit=unit,
        required=required,
    )


def _instant_fact_for_period(
    company_facts: dict[str, Any],
    filing: SecFiling,
    concepts: Sequence[str],
    period: date,
    *,
    unit: str = "USD",
    required: bool = True,
) -> SecFact | None:
    candidates = [
        fact
        for fact in _fact_candidates(company_facts, filing, concepts, unit)
        if fact.start_date is None and fact.end_date == period
    ]
    if not candidates:
        if not required:
            return None
        raise RuntimeError(
            f"SEC filing {filing.accession_number} has no usable {concepts[0]} fact."
        )
    best_concept = min(concepts.index(fact.concept) for fact in candidates)
    preferred = [
        fact for fact in candidates if concepts.index(fact.concept) == best_concept
    ]
    values = {fact.value for fact in preferred}
    if len(values) != 1:
        raise RuntimeError(
            f"SEC filing {filing.accession_number} has conflicting "
            f"{concepts[best_concept]} facts for {period.isoformat()}."
        )
    return preferred[0]


def _shares_fact(company_facts: dict[str, Any], filing: SecFiling) -> SecFact:
    concepts = ("EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding")
    candidates: list[SecFact] = []
    for taxonomy in ("dei", "us-gaap"):
        candidates.extend(
            _fact_candidates(
                company_facts, filing, concepts, "shares", taxonomy=taxonomy
            )
        )
    candidates = [
        fact
        for fact in candidates
        if fact.start_date is None and fact.end_date <= filing.filing_date
    ]
    if not candidates:
        raise RuntimeError(
            f"SEC filing {filing.accession_number} has no usable shares-outstanding fact."
        )
    return max(
        candidates,
        key=lambda fact: (fact.end_date, -concepts.index(fact.concept)),
    )


def _fact_candidates(
    company_facts: dict[str, Any],
    filing: SecFiling,
    concepts: Sequence[str],
    unit: str,
    *,
    taxonomy: str = "us-gaap",
) -> list[SecFact]:
    taxonomy_facts = company_facts.get("facts", {}).get(taxonomy, {})
    candidates: list[SecFact] = []
    for concept in concepts:
        concept_payload = taxonomy_facts.get(concept, {})
        values = concept_payload.get("units", {}).get(unit, [])
        for value in values:
            if (
                not isinstance(value, dict)
                or value.get("accn") != filing.accession_number
            ):
                continue
            try:
                numeric = float(value["val"])
                end_date = _parse_date(value["end"])
                start_date = _parse_date(value["start"]) if value.get("start") else None
            except (KeyError, TypeError, ValueError):
                continue
            if not math.isfinite(numeric):
                continue
            candidates.append(SecFact(concept, numeric, unit, start_date, end_date))
    return candidates


def _normalise_tickers(tickers: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(ticker).upper().strip() for ticker in tickers if str(ticker).strip()
        )
    )


def _normalise_dates(values: Sequence[str | date]) -> tuple[date, ...]:
    return tuple(sorted({_parse_date(value) for value in values}))


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read SEC archive JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"SEC archive JSON is not an object: {path}")
    return payload


def _safe_relative_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise RuntimeError("SEC manifest contains an invalid path.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError(f"SEC manifest contains an unsafe path: {value}")
    return path


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
