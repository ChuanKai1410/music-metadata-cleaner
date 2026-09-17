"""Search connection diagnostics exposed to the UI."""

from music_metadata_cleaner.providers.search import SearXNGProvider


def test_search_connection(base_url: str, timeout_seconds: int = 10) -> str:
    return SearXNGProvider(base_url, timeout_seconds=timeout_seconds).test_connection()
