from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class InvestmentPlan(BaseModel):
    rating: Literal["Buy", "Overweight", "Hold", "Underweight", "Sell"]
    thesis: str
    supporting_evidence: list[str]
    key_risks: list[str]
    recommended_action: str
