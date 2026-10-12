"""Cookie normalization, browser login and protected local session storage."""

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .exceptions import AuthenticationRequired, ShopBackError

DOMAIN = "shopback.com.tw"
DEFAULT_SESSION_PATH = Path.home() / ".config" / "shopback" / "session.json"


def parse_cookie_header(header: str) -> list[dict[str, Any]]:
    """Convert a Cookie request header into Playwright-style cookie records."""
    cookies = []
    for segment in header.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        if "=" not in segment:
            raise ValueError("Invalid cookie pair; expected name=value")
        name, value = segment.split("=", 1)
        name = name.strip()
        if not name or any(char.isspace() for char in name):
            raise ValueError("Invalid cookie name")
        cookies.append({"name": name, "value": value.strip(), "domain": DOMAIN, "path": "/"})
    if not cookies:
        raise ValueError("No cookies provided")
    return cookies


def _allowed_domain(domain: str) -> bool:
    domain = domain.lstrip(".").lower()
    return domain == DOMAIN or domain.endswith("." + DOMAIN)


def normalize_cookies(cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in cookies:
        if not isinstance(item, dict):
            raise ValueError("Invalid cookie record")
        name, value = item.get("name"), item.get("value")
        domain, path = item.get("domain", DOMAIN), item.get("path", "/")
        if not isinstance(name, str) or not name or not isinstance(value, str):
            raise ValueError("Invalid cookie name or value")
        if not isinstance(domain, str) or not _allowed_domain(domain):
            continue  # Ignore unrelated cookies from browser state.
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError("Invalid cookie path")
        result.append({**item, "name": name, "value": value, "domain": domain, "path": path})
    if not result:
        raise AuthenticationRequired("No ShopBack cookies found")
    return result


class SessionStore:
    """Store sensitive cookies as JSON, with private permissions and atomic replacement."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else DEFAULT_SESSION_PATH

    def _check_path(self) -> None:
        if self.path.is_symlink():
            raise ShopBackError("Refusing symlink session file")
        if self.path.exists() and not self.path.is_file():
            raise ShopBackError("Session path is not a regular file")

    def save(self, cookies: list[dict[str, Any]]) -> None:
        records = normalize_cookies(cookies)
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent.is_symlink():
            raise ShopBackError("Refusing symlink session directory")
        if os.name == "posix":
            parent.chmod(0o700)
        self._check_path()
        tmp_name = None
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=".session-", dir=parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "cookies": records}, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            if os.name == "posix":
                os.chmod(tmp_name, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(tmp_name, self.path)
        finally:
            if tmp_name is not None and os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def load(self) -> list[dict[str, Any]]:
        self._check_path()
        if not self.path.exists():
            raise AuthenticationRequired("No saved session. Run 'shopback login' first.")
        if os.name == "posix" and self.path.stat().st_mode & 0o077:
            raise ShopBackError("Session file permissions are too open; chmod 600 the file")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data["version"] != 1:
                raise ValueError("Unsupported session format")
            return normalize_cookies(data["cookies"])
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ShopBackError("Cannot load session file") from exc

    def clear(self) -> None:
        self._check_path()
        self.path.unlink(missing_ok=True)

    def exists(self) -> bool:
        self._check_path()
        return self.path.is_file()


def browser_login() -> list[dict[str, Any]]:
    """Let the user sign in and solve CAPTCHA manually in a visible browser."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ShopBackError("Install browser support: pip install 'shopback-tw-cli[browser]'") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.shopback.com.tw/", wait_until="domcontentloaded")
            print("Log in to ShopBack and complete any CAPTCHA in the Chrome window.")
            input("Press Enter here after login is complete... ")
            return normalize_cookies(context.cookies())
        finally:
            browser.close()
