"""SearXNG JSON adapter. Raw server payloads never leave this module."""

from __future__ import annotations

from html import unescape
import json
import re
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit
import httpx

from music_metadata_cleaner.domain.search import SearchResult, normalized, source_domain


class SearchProvider(Protocol):
    def search(self, query: str, count: int = 8) -> list[SearchResult]: ...


class SearchError(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)


def validate_endpoint(base_url: str) -> str:
    try:
        url = urlsplit(base_url.strip())
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError()
        _ = url.port
        return urlunsplit(
            (url.scheme.lower(), url.netloc.lower(), url.path.rstrip("/"), "", "")
        )
    except (ValueError, AttributeError):
        raise SearchError("INVALID_ENDPOINT") from None


def _text(value: object) -> str:
    return (
        unescape(re.sub(r"<[^>]*>", "", value)).strip()
        if isinstance(value, str)
        else ""
    )


def normalize_search_results(payload: object) -> list[SearchResult]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SearchError("INVALID_RESPONSE")
    results = []
    seen = set()
    for rank, row in enumerate(payload["results"], 1):
        if not isinstance(row, dict):
            continue
        url, title = row.get("url"), _text(row.get("title"))
        if (
            not isinstance(url, str)
            or not url.startswith(("https://", "http://"))
            or not title
            or url in seen
        ):
            continue
        try:
            domain = source_domain(url)
        except ValueError:
            continue
        if not domain:
            continue
        seen.add(url)
        engines = row.get("engines", [])
        engine = row.get("engine") or (
            ", ".join(e for e in engines if isinstance(e, str))
            if isinstance(engines, list)
            else ""
        )
        results.append(
            SearchResult(
                title, url, _text(row.get("content")), domain, rank, _text(engine)
            )
        )
    if payload["results"] and not results:
        raise SearchError("INVALID_RESPONSE")
    return results


class SearXNGProvider:
    def __init__(
        self,
        base_url: str,
        *,
        http_client: httpx.Client | None = None,
        request_cache=None,
        timeout_seconds: float = 10,
        cache_ttl_seconds: int = 86400,
    ):
        self.base_url = base_url
        self.http_client = http_client
        self.request_cache = request_cache
        self.timeout_seconds = max(1, min(60, timeout_seconds))
        self.cache_ttl_seconds = max(0, cache_ttl_seconds)

    def search(
        self, query: str, count: int = 8, *, use_cache: bool = True
    ) -> list[SearchResult]:
        endpoint = validate_endpoint(self.base_url)
        count = max(1, min(20, count))
        # Include endpoint and normalized query; cache a full first page so result
        # count changes do not require another request. No engine-specific count API.
        key = "searxng:v1:" + json.dumps(
            [endpoint, normalized(query)], ensure_ascii=False
        )
        payload = (
            self.request_cache.get(
                "searxng", key, max_age_seconds=self.cache_ttl_seconds
            )
            if self.request_cache and use_cache
            else None
        )
        if payload is None:
            try:
                if self.http_client is None:
                    with httpx.Client(timeout=self.timeout_seconds) as client:
                        response = self._get(client, endpoint, query)
                else:
                    response = self._get(self.http_client, endpoint, query)
            except httpx.TimeoutException:
                raise SearchError("TIMEOUT") from None
            except httpx.InvalidURL:
                raise SearchError("INVALID_ENDPOINT") from None
            except httpx.HTTPError:
                raise SearchError("SERVER_UNREACHABLE") from None
            if response.status_code == 403:
                raise SearchError("JSON_FORMAT_DISABLED")
            if response.status_code in (404, 405) or 300 <= response.status_code < 400:
                raise SearchError("INVALID_ENDPOINT")
            if response.status_code >= 500:
                raise SearchError("SERVER_UNREACHABLE")
            if response.status_code != 200:
                raise SearchError("INVALID_RESPONSE")
            try:
                payload = response.json()
            except ValueError:
                raise SearchError(
                    "JSON_FORMAT_DISABLED"
                    if "text/html" in response.headers.get("content-type", "")
                    else "INVALID_RESPONSE"
                ) from None
            normalize_search_results(payload)
            if self.request_cache and use_cache:
                self.request_cache.set("searxng", key, payload)
        return normalize_search_results(payload)[:count]

    def _get(self, client, endpoint, query):
        return client.get(
            endpoint + "/search",
            params={"q": query, "format": "json"},
            headers={"Accept": "application/json"},
            timeout=self.timeout_seconds,
        )

    def test_connection(self) -> str:
        try:
            self.search("music song", use_cache=False)
            return "PASS"
        except SearchError as exc:
            return exc.status
