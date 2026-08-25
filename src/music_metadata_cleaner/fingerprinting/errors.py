"""Fingerprinting error types."""


class FingerprintingError(RuntimeError):
    """Base class for fingerprinting failures."""


class FpcalcNotFoundError(FingerprintingError):
    """Raised when the fpcalc executable is unavailable."""


class FingerprintTimeoutError(FingerprintingError):
    """Raised when fpcalc does not complete before the timeout."""


class FingerprintGenerationError(FingerprintingError):
    """Raised when fpcalc fails or returns unusable output."""

