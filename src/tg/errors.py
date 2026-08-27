class TgError(Exception):
    """Expected user-facing failure."""


class ConfigError(TgError):
    pass


class NotAuthenticatedError(TgError):
    pass
