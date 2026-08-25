"""Desktop entry point."""

from __future__ import annotations

from music_metadata_cleaner.app.service_factory import create_default_workflow_service
from music_metadata_cleaner.ui.main_window import run_desktop_app


def main() -> int:
    return run_desktop_app(create_default_workflow_service())


if __name__ == "__main__":
    raise SystemExit(main())
