# UI polish report

## Scope

Presentation and UI wiring only. SearXNG, deterministic resolution, LRCLIB, ID3, rename, backup, history storage, and undo implementations were not modified. No new dependencies or features. Original music files were not used for write tests.

## Shared visual system

- `src/music_metadata_cleaner/ui/styles/app.qss`: organized base, typography, buttons, inputs, tables, tabs, scrollbars, progress/status, and dialog rules.
- `ui/theme.py`: centralized neutral dark palette, 8-unit control spacing and 16-unit outer margins, application-wide QSS loader, semantic roles, and consistent dialog setup. System font retained; only the application heading has an explicit larger type size. Qt Fusion provides a consistent platform baseline.
- Small `styles/up.svg` and `styles/down.svg` arrows restore clearly visible spin/dropdown affordances without an icon library.
- Restrained blue-gray accent, off-white text, muted secondary labels, subtle green/amber/red status text. No saturated row backgrounds, gradients, shadows, or decorative icons.
- Both inline widget styles were removed. Only the application-level theme loader calls `setStyleSheet`. Runtime changed-value roles and table text colors are confined to the UI.

## Main layout

- Compact import/list toolbar; one **Scan & Preview** entry. Recovery remains discoverable beside History and Settings.
- Apply Selected is the emphasized action; Apply All High Confidence remains distinct. Cancel and the single progress bar appear during processing. Logs remain hidden until Show Log is chosen.
- Six-column table retains selection behavior, gives File the largest share of flexible text space, keeps confidence/lyrics/status content-sized, and removes the grid. Rows use font-relative comfortable heights; elided values have tooltips.
- Two nested decorative group boxes were replaced with section labels and spacing. Current/Proposed values retain all fields, with subtly emphasized changed proposals.
- A resizable splitter and scrollable detail area preserve access to long filenames/evidence. Manual Search has one input and one adjacent Search action; Return submits that search.

## Action audit and removal

See [UI_ACTION_AUDIT.md](UI_ACTION_AUDIT.md), recorded before removal.

**One duplicate removed:** Preview Changes and Scan performed exactly the same all-track operation (`scan_files` only delegated to `preview_changes`). The retained **Scan & Preview** button connects directly to `preview_changes`. The unused wrapper and duplicate button connections/state updates were removed.

Retained distinct actions:

| Action | Purpose |
| --- | --- |
| Add Files / Add Folder | Import explicit files / discover a folder |
| Remove / Clear | Remove selected rows / clear the list; neither deletes files |
| Scan & Preview | Search and create proposals without writing MP3s |
| Apply Selected / Apply All High Confidence | Confirmed application to selected rows / eligible high-confidence rows |
| Remove Applied Rows | Clear only rows successfully applied through the high-confidence batch action; scope explained by tooltip |
| Manual Search / Use Candidate / Edit Artist / Title / Lyrics | Search keywords / choose an evidence candidate / edit a local preview |
| View Search Evidence / Show Log | Inspect selected-track evidence / reveal operational messages |
| History / Undo Last Batch | Inspect recorded operations / confirm restoration |
| Settings / Test Connection / Clear search cache | Configure preferences / test endpoint / clear cached requests |
| Save Preview / Save Settings | Save a local proposal / persist configuration |

No meaningful settings were combined or removed. No destructive style was assigned to list-only removal actions.

## Settings and other dialogs

- Existing five tabs retained; aligned forms use shared margins/spacing, wrap long help text, and use consistent inputs and a primary Save button. Files & Safety now displays its literal ampersand correctly.
- Manual editor uses bounded editable dropdowns, visible arrows, wrapped instructions, an error-text role, and a primary Save Preview button. Lyrics replacement safeguards remain unchanged.
- Evidence and history share `TextDialog`: resizable, scrollable, read-only text with a visible Close button and Escape dismissal. Evidence contents/score breakdown are preserved; history keeps the existing 25-operation limit.
- Candidate selection and confirmation/information dialogs inherit the same application palette/QSS. Native file/folder pickers retain the operating system's styling.

## Files created/modified

Created: `ui/theme.py`, `ui/text_dialog.py`, `ui/styles/app.qss`, `ui/styles/up.svg`, `ui/styles/down.svg`, this report, and `docs/UI_ACTION_AUDIT.md`.

Modified: `ui/main_window.py`, `ui/settings_dialog.py`, `ui/manual_edit_dialog.py`, `tests/test_gui_smoke.py`, `packaging/MusicMetadataCleaner.spec` (includes style assets), and `README.md` (current action name). UI paths are relative to `src/music_metadata_cleaner`.

## Verification

- Complete suite: **203 passed**, with GUI tests enabled and all external search/lyrics requests mocked.
- GUI subset: **15 passed** at each of 100%, 125%, and 150% Qt scaling.
- Coverage includes stylesheet loading, settings persistence, table/detail updates, resizing, import files/folder, consolidated scan/preview, manual search, candidate choice, manual editing, Apply Selected, Apply All High Confidence, rename/undo with temporary files, history/evidence access, hidden logs/progress, and duplicate removal. A byte comparison confirms scan/preview does not modify the temporary input files.
- Visually inspected offscreen Qt captures of main windows at 1280×720 and 1920×1080 logical sizes, all settings tabs, manual editor, candidate selection, evidence, history, apply/undo confirmations, and a representative error message. Scaling captures at 125% and 150% showed no obvious clipping in the reviewed layouts.
- `git diff --check` passed. Packaging configuration includes the QSS/SVG directory.

## Limits

Visual review used rendered Qt widgets, not a live native desktop session. Native file pickers, window chrome, and standard message-box icons remain platform-controlled. Long detail content intentionally scrolls and long table text intentionally elides. A packaged executable was not rebuilt; Linux runtime visuals were not tested here. No other visual inconsistency was found in the inspected captures.

Pre-existing deleted SQLite WAL/SHM sidecars were left untouched; this UI pass does not reset history.
