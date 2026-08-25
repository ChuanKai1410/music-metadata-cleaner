"""Confidence helper functions."""

from __future__ import annotations


def confidence_label(score: int) -> str:
    if score >= 90:
        return "high"
    if score >= 70:
        return "review"
    return "low"
