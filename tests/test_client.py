import json

import httpx
import pytest

from shopback import ShopBackClient
from shopback.exceptions import ApiError, SessionExpired, WithdrawalOutcomeUnknown


def test_withdraw_and_otp_flow():
    seen = []

    def handler(request):
        assert request.headers["cookie"] == "auth=secret"
        assert request.headers["content-type"] == "text/plain;charset=UTF-8"
        body = json.loads(request.content)
        seen.append((request.url.path, body))
        path = request.url.path
        if path == "/api/payment/withdraw":
            return httpx.Response(200, json={"isOtpRequired": "otp" not in body})
        if path == "/api/auth/me/start-otp-session":
            return httpx.Response(200, json={"session_id": "sid"})
        if path == "/api/auth/v2/send-otp":
            return httpx.Response(200, json={"request_id": "rid"})
        return httpx.Response(200, json={"success": True})

    with ShopBackClient(cookie="auth=secret", transport=httpx.MockTransport(handler)) as client:
        assert client.withdraw("payee", 100)["isOtpRequired"]
        session = client.send_otp()
        assert session == {"request_id": "rid", "session_id": "sid"}
        assert client.verify_otp("sid", "rid", "123456")["success"]
        assert not client.withdraw("payee", 100, "rid")["isOtpRequired"]
    assert seen[0][1] == {"payee": {"_id": "payee"}, "form": {"amount": 100}}
    assert seen[-1][1]["commit"] is True
    assert seen[-1][1]["otp"] == {"request_id": "rid"}


@pytest.mark.parametrize("amount", ["0", "-1", "NaN", "Infinity", "1.5", "nope"])
def test_invalid_amount(amount):
    with ShopBackClient(cookie="auth=secret") as client:
        with pytest.raises(ValueError):
            client.withdraw("payee", amount)


def test_unauthorized():
    transport = httpx.MockTransport(lambda _: httpx.Response(401, json={}))
    with ShopBackClient(cookie="auth=secret", transport=transport) as client:
        with pytest.raises(SessionExpired):
            client.send_otp()


def test_bad_otp_response():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"oops": True}))
    with ShopBackClient(cookie="auth=secret", transport=transport) as client:
        with pytest.raises(ApiError, match="session_id"):
            client.send_otp()


def test_ambiguous_withdraw_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("timeout")

    with ShopBackClient(cookie="auth=secret", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WithdrawalOutcomeUnknown):
            client.withdraw("payee", 100)
    assert len(calls) == 1
