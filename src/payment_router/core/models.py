from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from payment_router.router import RoutingPreference


class DataSource(StrEnum):
    VERIFIED = "VERIFIED"
    INDUSTRY_AVERAGE = "INDUSTRY_AVERAGE"
    ESTIMATED = "ESTIMATED"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)


class Hop(_FrozenModel):
    from_node: str
    to_node: str
    network_name: str
    fee_usd: Decimal = Field(ge=0)
    time_hours: Decimal = Field(ge=0)
    currency_in: str
    currency_out: str
    fx_rate: Decimal = Field(gt=0)
    data_source: DataSource


class Route(_FrozenModel):
    hops: list[Hop]
    total_fee_usd: Decimal = Field(ge=0)
    total_time_hours: Decimal = Field(ge=0)
    source_currency: str
    target_currency: str
    source_amount: Decimal = Field(gt=0)
    final_amount: Decimal = Field(ge=0)
    routing_preference: "RoutingPreference | None" = None


class NetworkQuote(_FrozenModel):
    network_name: str
    fee_usd: Decimal = Field(ge=0)
    time_hours: Decimal = Field(ge=0)
    fx_rate: Decimal = Field(gt=0)
    data_source: DataSource
