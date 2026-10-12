from typer.testing import CliRunner

from shopback.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "withdraw" in result.output


def test_login_requires_method():
    result = runner.invoke(app, ["login"])
    assert result.exit_code != 0
    assert "exactly one" in result.output


def test_withdraw_can_be_cancelled():
    result = runner.invoke(app, ["withdraw", "--payee-id", "p", "--amount", "100"], input="n\n")
    assert result.exit_code == 0
    assert "Initiate withdrawal" in result.output
