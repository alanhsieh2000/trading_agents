"""Dataset-backed analyst tools used in evaluation mode.

Each tool mirrors the name, description, and argument schema of a live analyst
tool so the language model calls it exactly as usual, but its ``_run`` ignores
the arguments and returns the payload recorded in the prepared dataset for the
fixed ``(ticker, as_of_date)`` this evaluation step is replaying.
"""

from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import PrivateAttr

from trading_agents.evaluation.dataset import EvalDataset
from trading_agents.tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_global_news,
    get_income_statement,
    get_indicators,
    get_news,
    get_stock_data,
)

# The CrewAI tools bound to analyst tasks (the plain sentiment functions are
# handled separately, as pre-fetched blocks in ``prepare_analyst_inputs``).
LIVE_ANALYST_TOOLS: tuple[BaseTool, ...] = (
    get_stock_data,
    get_indicators,
    get_news,
    get_global_news,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
)


class DatasetBackedTool(BaseTool):
    """A BaseTool that returns a recorded payload instead of calling an API."""

    _dataset: EvalDataset = PrivateAttr()
    _ticker: str = PrivateAttr()
    _as_of_date: str = PrivateAttr()

    def __init__(
        self,
        *,
        dataset: EvalDataset,
        ticker: str,
        as_of_date: str,
        **data: Any,
    ) -> None:
        super().__init__(**data)
        self._dataset = dataset
        self._ticker = ticker
        self._as_of_date = as_of_date

    def _run(self, *_args: Any, **_kwargs: Any) -> str:
        return self._dataset.tool_output(self.name, self._ticker, self._as_of_date)


def build_dataset_tools(
    dataset: EvalDataset, ticker: str, as_of_date: str
) -> dict[str, DatasetBackedTool]:
    """Build dataset-backed replacements keyed by tool name for one replay step."""
    return {
        template.name: DatasetBackedTool(
            dataset=dataset,
            ticker=ticker,
            as_of_date=as_of_date,
            name=template.name,
            description=template.description,
            args_schema=template.args_schema,
        )
        for template in LIVE_ANALYST_TOOLS
    }
