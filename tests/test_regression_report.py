from __future__ import annotations

from music_metadata_cleaner.app.regression_report import summarize_regression_csv


def test_summarize_regression_csv_counts_manual_sample_outcomes(tmp_path):
    report = tmp_path / "report.csv"
    report.write_text(
        "\n".join(
            [
                "filename,before_high_confidence,after_high_confidence,after_correct,youtube_used,after_confidence,acoustid_resolved,audd_fallback_resolved,youtube_verified,unresolved",
                "a.mp3,true,true,true,false,98,true,false,false,false",
                "b.mp3,true,true,true,true,91,true,false,true,false",
                "c.mp3,false,true,true,true,82,false,true,true,false",
                "d.mp3,false,true,false,true,95,false,true,true,false",
                "e.mp3,false,false,false,false,0,false,false,false,true",
            ]
        ),
        encoding="utf-8",
    )

    summary = summarize_regression_csv(report)

    assert summary.total == 5
    assert summary.previous_high_confidence == 2
    assert summary.previous_failed_or_uncertain == 3
    assert summary.existing_high_confidence_still_correct == 2
    assert summary.previously_failed_recovered == 1
    assert summary.incorrect_youtube_matches == 1
    assert summary.correct_high_confidence == 2
    assert summary.correct_medium_confidence == 1
    assert summary.unresolved == 1
    assert summary.incorrect_identifications == 1
    assert summary.acoustid_resolved == 2
    assert summary.audd_fallback_resolved == 2
    assert summary.youtube_verified == 3
