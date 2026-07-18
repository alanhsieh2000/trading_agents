import json
from datetime import date

import pytest

from trading_agents.evaluation import sec_sources


def _submissions(*rows):
    columns = {
        "form": [],
        "filingDate": [],
        "reportDate": [],
        "accessionNumber": [],
        "primaryDocument": [],
    }
    for form, filed, report, accession, primary in rows:
        columns["form"].append(form)
        columns["filingDate"].append(filed)
        columns["reportDate"].append(report)
        columns["accessionNumber"].append(accession)
        columns["primaryDocument"].append(primary)
    return {"cik": "1", "filings": {"recent": columns}}


def _add_fact(
    facts,
    taxonomy,
    concept,
    unit,
    accession,
    value,
    end,
    *,
    start=None,
):
    record = {"accn": accession, "val": value, "end": end}
    if start is not None:
        record["start"] = start
    facts.setdefault(taxonomy, {}).setdefault(concept, {"units": {}})[
        "units"
    ].setdefault(unit, []).append(record)


def _company_facts(*filings):
    facts = {}
    for accession, report_date, period_start, base, include_liabilities in filings:
        _add_fact(
            facts,
            "us-gaap",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "USD",
            accession,
            base + 1,
            report_date,
            start=period_start,
        )
        _add_fact(
            facts,
            "us-gaap",
            "NetIncomeLoss",
            "USD",
            accession,
            base + 2,
            report_date,
            start=period_start,
        )
        _add_fact(
            facts,
            "us-gaap",
            "EarningsPerShareDiluted",
            "USD/shares",
            accession,
            2.5,
            report_date,
            start=period_start,
        )
        for concept, value in (
            ("Assets", 1000),
            ("StockholdersEquity", 400),
            ("CashAndCashEquivalentsAtCarryingValue", 100),
        ):
            _add_fact(
                facts,
                "us-gaap",
                concept,
                "USD",
                accession,
                value,
                report_date,
            )
        if include_liabilities:
            _add_fact(
                facts,
                "us-gaap",
                "Liabilities",
                "USD",
                accession,
                600,
                report_date,
            )
        _add_fact(
            facts,
            "dei",
            "EntityCommonStockSharesOutstanding",
            "shares",
            accession,
            10,
            report_date,
        )
    return {"cik": 1, "facts": facts}


def test_active_filings_uses_strict_trade_date_cutoff():
    submissions = _submissions(
        ("10-Q", "2023-10-25", "2023-09-30", "old", "old.htm"),
        ("10-K", "2024-01-31", "2023-12-31", "new", "new.htm"),
    )

    filings = sec_sources._active_filings(
        "TEST",
        "0000000001",
        submissions,
        (date(2024, 1, 31), date(2024, 2, 1)),
    )

    assert [filing.accession_number for filing in filings] == ["old", "new"]


def test_render_point_in_time_fundamentals_uses_prior_filing_and_close(tmp_path):
    old = sec_sources.SecFiling(
        "TEST",
        "0000000001",
        "old",
        "10-Q",
        date(2023, 10, 25),
        date(2023, 9, 30),
        "old.htm",
    )
    new = sec_sources.SecFiling(
        "TEST",
        "0000000001",
        "new",
        "10-K",
        date(2024, 1, 31),
        date(2023, 12, 31),
        "new.htm",
    )
    archive = sec_sources.SecArchive(
        tmp_path,
        {"TEST": (old, new)},
        {
            "TEST": _company_facts(
                ("old", "2023-09-30", "2023-07-01", 100, False),
                ("new", "2023-12-31", "2023-01-01", 200, True),
            )
        },
    )
    prices = [("2024-01-30", 20.0), ("2024-01-31", 21.0)]

    same_day = sec_sources.render_point_in_time_fundamentals(
        archive, "TEST", "2024-01-31", prices
    )
    next_day = sec_sources.render_point_in_time_fundamentals(
        archive, "TEST", "2024-02-01", prices
    )

    assert "Source filing: 10-Q filed 2023-10-25" in same_day
    assert "Prior close: 20 USD on 2024-01-30." in same_day
    assert "Revenue (quarter): 101 USD." in same_day
    assert "Liabilities (derived as assets minus equity): 600 USD." in same_day
    assert "Estimated market capitalization: 200 USD." in same_day
    assert "Estimated price to book: 0.5." in same_day
    assert "Source filing: 10-K filed 2024-01-31" in next_day
    assert "Prior close: 21 USD on 2024-01-31." in next_day
    assert "Revenue (annual): 201 USD." in next_day
    assert "Current price" not in next_day


def test_render_point_in_time_balance_sheet_uses_disclosed_filing_periods(tmp_path):
    old = sec_sources.SecFiling(
        "TEST",
        "0000000001",
        "old",
        "10-Q",
        date(2023, 10, 25),
        date(2023, 9, 30),
        "old.htm",
    )
    new = sec_sources.SecFiling(
        "TEST",
        "0000000001",
        "new",
        "10-K",
        date(2024, 1, 31),
        date(2023, 12, 31),
        "new.htm",
    )
    facts = {"cik": 1, "facts": {}}
    for accession, period, assets, equity, include_liabilities in (
        ("old", "2023-09-30", 900, 350, True),
        ("new", "2022-12-31", 950, 375, False),
        ("new", "2023-12-31", 1000, 400, False),
    ):
        for concept, value in (
            ("CashAndCashEquivalentsAtCarryingValue", assets / 10),
            ("ShortTermInvestments", assets / 20),
            ("Assets", assets),
            ("StockholdersEquity", equity),
            ("LiabilitiesAndStockholdersEquity", assets),
        ):
            _add_fact(
                facts["facts"],
                "us-gaap",
                concept,
                "USD",
                accession,
                value,
                period,
            )
        if include_liabilities:
            _add_fact(
                facts["facts"],
                "us-gaap",
                "Liabilities",
                "USD",
                accession,
                assets - equity,
                period,
            )
    archive = sec_sources.SecArchive(
        tmp_path,
        {"TEST": (old, new)},
        {"TEST": facts},
    )

    same_day = sec_sources.render_point_in_time_balance_sheet(
        archive, "TEST", "2024-01-31"
    )
    next_day = sec_sources.render_point_in_time_balance_sheet(
        archive, "TEST", "2024-02-01"
    )

    assert "Source filing: 10-Q filed 2023-10-25" in same_day
    assert "line_item,2023-09-30" in same_day
    assert "Source filing: 10-K filed 2024-01-31" in next_day
    assert "line_item,2023-12-31,2022-12-31" in next_day
    assert "Cash and cash equivalents,100,95" in next_day
    assert "Marketable securities,50,47.5" in next_day
    assert (
        "Total liabilities (derived as assets minus equity where unavailable),600,575"
        in next_day
    )
    assert "2024-" not in next_day.split("line_item", 1)[1]


def test_render_point_in_time_balance_sheet_rejects_conflicting_facts(tmp_path):
    filing = sec_sources.SecFiling(
        "TEST",
        "0000000001",
        "accn",
        "10-K",
        date(2024, 1, 31),
        date(2023, 12, 31),
        "test.htm",
    )
    facts = {"cik": 1, "facts": {}}
    for concept, value in (
        ("Assets", 1000),
        ("Assets", 1001),
        ("StockholdersEquity", 400),
        ("LiabilitiesAndStockholdersEquity", 1000),
    ):
        _add_fact(
            facts["facts"],
            "us-gaap",
            concept,
            "USD",
            "accn",
            value,
            "2023-12-31",
        )
    archive = sec_sources.SecArchive(
        tmp_path,
        {"TEST": (filing,)},
        {"TEST": facts},
    )

    with pytest.raises(RuntimeError, match="conflicting Assets facts"):
        sec_sources.render_point_in_time_balance_sheet(archive, "TEST", "2024-02-01")


def _add_cash_flow_period(
    facts,
    accession,
    start,
    end,
    *,
    operating,
    capital_expenditures,
    investing,
    financing,
    exchange_rate,
    net_change=None,
):
    values = (
        ("NetIncomeLoss", operating / 2),
        ("NetCashProvidedByUsedInOperatingActivities", operating),
        ("PaymentsToAcquireProductiveAssets", capital_expenditures),
        ("NetCashProvidedByUsedInInvestingActivities", investing),
        ("NetCashProvidedByUsedInFinancingActivities", financing),
        (
            "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            exchange_rate,
        ),
        (
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
            operating + investing + financing + exchange_rate
            if net_change is None
            else net_change,
        ),
    )
    for concept, value in values:
        _add_fact(
            facts,
            "us-gaap",
            concept,
            "USD",
            accession,
            value,
            end,
            start=start,
        )


def test_render_point_in_time_cashflow_selects_filing_statement_periods(tmp_path):
    old = sec_sources.SecFiling(
        "TEST",
        "0000000001",
        "old",
        "10-Q",
        date(2023, 10, 25),
        date(2023, 9, 30),
        "old.htm",
    )
    new = sec_sources.SecFiling(
        "TEST",
        "0000000001",
        "new",
        "10-K",
        date(2024, 1, 31),
        date(2023, 12, 31),
        "new.htm",
    )
    facts = {"cik": 1, "facts": {}}
    for start, end, operating in (
        ("2023-01-01", "2023-09-30", 100),
        ("2022-01-01", "2022-09-30", 80),
        ("2023-07-01", "2023-09-30", 30),
        ("2022-10-01", "2023-09-30", 130),
    ):
        _add_cash_flow_period(
            facts["facts"],
            "old",
            start,
            end,
            operating=operating,
            capital_expenditures=20,
            investing=-30,
            financing=-60,
            exchange_rate=-1,
        )
    for year, operating in ((2023, 120), (2022, 110), (2021, 100)):
        _add_cash_flow_period(
            facts["facts"],
            "new",
            f"{year}-01-01",
            f"{year}-12-31",
            operating=operating,
            capital_expenditures=20,
            investing=-30,
            financing=-60,
            exchange_rate=-1,
        )
    archive = sec_sources.SecArchive(
        tmp_path,
        {"TEST": (old, new)},
        {"TEST": facts},
    )

    same_day = sec_sources.render_point_in_time_cashflow(
        archive, "TEST", "2024-01-31"
    )
    next_day = sec_sources.render_point_in_time_cashflow(
        archive, "TEST", "2024-02-01"
    )

    assert "Source filing: 10-Q filed 2023-10-25" in same_day
    assert (
        "line_item,2023-01-01..2023-09-30,2022-01-01..2022-09-30"
        in same_day
    )
    assert "2023-07-01..2023-09-30" not in same_day
    assert "2022-10-01..2023-09-30" not in same_day
    assert "Source filing: 10-K filed 2024-01-31" in next_day
    assert (
        "line_item,2023-01-01..2023-12-31,2022-01-01..2022-12-31,"
        "2021-01-01..2021-12-31" in next_day
    )
    assert (
        "Free cash flow (derived as operating cash flow minus capital expenditures),"
        "100,90,80" in next_day
    )


def test_render_point_in_time_cashflow_rejects_unreconciled_change(tmp_path):
    filing = sec_sources.SecFiling(
        "TEST",
        "0000000001",
        "accn",
        "10-K",
        date(2024, 1, 31),
        date(2023, 12, 31),
        "test.htm",
    )
    facts = {"cik": 1, "facts": {}}
    _add_cash_flow_period(
        facts["facts"],
        "accn",
        "2023-01-01",
        "2023-12-31",
        operating=100,
        capital_expenditures=20,
        investing=-30,
        financing=-60,
        exchange_rate=-1,
        net_change=999,
    )
    archive = sec_sources.SecArchive(
        tmp_path,
        {"TEST": (filing,)},
        {"TEST": facts},
    )

    with pytest.raises(RuntimeError, match="unreconciled cash change"):
        sec_sources.render_point_in_time_cashflow(archive, "TEST", "2024-02-01")


def test_render_point_in_time_cashflow_rejects_conflicting_facts(tmp_path):
    filing = sec_sources.SecFiling(
        "TEST",
        "0000000001",
        "accn",
        "10-K",
        date(2024, 1, 31),
        date(2023, 12, 31),
        "test.htm",
    )
    facts = {"cik": 1, "facts": {}}
    _add_cash_flow_period(
        facts["facts"],
        "accn",
        "2023-01-01",
        "2023-12-31",
        operating=100,
        capital_expenditures=20,
        investing=-30,
        financing=-60,
        exchange_rate=-1,
    )
    _add_fact(
        facts["facts"],
        "us-gaap",
        "NetIncomeLoss",
        "USD",
        "accn",
        999,
        "2023-12-31",
        start="2023-01-01",
    )
    archive = sec_sources.SecArchive(
        tmp_path,
        {"TEST": (filing,)},
        {"TEST": facts},
    )

    with pytest.raises(RuntimeError, match="conflicting NetIncomeLoss facts"):
        sec_sources.render_point_in_time_cashflow(archive, "TEST", "2024-02-01")


def test_duration_fact_prefers_quarter_over_year_to_date():
    filing = sec_sources.SecFiling(
        "TEST",
        "0000000001",
        "accn",
        "10-Q",
        date(2024, 1, 31),
        date(2023, 9, 30),
        "test.htm",
    )
    facts = {"cik": 1, "facts": {}}
    for start, value in (("2023-01-01", 300), ("2023-07-01", 100)):
        _add_fact(
            facts["facts"],
            "us-gaap",
            "NetIncomeLoss",
            "USD",
            "accn",
            value,
            "2023-09-30",
            start=start,
        )

    fact = sec_sources._duration_fact(facts, filing, ("NetIncomeLoss",), "USD")

    assert fact.value == 100


def test_ensure_sec_archive_requires_user_agent(monkeypatch, tmp_path):
    monkeypatch.delenv("SEC_UA", raising=False)

    with pytest.raises(RuntimeError, match="SEC_UA is required"):
        sec_sources.ensure_sec_archive(
            ["TEST"], ["2024-01-02"], raw_dir=tmp_path / "SEC"
        )


def test_ensure_sec_archive_downloads_manifested_filing_package(monkeypatch, tmp_path):
    monkeypatch.setenv("SEC_UA", "TradingAgents test contact@example.com")
    accession = "0000000001-23-000001"
    accession_path = accession.replace("-", "")
    base = sec_sources.SEC_ARCHIVE_URL.format(cik=1, accession=accession_path)
    ticker_payload = {"0": {"ticker": "TEST", "cik_str": 1}}
    submissions = _submissions(
        ("10-K", "2023-11-01", "2023-09-30", accession, "test.htm")
    )
    company_facts = {"cik": 1, "facts": {}}
    names = [
        "test.htm",
        "test.xsd",
        "test_cal.xml",
        "test_def.xml",
        "test_lab.xml",
        "test_pre.xml",
    ]
    filing_index = {"directory": {"item": [{"name": name} for name in names]}}
    responses = {
        sec_sources.SEC_TICKER_URL: json.dumps(ticker_payload).encode(),
        sec_sources.SEC_SUBMISSIONS_URL.format(cik="0000000001"): json.dumps(
            submissions
        ).encode(),
        sec_sources.SEC_COMPANY_FACTS_URL.format(cik="0000000001"): json.dumps(
            company_facts
        ).encode(),
        f"{base}/index.json": json.dumps(filing_index).encode(),
        **{f"{base}/{name}": name.encode() for name in names},
    }

    class Response:
        status_code = 200
        headers = {}

        def __init__(self, content):
            self.content = content

    class Session:
        def __init__(self):
            self.calls = []

        def get(self, url, *, headers, timeout):
            self.calls.append((url, headers, timeout))
            return Response(responses[url])

    session = Session()
    raw_dir = tmp_path / "SEC"

    archive = sec_sources.ensure_sec_archive(
        ["TEST"],
        ["2024-01-02"],
        raw_dir=raw_dir,
        session=session,
        request_delay_seconds=0,
    )

    assert archive.filings_by_ticker["TEST"][0].accession_number == accession
    assert (raw_dir / "TEST" / accession / "test.htm").read_bytes() == b"test.htm"
    assert (raw_dir / "manifest.json").is_file()
    assert all(
        headers["User-Agent"] == "TradingAgents test contact@example.com"
        for _, headers, _ in session.calls
    )
    calls = len(session.calls)
    sec_sources.ensure_sec_archive(
        ["TEST"], ["2024-01-02"], raw_dir=raw_dir, session=session
    )
    assert len(session.calls) == calls


def test_load_sec_archive_rejects_manifested_file_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("SEC_UA", "TradingAgents test contact@example.com")
    raw_dir = tmp_path / "SEC"
    raw_dir.mkdir()
    (raw_dir / "company_tickers.json").write_text("{}")
    content = (raw_dir / "company_tickers.json").read_bytes()
    (raw_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "files": [
                    {
                        "path": "company_tickers.json",
                        "url": "https://example.test",
                        "size": len(content),
                        "sha256": "0" * 64,
                    }
                ],
            }
        )
    )

    with pytest.raises(RuntimeError, match="integrity validation"):
        sec_sources.load_sec_archive(["TEST"], ["2024-01-02"], raw_dir=raw_dir)
