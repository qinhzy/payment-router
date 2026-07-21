from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from payment_router.router import RoutingPreference


class DataSource(StrEnum):
    VERIFIED = "VERIFIED"
    INDUSTRY_AVERAGE = "INDUSTRY_AVERAGE"
    ESTIMATED = "ESTIMATED"


_DATA_SOURCE_RISK = {
    DataSource.VERIFIED: 0,
    DataSource.INDUSTRY_AVERAGE: 1,
    DataSource.ESTIMATED: 2,
}


class _FrozenModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


class _SourcedModel(_FrozenModel):
    """Attach provenance to each numeric component as well as the whole quote."""

    data_source: DataSource
    fee_data_source: DataSource | None = None
    time_data_source: DataSource | None = None
    fx_data_source: DataSource | None = None

    @model_validator(mode="after")
    def validate_metric_provenance(self) -> _SourcedModel:
        metric_fields = ("fee_data_source", "time_data_source", "fx_data_source")
        for field_name in metric_fields:
            if getattr(self, field_name) is None:
                object.__setattr__(self, field_name, self.data_source)

        metric_sources = tuple(getattr(self, field_name) for field_name in metric_fields)
        least_trusted = max(metric_sources, key=_DATA_SOURCE_RISK.__getitem__)
        if self.data_source is not least_trusted:
            raise ValueError(
                "data_source must equal the least-trusted fee, time, and FX data source"
            )
        return self

    @property
    def provenance_sources(self) -> tuple[DataSource, ...]:
        sources = {
            self.fee_data_source,
            self.time_data_source,
            self.fx_data_source,
        }
        return tuple(source for source in DataSource if source in sources)


class _TimedModel(_SourcedModel):
    """Point time estimate plus an optional [min, max] bounds interval.

    Bounds default to the point estimate, so single-valued quotes stay
    unchanged. When provided, they must bracket the point estimate.
    """

    time_hours: Decimal = Field(ge=0)
    time_min_hours: Decimal | None = Field(default=None, ge=0)
    time_max_hours: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_time_bounds(self) -> _TimedModel:
        if self.time_min_hours is None:
            object.__setattr__(self, "time_min_hours", self.time_hours)
        if self.time_max_hours is None:
            object.__setattr__(self, "time_max_hours", self.time_hours)
        if not (self.time_min_hours <= self.time_hours <= self.time_max_hours):
            raise ValueError("time bounds must satisfy min <= expected <= max")
        return self


class Hop(_TimedModel):
    from_node: str
    to_node: str
    network_name: str
    fee_usd: Decimal = Field(ge=0)
    currency_in: str
    currency_out: str
    fx_rate: Decimal = Field(gt=0)


class Route(_FrozenModel):
    hops: list[Hop]
    total_fee_usd: Decimal = Field(ge=0)
    total_time_hours: Decimal = Field(ge=0)
    total_time_min_hours: Decimal | None = Field(default=None, ge=0)
    total_time_max_hours: Decimal | None = Field(default=None, ge=0)
    source_currency: str
    target_currency: str
    source_amount: Decimal = Field(gt=0)
    final_amount: Decimal = Field(ge=0)
    routing_preference: RoutingPreference | None = None

    @model_validator(mode="after")
    def validate_total_time_bounds(self) -> Route:
        if self.total_time_min_hours is None:
            object.__setattr__(self, "total_time_min_hours", self.total_time_hours)
        if self.total_time_max_hours is None:
            object.__setattr__(self, "total_time_max_hours", self.total_time_hours)
        if not (self.total_time_min_hours <= self.total_time_hours <= self.total_time_max_hours):
            raise ValueError("total time bounds must satisfy min <= expected <= max")
        return self


class NetworkQuote(_TimedModel):
    network_name: str
    fee_usd: Decimal = Field(ge=0)
    fx_rate: Decimal = Field(gt=0)
