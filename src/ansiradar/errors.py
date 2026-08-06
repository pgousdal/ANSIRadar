"""Expected failures shared by sources, replay, and polling."""


class SourceError(Exception):
    """Base class for expected source failures."""


class SourceUnavailable(SourceError):
    """The source could not be read or reached."""


class InvalidSourceData(SourceError):
    """The source body is not valid JSON or is structurally unusable."""


class UnsupportedSource(SourceError):
    """The source URI or JSON schema is unsupported."""


class ResponseTooLarge(SourceError):
    """The source response exceeded the configured size limit."""


class ReplayExhausted(SourceError):
    """A replay source has no further records."""
