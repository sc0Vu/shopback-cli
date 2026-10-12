"""Client exceptions."""


class ShopBackError(Exception):
    """Base client error."""


class AuthenticationRequired(ShopBackError):
    """No usable session was supplied."""


class ApiError(ShopBackError):
    """HTTP or API error."""


class SessionExpired(AuthenticationRequired):
    """Server rejected saved authentication."""


class WithdrawalOutcomeUnknown(ShopBackError):
    """A withdrawal request may have been processed despite transport failure."""
