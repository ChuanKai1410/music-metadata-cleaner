# UI action audit — before control removal

Scope: UI only. Reviewed all three UI modules and their signal/slot connections.

| Controls | Handler and actual behavior | Decision |
| --- | --- | --- |
| Scan / Preview Changes | `scan_files()` only delegates to `preview_changes()`; both start the same all-track search and preview worker | Keep one **Scan & Preview** entry wired to `preview_changes`; remove duplicate bottom button and delegating slot |
| Apply Selected / Apply All High Confidence | Selected rows versus eligible high-confidence rows, both with explicit confirmation | Retain both |
| Remove / Clear / Remove All High Confidence | Selected list rows / whole list / only successfully applied high-confidence rows | Retain all; rename last to **Remove Applied Rows**, with scope tooltip. None deletes files, so no destructive styling |
| History / Undo Last Batch | Inspect recorded operations / confirmed restoration | Retain both; move recovery beside History |
| Search / Use Candidate / Edit Artist / Title / Lyrics | Search user keywords / explicitly select search candidate / edit local preview and lyrics | Retain all in selected-track context |
| Settings / Test Connection / Clear search cache | Preferences / endpoint diagnostic / cached request deletion | Retain in their existing contexts |
| Save Preview / Apply Selected | Local proposed edit / confirmed on-disk modification | Retain; these are not duplicates |
| Preserve lyrics / Overwrite lyrics | Distinct safety preferences with existing dependency | Retain unchanged |

Other findings: two inline styles (main title and section headings); two nested decorative group boxes; equal-width table columns; crowded bottom action row; always-visible idle progress; long unwrapped dialog help labels; unbounded history message box; evidence dialog without a visible Close action. Logs already start hidden. Manual Search is embedded in the detail panel, not a separate dialog. Candidate selection uses QInputDialog. Confirmations/errors use QMessageBox. No other genuinely duplicate controls found.
