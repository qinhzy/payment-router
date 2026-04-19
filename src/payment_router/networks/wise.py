"""
Wise unauthenticated quote integration.

Data source verification:
- Verified on 2026-04-19 against
  https://docs.wise.com/guides/product/send-money/quotes/unauthenticated-quote
- Quote schema cross-checked on 2026-04-19 against
  https://docs.wise.com/api-reference/quote
- Public endpoint used:
  POST https://api.wise.com/v3/quotes/
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from payment_router.core import fx
from payment_router.core.models import DataSource, NetworkQuote
from payment_router.networks.base import PaymentNetwork

QUOTE_URL = "https://api.wise.com/v3/quotes/"
SUPPORTED_CURRENCIES = fx.supported_currencies()
PREFERRED_PAYIN_METHODS = ("BALANCE", "BANK_TRANSFER")
ENGLISH_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en",
}


class WiseAPIError(RuntimeError):
    """Raised when the Wise quote API cannot provide a reliable quote."""


class WiseNetwork(PaymentNetwork):
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def get_quote(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
    ) -> NetworkQuote | None:
        source_currency = from_currency.strip().upper()
        target_currency = to_currency.strip().upper()

        if (
            source_currency == target_currency
            or source_currency not in SUPPORTED_CURRENCIES
            or target_currency not in SUPPORTED_CURRENCIES
        ):
            return None

        payload = {
            "sourceCurrency": source_currency,
            "targetCurrency": target_currency,
            "sourceAmount": float(amount),
        }

        try:
            async with httpx.AsyncClient(
                headers=ENGLISH_HEADERS,
                timeout=self._timeout_seconds,
            ) as client:
                response = await client.post(QUOTE_URL, json=payload)
        except httpx.TimeoutException as exc:
            raise WiseAPIError("Wise quote request timed out") from exc
        except httpx.RequestError as exc:
            raise WiseAPIError("Wise quote request failed") from exc

        if response.is_error:
            if self._is_unsupported_corridor_error(response):
                return None
            raise WiseAPIError(
                f"Wise quote request failed with status {response.status_code}: "
                f"{self._safe_error_text(response)}"
            )

        try:
            response_json = response.json()
        except ValueError as exc:
            raise WiseAPIError("Wise quote response was not valid JSON") from exc

        if not isinstance(response_json, Mapping):
            raise WiseAPIError("Wise quote response must be a JSON object")

        try:
            selected_option = self._select_payment_option(response_json)
            fee_total = self._decimal_from_mapping(selected_option.get("fee"), "total")
            fx_rate = self._decimal_from_mapping(response_json, "rate")
            time_hours = self._extract_time_hours(response_json, selected_option)
        except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
            raise WiseAPIError("Wise quote response missing required fields") from exc

        return NetworkQuote(
            network_name="wise",
            fee_usd=fee_total,
            time_hours=time_hours,
            fx_rate=fx_rate,
            data_source=DataSource.VERIFIED,
        )

    def supported_currencies(self) -> set[str]:
        return set(fx.supported_currencies())

    @staticmethod
    def _safe_error_text(response: httpx.Response) -> str:
        text = response.text.strip()
        return text[:200] if text else "no response body"

    @staticmethod
    def _is_unsupported_corridor_error(response: httpx.Response) -> bool:
        if response.status_code not in {400, 404, 422}:
            return False

        payload = response.text.lower()
        keywords = (
            "unsupported",
            "not supported",
            "currency pair",
            "corridor",
            "route",
        )
        return any(keyword in payload for keyword in keywords)

    @staticmethod
    def _select_payment_option(response_json: Mapping[str, Any]) -> Mapping[str, Any]:
        raw_options = response_json.get("paymentOptions")
        if not isinstance(raw_options, list):
            raise KeyError("paymentOptions")

        enabled_options = [
            option
            for option in raw_options
            if isinstance(option, Mapping) and not option.get("disabled", False)
        ]

        for preferred_payin in PREFERRED_PAYIN_METHODS:
            for option in enabled_options:
                payin = str(option.get("payIn", "")).upper()
                if payin == preferred_payin:
                    return option

        raise KeyError("No enabled BALANCE or BANK_TRANSFER payment option")

    @classmethod
    def _extract_time_hours(
        cls,
        response_json: Mapping[str, Any],
        payment_option: Mapping[str, Any],
    ) -> Decimal:
        created_time_raw = response_json.get("createdTime")
        created_time = cls._parse_timestamp(created_time_raw) if created_time_raw else None

        delivery_time_raw = (
            payment_option.get("estimatedDelivery")
            or payment_option.get("estimatedDeliveryDate")
            or response_json.get("estimatedDelivery")
            or response_json.get("estimatedDeliveryDate")
        )
        if delivery_time_raw is not None:
            if created_time is None:
                raise KeyError("createdTime")

            delivery_time = cls._parse_timestamp(delivery_time_raw)
            delta_seconds = (delivery_time - created_time).total_seconds()
            if delta_seconds < 0:
                raise ValueError("estimated delivery cannot be before createdTime")
            return Decimal(str(delta_seconds)) / Decimal("3600")

        formatted_delivery_raw = (
            payment_option.get("formattedEstimatedDelivery")
            or payment_option.get("formattedEstimatedDeliveryDate")
            or response_json.get("formattedEstimatedDelivery")
            or response_json.get("formattedEstimatedDeliveryDate")
        )
        if formatted_delivery_raw is not None:
            return cls._parse_formatted_delivery(str(formatted_delivery_raw), created_time)

        raise KeyError("estimatedDelivery")

    @staticmethod
    def _decimal_from_mapping(mapping: Any, key: str) -> Decimal:
        if not isinstance(mapping, Mapping):
            raise TypeError(f"{key} must come from a JSON object")
        if key not in mapping:
            raise KeyError(key)
        return Decimal(str(mapping[key]))

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("timestamp must be a non-empty string")

        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        elif re.search(r"[+-]\d{4}$", normalized):
            normalized = normalized[:-5] + normalized[-5:-2] + ":" + normalized[-2:]

        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)

    @classmethod
    def _parse_formatted_delivery(
        cls,
        formatted_delivery: str,
        created_time: datetime | None,
    ) -> Decimal:
        normalized = formatted_delivery.strip().lower()
        if not normalized:
            raise ValueError("formattedEstimatedDelivery must not be empty")

        if normalized in {"now", "in seconds", "within seconds"}:
            return Decimal("0")

        minute_match = re.fullmatch(r"in (\d+) minutes?", normalized)
        if minute_match:
            minutes = Decimal(minute_match.group(1))
            return minutes / Decimal("60")

        hour_match = re.fullmatch(r"in (\d+) hours?", normalized)
        if hour_match:
            return Decimal(hour_match.group(1))

        day_match = re.fullmatch(r"in (\d+) days?", normalized)
        if day_match:
            days = Decimal(day_match.group(1))
            return days * Decimal("24")

        if created_time is None:
            raise KeyError("createdTime")

        if normalized.startswith("by "):
            due_datetime = cls._parse_by_day_label(formatted_delivery[3:].strip(), created_time)
            delta_seconds = (due_datetime - created_time).total_seconds()
            if delta_seconds < 0:
                raise ValueError("formattedEstimatedDelivery resolved before createdTime")
            return Decimal(str(delta_seconds)) / Decimal("3600")

        raise ValueError(f"Unsupported formattedEstimatedDelivery value: {formatted_delivery}")

    @staticmethod
    def _parse_by_day_label(label: str, created_time: datetime) -> datetime:
        created_utc = created_time.astimezone(timezone.utc)

        for date_format in ("%A, %B %d", "%A, %b %d", "%B %d", "%b %d"):
            try:
                parsed = datetime.strptime(label, date_format)
            except ValueError:
                continue

            candidate = datetime(
                year=created_utc.year,
                month=parsed.month,
                day=parsed.day,
                hour=23,
                minute=59,
                second=59,
                tzinfo=timezone.utc,
            )
            if candidate < created_utc:
                candidate = candidate.replace(year=candidate.year + 1)
            return candidate

        weekdays = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        weekday_name = label.strip().lower()
        if weekday_name not in weekdays:
            raise ValueError(f"Unsupported date label: {label}")

        days_ahead = (weekdays[weekday_name] - created_utc.weekday()) % 7
        candidate_date = (created_utc + timedelta(days=days_ahead)).date()
        return datetime(
            year=candidate_date.year,
            month=candidate_date.month,
            day=candidate_date.day,
            hour=23,
            minute=59,
            second=59,
            tzinfo=timezone.utc,
        )
