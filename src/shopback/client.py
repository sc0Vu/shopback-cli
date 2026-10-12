"""HTTP API client. Endpoints are based on observed browser requests, not an official API."""

import json
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from .auth import SessionStore, normalize_cookies, parse_cookie_header
from .exceptions import ApiError, AuthenticationRequired, SessionExpired, WithdrawalOutcomeUnknown

BASE_URL = "https://www.shopback.com.tw"


class ShopBackClient:
    def __init__(
        self,
        *,
        cookie: str | None = None,
        cookies: list[dict[str, Any]] | None = None,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ):
        if cookie is not None and cookies is not None:
            raise ValueError("Provide cookie or cookies, not both")
        if cookie is not None:
            cookies = parse_cookie_header(cookie)
        if cookies is None:
            raise AuthenticationRequired("Provide cookies or load a saved session")
        jar = httpx.Cookies()
        for item in normalize_cookies(cookies):
            jar.set(item["name"], item["value"], domain=item["domain"], path=item["path"])
        self._http = httpx.Client(
            base_url=BASE_URL,
            cookies=jar,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Content-Type": "text/plain;charset=UTF-8",
                "X-Shopback-Screen": "/payment",
                "Referer": BASE_URL + "/payment",
            },
        )

    @classmethod
    def from_saved_session(
        cls,
        store: SessionStore | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> "ShopBackClient":
        return cls(cookies=(store or SessionStore()).load(), transport=transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ShopBackClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _post(self, endpoint: str, payload: dict[str, Any], *, money_moving: bool = False) -> dict[str, Any]:
        try:
            response = self._http.post(
                endpoint, content=json.dumps(payload, separators=(",", ":")),
            )
        except httpx.RequestError as exc:
            if money_moving:
                raise WithdrawalOutcomeUnknown(
                    "Withdrawal transport failed; outcome unknown. Check your account before retrying."
                ) from exc
            raise ApiError("Network request failed") from exc
        if response.status_code in (401, 403):
            raise SessionExpired("Session rejected. Please log in again.")
        if response.is_redirect:
            raise SessionExpired("Unexpected redirect; authentication may have expired")
        if response.status_code >= 400:
            if endpoint != "/api/payment/withdraw":
                raise ApiError(f"ShopBack API returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ApiError("Expected JSON response from ShopBack") from exc
        if not isinstance(data, dict):
            raise ApiError("Expected JSON object from ShopBack")
        return data

    def withdraw(
        self, payee_id: str, amount: Decimal | str | int, otp_request_id: str | None = None
    ) -> dict[str, Any]:
        if not payee_id.strip():
            raise ValueError("payee_id must not be empty")
        try:
            decimal_amount = Decimal(str(amount))
        except InvalidOperation as exc:
            raise ValueError("Invalid amount") from exc
        if not decimal_amount.is_finite() or decimal_amount <= 0:
            raise ValueError("Amount must be finite and positive")
        # Preserve numeric JSON rather than sending a quoted decimal.
        if decimal_amount != decimal_amount.to_integral_value():
            raise ValueError("Amount must be an integer in TWD")
        payload: dict[str, Any] = {
            "payee": {"_id": payee_id}, "form": {"amount": int(decimal_amount)}
        }
        if otp_request_id is not None:
            if not otp_request_id.strip():
                raise ValueError("otp_request_id must not be empty")
            payload["otp"] = {"request_id": otp_request_id}
            payload["commit"] = True
        return self._post("/api/payment/withdraw", payload, money_moving=True)

    def send_otp(self) -> dict[str, Any]:
        session = self._post(
            "/api/auth/me/start-otp-session",
            {"target": "cashout", "mobile_country_code": "", "mobile_number": ""},
        )
        session_id = session.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ApiError("OTP session response did not contain session_id")
        sent = self._post(
            "/api/auth/v2/send-otp", {"session_id": session_id, "channel": "sms"}
        )
        return {**sent, "session_id": session_id}

    def verify_otp(self, session_id: str, request_id: str, otp: str) -> dict[str, Any]:
        if not all((session_id, request_id, otp)):
            raise ValueError("session_id, request_id and otp are required")
        return self._post(
            "/api/auth/v2/verify-otp",
            {"session_id": session_id, "request_id": request_id, "otp": otp},
        )
