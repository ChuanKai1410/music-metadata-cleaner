"""Provider error types."""


class ProviderError(RuntimeError):
    """Base class for metadata provider failures."""


class ProviderTimeoutError(ProviderError):
    """Raised when a provider request times out."""


class ProviderNetworkError(ProviderError):
    """Raised when a provider request fails due to networking."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider reports rate limiting."""


class ProviderResponseError(ProviderError):
    """Raised when a provider response is invalid or unsuccessful."""

