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


class Hop(_SourcedModel):
    from_node: str
    to_node: str
    network_name: str
    fee_usd: Decimal = Field(ge=0)
    time_hours: Decimal = Field(ge=0)
    currency_in: str
    currency_out: str
    fx_rate: Decimal = Field(gt=0)


class Route(_FrozenModel):
    hops: list[Hop]
    total_fee_usd: Decimal = Field(ge=0)
    total_time_hours: Decimal = Field(ge=0)
    source_currency: str
    target_currency: str
    source_amount: Decimal = Field(gt=0)
    final_amount: Decimal = Field(ge=0)
    routing_preference: RoutingPreference | None = None


class NetworkQuote(_SourcedModel):
    network_name: str
    fee_usd: Decimal = Field(ge=0)
    time_hours: Decimal = Field(ge=0)
    fx_rate: Decimal = Field(gt=0)
