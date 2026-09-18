# Live 15-file benchmark — 17 September 2026

> Historical baseline: measurements and artifacts below are preserved from this run. Subsequent UI/manual-edit work did not rerun or retune this benchmark. See the [current benchmark guide](../../SEARCH_BENCHMARK.md) for interpretation and repeat instructions, or the [user guide](../../USER_GUIDE.md) for current controls.

## Outcome

- SearXNG JSON connection: PASS. The endpoint was loaded from the project .env; no API key was used.
- 15 exact user-selected MP3s processed; 2 High, 0 Medium, 13 Low.
- 3 identity proposals: 2 High and 1 Low. The remaining 12 had no final proposed identity.
- 13 Review statuses; 0 Search Failed; 0 Insufficient Information. Two queries returned no results for their files and remained Review.
- Initial lyrics statuses: 2 Lyrics Not Found, due to sandbox network restrictions on LRCLIB.
- Follow-up with permitted network access: Kesha / TiK ToK plain lyrics Found, no lyrics-review flag; Neoni x burnboy / Champion Not Found.
- All 15 SHA-256 hashes matched before and after. No apply, rename, tag write, backup or undo was invoked.
- Production code and scoring were not changed during this benchmark.
- Initial run duration: 40.7 seconds; maximum 8 results per query; timeout 10 seconds.

## Correctness interpretation

The two High proposals agree with the supplied filenames, existing ID3 and returned search titles. No High proposal was visibly contradicted by that textual evidence. However, no independently verified ground-truth manifest was supplied, so the machine-readable correctness column remains Unverified for all 15. This is not a measured 100% accuracy claim, and no audio identification was performed.

Formal Correct High / Correct Medium / Incorrect metrics are therefore not scored yet. Observed automatic High resolution rate is 2/15 (13.3%). One additional Low identity is available for manual review. This real-world baseline shows the current resolver needs further work despite the mocked test suite passing.

## Per-file results

| # | File | Confidence | Proposed Artist / Title | Results | Candidates | Observation |
|---|---|---|---|---:|---:|---|
| 1 | Imagine Dragons - Warriors (Lyrics).mp3 | Low | — | 15 | 7 | Correct-looking main candidate exists, but presentation variants are treated as competing identities. |
| 2 | K-On!! - U&I [Full English Sub].mp3 | Low | — | 16 | 4 | Series/character metadata and encyclopedia page names are mistaken for song candidates. |
| 3 | Kesha - TiK ToK (Lyrics).mp3 | High | Kesha / TiK ToK | 8 | 1 | High proposal agrees with filename, ID3, YouTube and Genius; plain lyrics found on permitted retry. |
| 4 | KeyKey - 當想你成為習慣『一個人說著晚安，失了魂丟了期盼。』【動態歌詞Lyrics】.mp3 | Low | — | 13 | 3 | Quoted lyric tails and DJ/version labels prevent clean grouping. Version needs review. |
| 5 | LEGENDS NEVER DIE _ LYRICS _ LEAGUE OF LEGENDS.mp3 | Low | — | 8 | 0 | Useful text and results exist, but no artist/title pair survives extraction. |
| 6 | Lil Nas X - MONTERO (Call Me By Your Name) (Lyrics).mp3 | Low | — | 14 | 6 | Parser incorrectly splits the title phrase Call Me By Your Name at By, creating false artist candidates. |
| 7 | Lizm Ladyhao - 紙短情長『我的故事都是關於你呀。』【動態歌詞Lyrics】.mp3 | Low | — | 15 | 3 | Quoted lyric tails and site suffixes are not cleaned sufficiently. |
| 8 | Neoni & burnboy - Champion.mp3 | High | Neoni x burnboy / Champion | 8 | 1 | High proposal agrees with filename, ID3, YouTube and Genius. LRCLIB returned no result on permitted retry. |
| 9 | Ngây Thơ - Tăng Duy Tân x Phong Max  _ Phong Max remix _.mp3 | Low | — | 6 | 2 | Remix evidence requires review; site/download suffixes contaminate candidates. |
| 10 | tomp3.cc - The Chainsmokers  Who Do You Love Lyric Video ft 5 Seconds of Summer.mp3 | Low | — | 9 | 0 | Embedded Lyric Video text remains in queries; returned titles omit artist and are not resolved. |
| 11 | tomp3.cc - The Chainsmokers ILLENIUM  Takeaway Official Video ft Lennon Stella.mp3 | Low | The Chainsmokers & ILLENIUM Ft. Lennon Stella / Takeaway | 12 | 1 | One Low proposal: The Chainsmokers & ILLENIUM Ft. Lennon Stella / Takeaway. Manual confirmation required. |
| 12 | tomp3.cc - 媽媽的話  Zyboy忠宇這一次我告別故鄉踏上我的流浪無知和久違的理想像期待在前方動態歌詞.mp3 | Low | — | 1 | 0 | Long quoted query includes lyric text; one result returned, no clean candidate extracted. |
| 13 | tomp3.cc - 是你  夢然是你 是你 身後的青春都是你 繪成了我的山川流溪動態歌詞PinyinLyrics.mp3 | Low | — | 0 | 0 | Long quoted query returned no results. |
| 14 | tomp3.cc - 王靖雯  玫瑰少年哪朵玫瑰沒有荊棘 最好的 報復是 美麗 最美的 盛開是 反擊動態歌詞PinyinLyrics.mp3 | Low | — | 10 | 0 | Results contain useful-looking artist/title text, but unspaced dashes and lyric tails prevent extraction. |
| 15 | 【呪術廻戦】呪術廻戦 ×「廻廻奇譚」-MAD-AMV-【Jujutsu Kaisen】_256k.mp3 | Low | — | 0 | 0 | Existing tags describe an anime edit rather than a clear song identity; both queries returned no results. |

## Highest-priority fixes exposed by the run

1. Make by-artist parsing aware of structured artist/title boundaries and parentheses so MONTERO (Call Me By Your Name) is not split inside its title.
2. Clean known presentation/site suffixes before grouping; avoid treating lyric pages, loops and metadata boilerplate as independent song identities.
3. Handle Chinese quoted lyric tails and dash separators without surrounding spaces, preserving actual song/version text.
4. Generate shorter useful fallback queries for long downloader names and reject non-song encyclopedia/title candidates.
5. Keep genuine covers/remixes/live versions separate; improve noise handling rather than simply increasing confidence scores.
6. Distinguish lyrics network failure from a genuine provider Not Found result in diagnostics and UI.

These are findings for the next tuning pass, not changes silently applied to improve this baseline.

## Supporting search evidence for High proposals

### Kesha — TiK ToK

- [Kesha - TiK ToK (Lyrics) - YouTube](https://www.youtube.com/watch?v=OF04pKp-r9o)
- [Kesha – TiK ToK Lyrics - Genius](https://genius.com/Kesha-tik-tok-lyrics)

### Neoni x burnboy — Champion

- [Neoni x burnboy - Champion (Official Lyric Video) - YouTube](https://www.youtube.com/watch?v=WDhbbLIcCtw)
- [NEONI & Burnboy - Champion - YouTube](https://www.youtube.com/watch?v=e_Wf3YmThrI)
- [Neoni & burnboy – Champion Lyrics - Genius](https://genius.com/Neoni-and-burnboy-champion-lyrics)
- [Neoni & burnboy - Champion - YouTube](https://www.youtube.com/watch?v=EBtNXhbtsjA)

## Artifacts

- [Raw per-track results](results.csv): baseline statuses, queries and proposals.
- [Complete search evidence](evidence.json): result titles/snippets/URLs, candidate groups, scoring and existing identity fields. No full lyrics or audio are embedded.
- [Summary](summary.json): baseline counts and configuration.
- [Integrity verification](integrity.json): before/after SHA-256 hashes.
- [Initial lyrics diagnostics](lyrics-diagnostics.json) and [permitted retry](lyrics-diagnostics-retry.json): network restriction and actual provider outcomes.

Live search results are time-dependent. The isolated request cache is under .test-workspaces/phase9-live; existing application history was not opened for writes.
