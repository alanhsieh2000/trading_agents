from __future__ import annotations

from enum import Enum

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PortfolioRating(str, Enum):
    """5-tier rating used by the Research Manager and Portfolio Manager."""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class InvestmentPlan(BaseModel):
    """Structured investment plan produced by the Research Manager."""

    model_config = ConfigDict(use_enum_values=True)

    recommendation: PortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate."
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including position sizing guidance consistent with the rating."
        ),
    )


class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager."""

    rating: PortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate."
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering entry strategy, position sizing, "
            "key risk levels, and time horizon. Two to four sentences."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis."
        ),
    )
    price_target: Optional[float] = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    time_horizon: Optional[str] = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )


class LessonRecord(BaseModel):
    """One stored row about a single past decision for one instrument.

    The reflection and the realized returns are filled in later, once the
    outcome of the decision is known.
    """

    ticker: str = Field(description="The instrument the decision was made for.")
    trade_date: str = Field(description="The date the decision was made (YYYY-MM-DD).")
    final_decision: str = Field(
        description="The final position rating recorded at the trade date.",
    )
    raw_return: Optional[float] = Field(
        default=None,
        description="Realized close-to-close return of the instrument over the holding window.",
    )
    alpha_return: Optional[float] = Field(
        default=None,
        description="raw_return minus the benchmark's return over the same window.",
    )
    holding_days: Optional[int] = Field(
        default=None,
        description="Transaction days between the trade date and the end date, capped.",
    )
    reflection: Optional[str] = Field(
        default=None,
        description="Plain-prose lesson written once the outcome is known.",
    )


class LessonBook(BaseModel):
    """Persistent collection of lesson records for a single instrument."""

    lessons: list[LessonRecord] = Field(default_factory=list)


class TraderAction(str, Enum):
    """3-tier transaction direction used by the Trader."""

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader."""

    model_config = ConfigDict(use_enum_values=True)

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences."
        ),
    )
    entry_price: Optional[float] = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    position_sizing: Optional[str] = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )

