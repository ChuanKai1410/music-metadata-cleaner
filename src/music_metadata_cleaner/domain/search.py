"""Deterministic text-only candidate extraction, agreement and confidence rules."""

from __future__ import annotations
from dataclasses import dataclass, replace
import re
import unicodedata
from urllib.parse import urlsplit
from music_metadata_cleaner.domain.models import TrackMetadata


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source_domain: str = ""
    rank: int = 1
    engine: str = ""

    @property
    def domain(self) -> str:
        return self.source_domain


@dataclass(frozen=True)
class ResolvedTrackIdentity:
    artist: str
    title: str
    confidence: str
    evidence: tuple[SearchResult, ...]
    search_query: str
    source_summaries: tuple[str, ...] = ()
    internal_score: int = 0
    evidence_breakdown: tuple[str, ...] = ()

    @property
    def confidence_level(self) -> str:
        return self.confidence


def normalized(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    text = text.translate(
        str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
    )
    return " ".join(text.split())


def artist_key(value: str) -> str:
    text = re.sub(
        r"\s+(?:x|and|feat\.?|ft\.?|featuring)\s+|\s*[&×,、]\s*", "|", normalized(value)
    )
    return "|".join(sorted(part.strip() for part in text.split("|") if part.strip()))


NOISE = r"official music video|official lyric video|official video|official audio|official MV|lyric video|lyrics video|full version|(?:full\s+)?HD|HQ|1080p|720p|2160p|4K|MV|PV|visualizer"


def clean_filename(filename: str) -> str:
    text = re.split(r"[/\\]", filename)[-1]
    text = re.sub(r"\.mp3$", "", text, flags=re.I)
    text = re.sub(
        r"^(?:tomp3\.cc|ytmp3|y2mate|x2mate|yt5s)(?:\.(?:com|io|cc))?\s*[-–—_]*\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"[\[（(【]\s*(?:(?:"
        + NOISE
        + r")|\d+\s*kbps|lyrics|audio|download)(?:\s+(?:"
        + NOISE
        + r"))*\s*[\]）)】]",
        " ",
        text,
        flags=re.I,
    )
    # Bare short words such as Audio, Download, Full and Lyrics can be titles.
    # Preserve them except a Lyrics suffix on an already structured artist/title.
    while True:
        cleaned = re.sub(r"\s+(?:" + NOISE + r")\s*$", "", text, flags=re.I).strip(
            " -–—_"
        )
        if cleaned == text:
            break
        text = cleaned
    return " ".join(text.split())


class FilenameCleaner:
    def clean(self, filename: str) -> str:
        return clean_filename(filename)


def useful_text(value: str) -> bool:
    text = normalized(value)
    if not any(c.isalpha() for c in text):
        return False
    if re.fullmatch(
        r"(?:track|audio|song|untitled|unknown|download|recording)[\s_\-]*\d*", text
    ):
        return False
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", text) and any(c.isdigit() for c in text):
        return False
    return not any(
        label in text
        for label in (
            "流行歌曲推荐",
            "歌曲推荐",
            "tiktok",
            "抖音热门",
            "best songs",
            "music compilation",
        )
    )


def build_search_queries(
    filename: str, metadata: TrackMetadata, keywords: str | None = None
) -> tuple[str, ...]:
    cleaned = clean_filename(filename)
    texts = []
    if keywords is not None:
        if keywords.strip():
            texts.append(keywords)
    else:
        if (
            metadata.artist
            and metadata.title
            and useful_text(metadata.artist)
            and useful_text(metadata.title)
        ):
            texts.append(f"{metadata.artist} {metadata.title}")
        if useful_text(cleaned):
            texts.append(cleaned)
        elif metadata.title and useful_text(metadata.title):
            texts.append(metadata.title)
    texts = list(
        dict.fromkeys(" ".join(t.replace('"', "").split())[:400] for t in texts)
    )
    if not texts:
        return ()
    # Two queries maximum, with a filename alternative when ID3 could be wrong.
    return (
        f'"{texts[0]}"',
        (
            f'"{texts[1]}" song'
            if len(texts) > 1 and normalized(texts[1]) != normalized(texts[0])
            else f'"{texts[0]}" song'
        ),
    )


class SearchQueryBuilder:
    def build(
        self, filename: str, metadata: TrackMetadata, keywords: str | None = None
    ) -> tuple[str, ...]:
        return build_search_queries(filename, metadata, keywords)


PRIMARY = {"spotify.com", "apple.com", "youtube.com", "soundcloud.com", "bandcamp.com"}
SECONDARY = {"genius.com", "musixmatch.com", "last.fm", "discogs.com", "wikipedia.org"}


def source_domain(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    if host == "youtu.be":
        return "youtube.com"
    for domain in PRIMARY | SECONDARY:
        if host == domain or host.endswith("." + domain):
            return domain
    # Conservative publisher grouping, including common multi-label suffixes.
    parts = host.split(".")
    suffix_length = (
        3
        if len(parts) > 2
        and parts[-2] in {"co", "com", "org", "net"}
        and len(parts[-1]) == 2
        else 2
    )
    return ".".join(parts[-suffix_length:])


def source_weight(url: str) -> int:
    domain = source_domain(url)
    return 15 if domain in PRIMARY else 10 if domain in SECONDARY else 3


SITE = r"YouTube|Spotify|Apple Music|Genius|SoundCloud|Musixmatch|Bandcamp|Last\.fm|Discogs|Wikipedia"


def _result_text(value: str) -> str:
    text = value.strip()
    while True:
        stripped = re.sub(r"\s*[-–—|]\s*(?:" + SITE + r")\s*$", "", text, flags=re.I)
        if stripped == text:
            break
        text = stripped
    text = clean_filename(text)
    if re.search(r"\s[-–—|:]\s", text) or re.search(r"\sby\s", text, re.I):
        text = re.sub(r"\s+Lyrics$", "", text, flags=re.I)
    return text


def extract_candidates(result: SearchResult) -> list[tuple[str, str, bool]]:
    text = _result_text(result.title)
    match = re.match(
        r"^(.+?)\s+(?:[-–—]\s*)?(?:song|single)\s+by\s+(.+?)(?:\s+on\s+(?:Apple Music|Spotify))?$",
        text,
        re.I,
    )
    if not match:
        match = re.match(
            r"^(.+?)\s+by\s+(.+?)(?:\s+on\s+(?:Apple Music|Spotify))?$", text, re.I
        )
    if match:
        return [(match[2].strip(), match[1].strip(" -–—"), True)]
    parts = re.split(r"\s+[-–—|]\s+|:\s+", text, maxsplit=1)
    if len(parts) == 2 and all(useful_text(p) for p in parts):
        return [(parts[0], parts[1], False), (parts[1], parts[0], False)]
    return []


VERSION = r"\b(?:live|remix|acoustic|cover|instrumental|remaster(?:ed)?|sped up|slowed|reverb|radio edit|extended)\b"


def version_markers(text: str) -> frozenset[str]:
    return frozenset(re.findall(VERSION, normalized(text)))


def _contains(text: str, phrase: str) -> bool:
    # Word boundaries on Latin tokens, substring comparison for CJK scripts.
    return bool(
        re.search(
            r"(?<![a-z0-9])" + re.escape(normalized(phrase)) + r"(?![a-z0-9])",
            normalized(text),
        )
    )


class RuleBasedIdentityResolver:
    def resolve(
        self,
        cleaned_filename: str,
        metadata: TrackMetadata,
        results: list[SearchResult],
        search_query: str = "",
        *,
        original_filename: str = "",
    ) -> tuple[ResolvedTrackIdentity, ...]:
        groups = {}
        for result in results:
            for artist, title, explicit in extract_candidates(result):
                key = (artist_key(artist), normalized(title))
                groups.setdefault(key, []).append((artist, title, result, explicit))
        identities = []
        input_text = normalized(cleaned_filename)
        for key, entries in groups.items():
            artist, title = entries[0][:2]
            id3_artist = bool(metadata.artist and artist_key(metadata.artist) == key[0])
            id3_title = bool(metadata.title and normalized(metadata.title) == key[1])
            filename_artist = all(
                _contains(input_text, part) for part in key[0].split("|")
            )
            filename_title = _contains(input_text, title)
            explicit = any(e[3] for e in entries)
            # Determine direction through explicit syntax, ID3 or artist-first input.
            # Reverse pairs remain possible only when direction has actual support.
            starts_artist = any(
                input_text.startswith(part) for part in key[0].split("|")
            )
            oriented = (
                explicit
                or id3_artist
                or (filename_artist and filename_title and starts_artist)
            )
            if not oriented:
                continue
            if not (filename_artist or filename_title or id3_artist or id3_title):
                continue
            evidence = tuple({e[2].url: e[2] for e in entries}.values())
            domains = {source_domain(e.url) for e in evidence} - {""}
            filename_points = (
                25
                if filename_artist and filename_title
                else 10 if filename_title else 5 if filename_artist else 0
            )
            id3_points = (
                15 if id3_artist and id3_title else 5 if id3_artist or id3_title else 0
            )
            agreement = min(30, max(0, len(domains) - 1) * 15)
            reliability = max((source_weight(e.url) for e in evidence), default=0)
            consistency = 15 if explicit or id3_artist or starts_artist else 0
            score = filename_points + id3_points + agreement + reliability + consistency
            breakdown = [
                f"Filename: {filename_points}/25",
                f"Existing ID3: {id3_points}/15",
                f"Independent source agreement: {agreement}/30 ({len(domains)} domains)",
                f"Source reliability: {reliability}/15",
                f"Artist/title orientation: {consistency}/15",
            ]
            conflict = version_markers(cleaned_filename) != version_markers(title)
            if conflict:
                score = min(59, max(0, score - 25))
                breakdown.append("Version disagrees with filename: -25, capped at Low")
            # Hard gates prevent one source or unrelated input becoming High.
            if (
                len(domains) < 2
                or reliability < 10
                or not (filename_points == 25 or id3_points == 15)
            ):
                score = min(score, 79)
            score = min(100, score)
            # Use supported display strings. Never translate or infer artist aliases.
            display = max(
                entries,
                key=lambda e: (
                    sum(ord(c) > 127 for c in e[0]) > 0
                    and any(
                        ord(c) > 127 for c in cleaned_filename + (metadata.artist or "")
                    ),
                    source_weight(e[2].url),
                    -e[2].rank,
                ),
            )
            confidence = "High" if score >= 80 else "Medium" if score >= 60 else "Low"
            identities.append(
                ResolvedTrackIdentity(
                    display[0],
                    display[1],
                    confidence,
                    evidence,
                    search_query,
                    (f"{len(domains)} independent sources agree",),
                    score,
                    tuple(breakdown),
                )
            )
        identities.sort(
            key=lambda c: (
                -c.internal_score,
                -len(c.evidence),
                normalized(c.artist),
                normalized(c.title),
            )
        )
        if len(identities) > 1:
            # Competing plausible artists, titles, versions and untranslated aliases
            # require review; never merge different recordings to inflate confidence.
            identities = [
                replace(
                    c,
                    internal_score=min(c.internal_score, 59),
                    confidence="Low",
                    evidence_breakdown=c.evidence_breakdown
                    + ("Competing identities or versions: capped at Low",),
                )
                for c in identities
            ]
        return tuple(identities)
