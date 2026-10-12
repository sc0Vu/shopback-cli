# ShopBack Taiwan CLI (unofficial)

Python CLI and SDK built from observed browser requests. **Not affiliated with ShopBack.** The API is undocumented and can change. Not tested against live ShopBack servers. Use only with your own account and respect the service's terms.

## Install

```bash
pip install -e .
# For interactive Chrome login (requires installed Google Chrome):
pip install -e '.[browser]'
# For development:
pip install -e '.[dev,browser]'
```

## Authentication

```bash
shopback login --cookie   # Hidden prompt for the complete Cookie request header
shopback login --browser  # Opens visible Chrome; log in and complete CAPTCHA manually
shopback status           # Checks saved-file presence, NOT server authentication
shopback logout           # Deletes local session; does not revoke remote cookies
```

Saved cookies: `~/.config/shopback/session.json` (directory mode 0700, file mode 0600 on Unix). **The file is plaintext and is as sensitive as a password.** Never commit it or share it. Windows permissions follow the OS defaults; use a private user profile. Set `SHOPBACK_COOKIE` to override the saved session for API calls (avoid putting secrets into shell history).

## Withdrawal

```bash
shopback withdraw --payee-id YOUR_PAYEE_ID --amount 100
```

The CLI confirms before the first request and before the OTP-backed final submission. A withdrawal may be initiated by the initial request, even if OTP is not required. **Never automatically retry a withdrawal after network failure**; first check your account. API response fields are not yet fully documented. In particular, the CLI requires `{"success": true}` for OTP verification; if ShopBack uses a different response shape, it stops safely. Capture a *redacted* response and adapt the check before relying on it.

SDK example:

```python
from shopback import ShopBackClient

with ShopBackClient.from_saved_session() as client:
    first = client.withdraw("PAYEE_ID", 100)
    if first.get("isOtpRequired"):
        session = client.send_otp()
        request_id = session.get("request_id") or session.get("requestId")
        verified = client.verify_otp(session["session_id"], request_id, input("OTP: "))
        if verified.get("success") is True:
            # Confirm with the user before committing a money-moving action.
            final = client.withdraw("PAYEE_ID", 100, otp_request_id=request_id)
```

## Development

```bash
python -m pytest -q
ruff check .
python -m compileall -q src
```

Only the four endpoints seen in browser traffic are implemented. `status` does not call a guessed account endpoint. Browser login requires user interaction; CAPTCHA is not bypassed. Browser login stores cookies, not localStorage tokens. If ShopBack requires additional browser-bound authentication, the API calls may fail.
