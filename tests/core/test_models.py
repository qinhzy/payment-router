from decimal import Decimal

from payment_router.core.models import DataSource, Hop, NetworkQuote, Route


def test_hop_model_accepts_typed_values() -> None:
    hop = Hop(
        from_node="wallet_usd",
        to_node="bank_eur",
        network_name="swift",
        fee_usd=Decimal("12.50"),
        time_hours=Decimal("24"),
        currency_in="USD",
        currency_out="EUR",
        fx_rate=Decimal("0.92"),
        data_source=DataSource.VERIFIED,
    )

    assert hop.network_name == "swift"
    assert hop.data_source is DataSource.VERIFIED


def test_route_model_embeds_hops() -> None:
    hop = Hop(
        from_node="wallet_usd",
        to_node="bank_eur",
        network_name="sepa",
        fee_usd=Decimal("4.00"),
        time_hours=Decimal("6"),
        currency_in="USD",
        currency_out="EUR",
        fx_rate=Decimal("0.91"),
        data_source=DataSource.INDUSTRY_AVERAGE,
    )
    route = Route(
        hops=[hop],
        total_fee_usd=Decimal("4.00"),
        total_time_hours=Decimal("6"),
        source_currency="USD",
        target_currency="EUR",
        source_amount=Decimal("1000"),
        final_amount=Decimal("906"),
    )

    assert route.hops == [hop]
    assert route.final_amount == Decimal("906")


def test_network_quote_model_tracks_data_source() -> None:
    quote = NetworkQuote(
        network_name="wise",
        fee_usd=Decimal("7.25"),
        time_hours=Decimal("1.5"),
        fx_rate=Decimal("0.915"),
        data_source=DataSource.ESTIMATED,
    )

    assert quote.network_name == "wise"
    assert quote.data_source is DataSource.ESTIMATED
