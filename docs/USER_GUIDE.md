# User guide

[Quick start](../README.md#-quick-start) · [Documentation index](README.md)

## Connect search

1. Open **Settings → Search**.
2. Enter the **base URL** of your SearXNG instance, such as `http://localhost:8080`. Do not append `/search`, a query, credentials, or a fragment.
3. Click **Test Connection**. A working JSON endpoint returns **PASS**.
4. Click **Save**.

A browser search working does not guarantee JSON access. Your instance must allow JSON search responses. Its search configuration should include:

```yaml
search:
  formats:
    - html
    - json
```

There is no built-in server or API key. `SEARXNG_URL` overrides the saved setting. The app also loads `.env` from the folder it is launched in, without overriding existing environment variables:

```dotenv
SEARXNG_URL=http://localhost:8080
```

Restart after editing `.env`. To use the saved URL instead, remove the environment override. Do not publish your personal `.env`.

## Scan, review, apply

1. **Add Files** selects MP3s; **Add Folder** discovers MP3s in a folder. Files are read, not changed.
2. **Scan & Preview** searches the loaded list using up to two queries per track, stopping early for strong evidence. Cancel is available during processing.
3. Select a row. The detail panel compares **Current** and **Proposed** values; changed proposals receive subtle emphasis. Drag the divider to adjust space or scroll long details.
4. Use **View Search Evidence** to inspect the original/cleaned filename, queries, candidate scores, domains, titles, URLs, and snippets.
5. Resolve uncertain tracks using the options below.
6. **Apply Selected** applies selected rows with valid, reviewed proposals. **Apply All High Confidence** selects eligible High-confidence rows. Both require confirmation and follow the saved Files & Safety settings.

The filename convention is `Artist - Title.mp3`, in the existing folder. Invalid filename characters are sanitized. The search workflow changes artist/title, not album/year enrichment; existing supported fields are preserved. The detail panel can show “-” for fields with no proposed replacement.

## When search needs help

| Action | Use it when |
| --- | --- |
| **Search keywords → Search** | You know useful text missing from the filename/tags. Search applies to the first selected row; Return also submits. |
| **Use Candidate** | Search found plausible alternatives. Inspect evidence, choose the correct identity, and confirm the selection. |
| **Edit Artist / Title / Lyrics** | You know the values yourself, even if search found nothing. No network request is required. |

`track001.mp3` or a generic recommendation name with no useful tags returns **Insufficient Information**. The app cannot identify audio content.

In the manual editor, Artist and Title are editable dropdowns containing filename fragments, existing tags, and available candidates. Choose, type, or **Swap Artist / Title**. Suggestions are unverified text, not guaranteed identities.

![Manual editor with editable artist/title suggestions and optional lyrics](images/manual-edit.png)
*Demonstration values in the actual Qt editor.*

**Save Preview** stages changes only. A changed identity displays **Manual confirmed**, not an invented High score. Use **Apply Selected** to write it. Rescanning creates a fresh search preview and can replace an unsaved manual proposal.

## Understand the table

Columns: **File | Artist | Title | Confidence | Lyrics | Status**. Hover over truncated text to read the full value.

| Indicator | Meaning / next step |
| --- | --- |
| High / Medium / Low | Strength of textual evidence, not a probability. Medium/Low need explicit review. |
| Manual confirmed | Artist/title was explicitly entered or changed by the user. |
| Found / Not Found | Usable existing/proposed plain lyrics are present / absent. This does not affect identity confidence. |
| Ready / Ready (manual) | A proposal is available for confirmed application. |
| Review | Evidence is missing, ambiguous, or awaiting confirmation. Inspect sources, search, or edit. |
| Insufficient Information | No useful automatic search text. Provide keywords or edit values. |
| Lyrics Not Found | Identity can still be applied; lyrics are unavailable. |
| Search Failed | Check the endpoint, connection diagnostics, or retry later. |
| Invalid MP3 / Cancelled / Applied | File could not be read / processing stopped / changes were applied. |

**Not Found** also covers lyrics not yet retrieved or unavailable because of a lookup failure. It is not proof that lyrics do not exist online. See [confidence rules](CONFIDENCE_AND_MANUAL_EDIT.md).

## Lyrics

LRCLIB supplies plain lyrics only after High-confidence resolution or explicit candidate selection. Existing lyrics are kept by default. Missing or mismatched online lyrics do not block artist/title cleanup; mismatched lyrics are not written.

To supply lyrics yourself, open the manual editor, enable **Use manually entered plain lyrics**, and paste/type text. If lyrics already exist, explicitly confirm replacement for that file. **Update ID3** must be enabled to write lyrics. Manually entered lyrics can be written even when online retrieval is disabled. No synchronized lyrics or `.lrc` export is available.

## Settings

| Tab | Controls and defaults |
| --- | --- |
| General | Default music folder; fixed `Artist - Title.mp3` format and original-language preservation |
| Search | SearXNG URL; maximum results **8** (1–20); timeout **10 seconds** (1–60); automatic search on; Test Connection |
| Lyrics | Retrieve plain lyrics on; preserve existing lyrics on; overwrite off |
| Files & Safety | Rename, Update ID3, and backup all on |
| Advanced | Search cache expiration **86400 seconds**; Clear search cache; history/log paths; diagnostics guidance |

With automatic search disabled, use Manual Search. For automatic lyrics replacement, disable preservation and explicitly enable overwrite. These remain separate controls. **Save** persists settings; **Cancel** discards edits. Connection tests and cache clearing take effect immediately, even if you later cancel the dialog.

## List cleanup, history, and safety

- **Remove** removes selected rows; **Clear** empties the list. Neither deletes MP3s.
- **Remove Applied Rows** removes only rows successfully applied through **Apply All High Confidence**. It does not remove every High row or every manually applied row.
- **History** shows the most recent 25 operations. **Undo Last Batch** asks for confirmation, then restores supported original tags and names, including successful files in a partially applied batch.
- SQLite history is recorded before modification. Backups are enabled by default and retain full original file bytes. Undo uses supported tag snapshots, not a complete arbitrary-frame restore.
- Existing target names and backup files are never silently overwritten. A changed tag snapshot requires a fresh preview. Rename requires filesystem hard-link support and fails safely when unsupported.
- **Show Log** reveals the normally hidden message panel. Advanced lists the persistent log and history locations.

New installations use `%LOCALAPPDATA%/MusicMetadataCleaner` on Windows. Linux uses `$XDG_CONFIG_HOME/MusicMetadataCleaner` (default `~/.config`) for preferences/history and `$XDG_CACHE_HOME/MusicMetadataCleaner` (default `~/.cache`) for logs. Search cache shares the history database and can be cleared independently. Existing project-local preferences/history are adopted without moving or deleting them.

## Troubleshooting

| Test/status | Check |
| --- | --- |
| INVALID_ENDPOINT | Use a valid HTTP(S) base URL; remove `/search`, query parameters, and embedded credentials. |
| JSON_FORMAT_DISABLED | Enable JSON and check access restrictions. HTML responses and HTTP 403 produce this diagnostic. |
| SERVER_UNREACHABLE / TIMEOUT | Check the server, network, and configured timeout. |
| INVALID_RESPONSE | Confirm the endpoint returns the expected SearXNG JSON structure. |
| Search works, identity stays Review | Search results do not establish one supported identity. Use Candidate or manual editing. |
| Apply/undo conflict | Inspect the message/log and resolve filename or backup collisions yourself; never rely on silent overwrite. |
| Qt DLL/import error | Use a clean virtual environment with compatible PySide6 libraries; see [build guide](BUILD.md). |

A High label is not a correctness guarantee. The recorded 15-song baseline and remaining parser limitations are documented in [Search benchmark](SEARCH_BENCHMARK.md).
