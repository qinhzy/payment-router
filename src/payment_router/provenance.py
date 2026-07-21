from __future__ import annotations

from dataclasses import dataclass

from payment_router.core.models import DataSource


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    evidence_id: str
    network: str
    metric: str
    classification: DataSource
    value: str
    checked_on: str
    reference: str | None
    caveat: str


PROVENANCE_RECORDS = (
    ProvenanceRecord(
        evidence_id="wise-live-quote",
        network="Wise",
        metric="rate, source fee, delivery estimate",
        classification=DataSource.VERIFIED,
        value="Live API response per request",
        checked_on="2026-07-18",
        reference=("https://docs.wise.com/guides/product/send-money/quotes/unauthenticated-quote"),
        caveat="Display-only quote; rates expire and cannot create a transfer.",
    ),
    ProvenanceRecord(
        evidence_id="fx-frozen-table",
        network="Shared FX",
        metric="USD normalization rates (default source)",
        classification=DataSource.ESTIMATED,
        value="USD 1.00; EUR 1.08; GBP 1.27; CNY 0.14",
        checked_on="2026-04-19",
        reference=None,
        caveat="Frozen teaching values for reproducibility, not current market pricing.",
    ),
    ProvenanceRecord(
        evidence_id="fx-live-ecb",
        network="Shared FX",
        metric="USD normalization rates (--fx live)",
        classification=DataSource.VERIFIED,
        value="ECB euro reference rates per fetched snapshot",
        checked_on="2026-07-20",
        reference="https://www.frankfurter.dev/",
        caveat=(
            "ECB reference rates are indicative daily fixings published once "
            "per business day, not tradable quotes; snapshots may lag."
        ),
    ),
    ProvenanceRecord(
        evidence_id="sepa-sct-time",
        network="SEPA",
        metric="maximum execution time",
        classification=DataSource.VERIFIED,
        value="One banking business day (modelled as 24 hours)",
        checked_on="2026-07-18",
        reference="https://www.europeanpaymentscouncil.eu/what-we-do/sepa-credit-transfer",
        caveat="Calendar-hour modelling does not encode bank holidays or cut-off times.",
    ),
    ProvenanceRecord(
        evidence_id="sepa-sct-fee",
        network="SEPA",
        metric="sender fee",
        classification=DataSource.ESTIMATED,
        value="EUR 0.25",
        checked_on="2026-07-18",
        reference=None,
        caveat="Teaching assumption; the EPC scheme does not set customer pricing.",
    ),
    ProvenanceRecord(
        evidence_id="sepa-instant-time",
        network="SEPA Instant",
        metric="maximum execution time",
        classification=DataSource.VERIFIED,
        value="10 seconds",
        checked_on="2026-07-18",
        reference=(
            "https://www.europeanpaymentscouncil.eu/what-we-do/sepa-instant-credit-transfer"
        ),
        caveat="Availability still depends on participating payment service providers.",
    ),
    ProvenanceRecord(
        evidence_id="sepa-instant-fee",
        network="SEPA Instant",
        metric="sender fee",
        classification=DataSource.ESTIMATED,
        value="EUR 0.50",
        checked_on="2026-07-18",
        reference=None,
        caveat="Teaching assumption; the EPC scheme does not set customer pricing.",
    ),
    ProvenanceRecord(
        evidence_id="swift-topology",
        network="SWIFT",
        metric="correspondent-banking structure",
        classification=DataSource.VERIFIED,
        value="Interbank messaging across correspondent relationships",
        checked_on="2026-07-18",
        reference="https://www.swift.com/payments/correspondent-banking",
        caveat="SWIFT is a messaging network, not a single priced payment rail.",
    ),
    ProvenanceRecord(
        evidence_id="swift-model-parameters",
        network="SWIFT",
        metric="hops, fees, time, FX spread",
        classification=DataSource.ESTIMATED,
        value="3 hops; $20 + 0.2%; 18h (band 6-48h) per hop; 1% spread",
        checked_on="2026-07-20",
        reference=None,
        caveat="Scenario assumptions, not an industry median or a bank quote.",
    ),
)
