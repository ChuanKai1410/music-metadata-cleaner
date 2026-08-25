from __future__ import annotations

from music_metadata_cleaner.env_loader import load_dotenv


def test_load_dotenv_sets_values_without_overriding_existing_environment(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "ACOUSTID_API_KEY=from-file",
                "FPCALC_PATH=\"C:\\Tools\\chromaprint\\fpcalc.exe\"",
                "EXISTING=from-file",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING", "already-set")

    load_dotenv(env_path)

    assert __import__("os").environ["ACOUSTID_API_KEY"] == "from-file"
    assert __import__("os").environ["FPCALC_PATH"] == "C:\\Tools\\chromaprint\\fpcalc.exe"
    assert __import__("os").environ["EXISTING"] == "already-set"
