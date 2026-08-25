# MusicBrainz Release Selection

Given a confirmed MusicBrainz recording ID, Music Metadata Cleaner must enrich the local file with canonical metadata without blindly selecting the first release returned by MusicBrainz.

## Request Strategy

The MusicBrainz provider performs a recording lookup using the recording MBID and requests JSON with:

```text
inc=artist-credits+releases+release-groups+media
```

The client sends a meaningful `User-Agent` header and rate-limits uncached requests to at most one request per second.

Results are cached in memory by recording ID for the lifetime of the provider instance. Cached lookups do not make another network request.

## Original-Language Preference

MusicBrainz recording and artist-credit fields are treated as the canonical display values. MusicBrainz generally stores artist credits and recording titles in their credited/original form, so the provider preserves those values instead of transliterating or normalizing them.

This means values such as:

```text
米津玄師 - Lemon
```

are preserved when MusicBrainz returns them.

## Release Scoring

Each candidate release is scored using reliable metadata signals:

- Official status: strong preference.
- Track evidence: strong preference when included media data contains a track linked to the confirmed recording ID.
- Release date: preference for dated releases.
- Release group primary type: preference for Album, Single, or EP.
- Country: small preference when available.

After scoring, ties are resolved by earliest release date, then release ID for deterministic output.

## Why Not First Release

MusicBrainz may return multiple releases for a recording, including compilations, unofficial releases, regional editions, and releases with incomplete track data. The first item in an API response is not guaranteed to be the best tagging choice.

The selection strategy favors the release with the clearest evidence that it is official, dated, and actually contains the confirmed recording as a track.

## Future Improvements

Future phases can add user preferences for:

- Preferred country.
- Preferred release type.
- Earliest release versus album release.
- Excluding compilations.
- Manual release override.
