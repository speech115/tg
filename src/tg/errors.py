class TgError(Exception):
    """Expected user-facing failure."""


class ConfigError(TgError):
    pass


class NotAuthenticatedError(TgError):
    pass


class SessionBusyError(TgError):
    pass


class UsageError(TgError):
    pass


class SkillError(TgError):
    pass
