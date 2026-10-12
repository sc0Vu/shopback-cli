import os

import pytest

from shopback.auth import SessionStore, normalize_cookies, parse_cookie_header
from shopback.exceptions import AuthenticationRequired, ShopBackError


def test_cookie_header():
    cookies = parse_cookie_header("a=one; b=two=three")
    assert [(x["name"], x["value"]) for x in cookies] == [("a", "one"), ("b", "two=three")]
    with pytest.raises(ValueError):
        parse_cookie_header("bad")


def test_domain_filter():
    cookies = normalize_cookies([
        {"name": "a", "value": "1", "domain": ".shopback.com.tw", "path": "/"},
        {"name": "b", "value": "2", "domain": "evilshopback.com.tw", "path": "/"},
    ])
    assert [x["name"] for x in cookies] == ["a"]


def test_save_load_logout(tmp_path):
    path = tmp_path / "config" / "session.json"
    store = SessionStore(path)
    with pytest.raises(AuthenticationRequired):
        store.load()
    store.save(parse_cookie_header("session=secret"))
    assert store.exists()
    assert store.load()[0]["value"] == "secret"
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
    store.clear()
    assert not store.exists()


def test_refuse_symlink(tmp_path):
    target = tmp_path / "target"
    target.write_text("secret")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ShopBackError, match="symlink"):
        SessionStore(link).save(parse_cookie_header("a=b"))
