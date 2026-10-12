"""Command-line interface."""

import json
import os
from getpass import getpass
from typing import Any

import typer

from .auth import SessionStore, browser_login, parse_cookie_header
from .client import ShopBackClient
from .exceptions import ShopBackError

app = typer.Typer(help="Unofficial ShopBack Taiwan CLI", no_args_is_help=True)
otp_app = typer.Typer(help="OTP operations")
app.add_typer(otp_app, name="otp")


def _print_response(value: dict[str, Any]) -> None:
    # API responses might contain secrets. Do not dump unfiltered responses.
    safe = {
        k: v for k, v in value.items() if k in {"isOtpRequired", "status", "success", "message"}
    }
    typer.echo(json.dumps(safe, ensure_ascii=False, indent=2))
    if not safe:
        typer.echo("API response received (details omitted to protect credentials).")


def _client() -> ShopBackClient:
    cookie = os.environ.get("SHOPBACK_COOKIE")
    return ShopBackClient(cookie=cookie) if cookie else ShopBackClient.from_saved_session()


@app.command()
def login(
    browser: bool = typer.Option(False, "--browser", help="Log in using visible Chrome"),
    cookie: bool = typer.Option(False, "--cookie", help="Paste a Cookie request header"),
) -> None:
    """Save authentication cookies locally."""
    if browser == cookie:
        raise typer.BadParameter("Choose exactly one of --browser or --cookie")
    records = browser_login() if browser else parse_cookie_header(getpass("Cookie header: "))
    SessionStore().save(records)
    typer.echo("Session saved locally. Authentication validity is not yet verified.")


@app.command()
def status() -> None:
    """Show whether a local session exists (not server-side authentication status)."""
    store = SessionStore()
    if store.exists():
        store.load()
        typer.echo("Saved session found. Server-side validity is unknown.")
    else:
        typer.echo("No saved session.")


@app.command()
def logout() -> None:
    """Delete locally saved cookies; does not revoke the remote session."""
    SessionStore().clear()
    typer.echo("Local session deleted.")


@app.command()
def withdraw(
    payee_id: str = typer.Option(..., "--payee-id"),
    amount: str = typer.Option(..., "--amount"),
) -> None:
    """Withdraw with optional SMS OTP. Confirm before initiating any withdrawal."""
    typer.echo(f"Payee: {payee_id} | Amount: TWD {amount}")
    if not typer.confirm("Initiate withdrawal request?", default=False):
        raise typer.Exit()
    with _client() as client:
        result = client.withdraw(payee_id, amount)
        if result.get("isOtpRequired") is not True:
            _print_response(result)
            return
        typer.echo("OTP required. Requesting SMS...")
        session = client.send_otp()
        session_id = session["session_id"]
        request_id = session.get("request_id") or session.get("requestId")
        if not isinstance(request_id, str) or not request_id:
            raise ShopBackError("OTP response missing request_id; cannot continue")
        code = getpass("SMS OTP: ")
        verification = client.verify_otp(session_id, request_id, code)
        # Response schema is unverified. Never treat an unknown result as verified.
        if verification.get("status") != "OK":
            typer.echo("OTP verification not explicitly confirmed by API. Stopping safely.")
            _print_response(verification)
            raise typer.Exit(code=1)
        if typer.prompt("Type WITHDRAW to submit", default="") != "WITHDRAW":
            raise typer.Exit()
        result = client.withdraw(payee_id, amount, otp_request_id=request_id)
        _print_response(result)


@otp_app.command("send")
def otp_send() -> None:
    """Send SMS OTP (session identifiers intentionally not printed)."""
    with _client() as client:
        result = client.send_otp()
    typer.echo("OTP request sent. Use SDK to access session/request IDs.")
    _print_response(result)


@otp_app.command("verify")
def otp_verify(
    session_id: str = typer.Option(..., "--session-id"),
    request_id: str = typer.Option(..., "--request-id"),
) -> None:
    """Verify a manually supplied OTP."""
    with _client() as client:
        result = client.verify_otp(session_id, request_id, getpass("SMS OTP: "))
    _print_response(result)


def main() -> None:
    try:
        app()
    except (ShopBackError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    main()
