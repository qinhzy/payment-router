from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal

import httpx
import pytest
from pytest_httpx import HTTPXMock

from payment_router.core.models import DataSource
from payment_router.networks.wise import QUOTE_URL, WiseAPIError, WiseNetwork

# Captured from a live `POST https://api.wise.com/v3/quotes/` request on
# 2026-04-19 with:
# {"sourceCurrency": "GBP", "targetCurrency": "CNY", "sourceAmount": 1000}
LIVE_WISE_GBP_CNY_RESPONSE = {
    "sourceAmount": 1000.0,
    "guaranteedTargetAmountAllowed": False,
    "targetAmountAllowed": True,
    "paymentOptions": [
        {
            "formattedEstimatedDelivery": "in seconds",
            "estimatedDeliveryDelays": [],
            "allowedProfileTypes": ["PERSONAL", "BUSINESS"],
            "feePercentage": 0.0113,
            "estimatedDelivery": "2026-04-19T05:56:31Z",
            "sourceAmount": 1000.0,
            "targetAmount": 9113.22,
            "sourceCurrency": "GBP",
            "targetCurrency": "CNY",
            "payOut": "BANK_TRANSFER",
            "payIn": "PISP",
            "price": {
                "priceSetId": 5064,
                "total": {
                    "type": "TOTAL",
                    "label": "Total fees",
                    "value": {
                        "amount": 11.25,
                        "currency": "GBP",
                        "label": "11.25 GBP",
                    },
                },
                "items": [
                    {
                        "type": "PAYIN",
                        "label": "fee",
                        "value": {
                            "amount": 0.0,
                            "currency": "GBP",
                            "label": "0 GBP",
                        },
                    },
                    {
                        "type": "TRANSFERWISE",
                        "label": "Our fee",
                        "value": {
                            "amount": 11.25,
                            "currency": "GBP",
                            "label": "11.25 GBP",
                        },
                    },
                ],
                "priceDecisionReferenceId": "76913f7c-4b40-463b-1ff9-8f5113094468",
            },
            "fee": {
                "transferwise": 11.25,
                "payIn": 0.0,
                "discount": 0,
                "total": 11.25,
                "priceSetId": 5064,
                "partner": 0.0,
            },
            "disabled": False,
        },
        {
            "formattedEstimatedDelivery": "in seconds",
            "estimatedDeliveryDelays": [],
            "allowedProfileTypes": ["PERSONAL", "BUSINESS"],
            "feePercentage": 0.0113,
            "estimatedDelivery": "2026-04-19T05:56:31Z",
            "sourceAmount": 1000.0,
            "targetAmount": 9113.22,
            "sourceCurrency": "GBP",
            "targetCurrency": "CNY",
            "payOut": "BANK_TRANSFER",
            "payIn": "BANK_TRANSFER",
            "price": {
                "priceSetId": 5064,
                "total": {
                    "type": "TOTAL",
                    "label": "Total fees",
                    "value": {
                        "amount": 11.25,
                        "currency": "GBP",
                        "label": "11.25 GBP",
                    },
                },
                "items": [
                    {
                        "type": "PAYIN",
                        "label": "fee",
                        "value": {
                            "amount": 0.0,
                            "currency": "GBP",
                            "label": "0 GBP",
                        },
                    },
                    {
                        "type": "TRANSFERWISE",
                        "label": "Our fee",
                        "value": {
                            "amount": 11.25,
                            "currency": "GBP",
                            "label": "11.25 GBP",
                        },
                    },
                ],
                "priceDecisionReferenceId": "76913f7c-4b40-463b-1ff9-8f5113094468",
            },
            "fee": {
                "transferwise": 11.25,
                "payIn": 0.0,
                "discount": 0,
                "total": 11.25,
                "priceSetId": 5064,
                "partner": 0.0,
            },
            "disabled": False,
        },
        {
            "formattedEstimatedDelivery": "in seconds",
            "estimatedDeliveryDelays": [],
            "allowedProfileTypes": ["PERSONAL", "BUSINESS"],
            "feePercentage": 0.0111,
            "estimatedDelivery": "2026-04-19T05:56:31Z",
            "disabledReason": {
                "code": "error.payInmethod.disabled",
                "message": (
                    "Sorry, using a multi currency account is currently not available "
                    "in your country. Please choose another payment method."
                ),
                "arguments": [],
            },
            "sourceAmount": 1000.0,
            "targetAmount": 9114.88,
            "sourceCurrency": "GBP",
            "targetCurrency": "CNY",
            "payOut": "BANK_TRANSFER",
            "payIn": "BALANCE",
            "price": {
                "priceSetId": 5063,
                "total": {
                    "type": "TOTAL",
                    "label": "Total fees",
                    "value": {
                        "amount": 11.07,
                        "currency": "GBP",
                        "label": "11.07 GBP",
                    },
                },
                "items": [
                    {
                        "type": "PAYIN",
                        "label": "fee",
                        "value": {
                            "amount": 0.0,
                            "currency": "GBP",
                            "label": "0 GBP",
                        },
                    },
                    {
                        "type": "TRANSFERWISE",
                        "label": "Our fee",
                        "value": {
                            "amount": 11.07,
                            "currency": "GBP",
                            "label": "11.07 GBP",
                        },
                    },
                ],
                "priceDecisionReferenceId": "76913f7c-4b40-463b-1ff9-8f5113094468",
            },
            "fee": {
                "transferwise": 11.07,
                "payIn": 0.0,
                "discount": 0,
                "total": 11.07,
                "priceSetId": 5063,
                "partner": 0.0,
            },
            "disabled": True,
        },
    ],
    "notices": [
        {
            "code": "notice.personal.to.cny.wallet.info",
            "text": (
                "To receive your money, Alipay and Weixin recipients may need to "
                "link a bank card to their wallets. Alipay recipients will receive "
                "a push notification and Weixin recipients will receive a SMS to "
                "help them complete this one time setup."
            ),
            "link": None,
            "type": "INFO",
        }
    ],
    "transferFlowConfig": {
        "highAmount": {
            "showFeePercentage": False,
            "trackAsHighAmountSender": False,
            "showEducationStep": False,
            "offerPrefundingOption": False,
            "overLimitThroughCs": False,
            "overLimitThroughWiseAccount": False,
        },
        "hiddenPaymentOptions": ["BANK_TRANSFER"],
    },
    "rateTimestamp": "2026-04-19T05:55:57Z",
    "clientId": "unknown",
    "sourceCurrency": "GBP",
    "targetCurrency": "CNY",
    "createdTime": "2026-04-19T05:56:31Z",
    "rateType": "FIXED",
    "payOut": "BANK_TRANSFER",
    "funding": "POST",
    "rateExpirationTime": "2026-04-20T07:59:59Z",
    "guaranteedTargetAmount": False,
    "providedAmountType": "SOURCE",
    "rate": 9.21691,
    "status": "PENDING",
    "expirationTime": "2026-04-19T06:26:31Z",
    "type": "REGULAR",
}


pytestmark = pytest.mark.anyio


async def test_get_quote_returns_verified_quote_for_gbp_to_cny(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=QUOTE_URL,
        json=deepcopy(LIVE_WISE_GBP_CNY_RESPONSE),
    )
    network = WiseNetwork()

    quote = await network.get_quote(Decimal("1000"), "GBP", "CNY")

    assert quote is not None
    assert quote.network_name == "wise"
    assert quote.fee_usd == Decimal("11.25")
    assert quote.fx_rate == Decimal("9.21691")
    assert quote.time_hours == Decimal("0")
    assert quote.data_source is DataSource.VERIFIED

    request = httpx_mock.get_requests()[0]
    assert request.url == httpx.URL(QUOTE_URL)
    assert request.headers["Accept-Language"] == "en"
    assert json.loads(request.content.decode("utf-8")) == {
        "sourceCurrency": "GBP",
        "targetCurrency": "CNY",
        "sourceAmount": 1000.0,
    }


async def test_get_quote_returns_none_for_unsupported_corridor(
    httpx_mock: HTTPXMock,
) -> None:
    network = WiseNetwork()

    quote = await network.get_quote(Decimal("1000"), "JPY", "CNY")

    assert quote is None
    assert not httpx_mock.get_requests()


async def test_get_quote_raises_on_server_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=QUOTE_URL,
        status_code=500,
        json={"error": "internal server error"},
    )
    network = WiseNetwork()

    with pytest.raises(WiseAPIError, match="status 500"):
        await network.get_quote(Decimal("1000"), "GBP", "CNY")


async def test_get_quote_raises_on_missing_required_fields(
    httpx_mock: HTTPXMock,
) -> None:
    invalid_response = deepcopy(LIVE_WISE_GBP_CNY_RESPONSE)
    del invalid_response["rate"]
    httpx_mock.add_response(
        method="POST",
        url=QUOTE_URL,
        json=invalid_response,
    )
    network = WiseNetwork()

    with pytest.raises(WiseAPIError, match="missing required fields"):
        await network.get_quote(Decimal("1000"), "GBP", "CNY")


async def test_get_quote_wraps_timeouts(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(
        httpx.ReadTimeout("Timed out while contacting Wise"),
        method="POST",
        url=QUOTE_URL,
    )
    network = WiseNetwork()

    with pytest.raises(WiseAPIError, match="timed out"):
        await network.get_quote(Decimal("1000"), "GBP", "CNY")
