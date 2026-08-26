"""Temporary audio segment extraction for fallback recognition."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterator
import uuid

from mutagen import File as MutagenFile


class AudioSegmentError(RuntimeError):
    """Raised when fallback recognition clips cannot be prepared."""


@dataclass(frozen=True)
class AudioSegment:
    index: int
    start_seconds: int
    path: Path


def get_audio_duration_seconds(path: str | Path) -> int | None:
    audio = MutagenFile(Path(path))
    if audio is None or not getattr(audio, "info", None):
        return None
    length = getattr(audio.info, "length", None)
    if length is None:
        return None
    seconds = int(round(float(length)))
    return seconds if seconds > 0 else None


def segment_start_times(duration_seconds: int, *, max_segments: int = 3, clip_seconds: int = 15) -> list[int]:
    """Generate segment starts around 25%, 50%, and 75% without leaving bounds."""

    if duration_seconds <= 0:
        return []
    max_segments = max(1, max_segments)
    clip_seconds = max(1, clip_seconds)
    if duration_seconds <= clip_seconds:
        return [0]

    positions = (0.25, 0.5, 0.75)
    latest_start = max(0, duration_seconds - clip_seconds)
    starts: list[int] = []
    for position in positions[:max_segments]:
        center = round(duration_seconds * position)
        start = max(0, min(latest_start, center - clip_seconds // 2))
        if start not in starts:
            starts.append(start)
    return starts or [0]


def build_ffmpeg_extract_command(
    *,
    ffmpeg_executable: str,
    source_path: str | Path,
    output_path: str | Path,
    start_seconds: int,
    clip_seconds: int = 15,
) -> list[str]:
    return [
        ffmpeg_executable,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(max(0, start_seconds)),
        "-t",
        str(max(1, clip_seconds)),
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "44100",
        "-b:a",
        "128k",
        str(output_path),
    ]


def resolve_ffmpeg_executable(ffmpeg_executable: str | Path = "ffmpeg") -> str:
    """Resolve a configured ffmpeg value to the executable that should be run."""

    configured = str(ffmpeg_executable).strip() or "ffmpeg"
    path = Path(configured)
    executable_name = "ffmpeg.exe" if _is_windows() else "ffmpeg"

    if path.exists() and path.is_dir():
        return str(path / executable_name)
    if path.exists() and path.is_file():
        return str(path)
    if path.name.lower() != executable_name and (path / executable_name).exists():
        return str(path / executable_name)

    found = shutil.which(configured)
    return found or configured


def check_ffmpeg_available(ffmpeg_executable: str | Path = "ffmpeg") -> tuple[bool, str, str]:
    """Return safe ffmpeg availability diagnostics without modifying files."""

    resolved = resolve_ffmpeg_executable(ffmpeg_executable)
    try:
        completed = subprocess.run(
            [resolved, "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False, resolved, "FFMPEG_INVALID_PATH"
    return completed.returncode == 0, resolved, "READY" if completed.returncode == 0 else "FFMPEG_EXECUTION_FAILED"


@contextmanager
def temporary_audio_segments(
    source_path: str | Path,
    *,
    duration_seconds: int | None = None,
    ffmpeg_executable: str = "ffmpeg",
    max_segments: int = 3,
    clip_seconds: int = 15,
) -> Iterator[list[AudioSegment]]:
    """Extract temporary audio clips and delete them afterward."""

    ffmpeg_executable = resolve_ffmpeg_executable(ffmpeg_executable)
    available, _, status = check_ffmpeg_available(ffmpeg_executable)
    if not available:
        raise AudioSegmentError(status)

    source = Path(source_path)
    duration = duration_seconds or get_audio_duration_seconds(source)
    if duration is None:
        raise AudioSegmentError("Audio duration is unavailable for fallback recognition.")

    temp_dir = Path(tempfile.mkdtemp(prefix="music-cleaner-segments-"))
    segments: list[AudioSegment] = []
    try:
        for index, start in enumerate(segment_start_times(duration, max_segments=max_segments, clip_seconds=clip_seconds), start=1):
            output = temp_dir / f"{uuid.uuid4().hex}.mp3"
            command = build_ffmpeg_extract_command(
                ffmpeg_executable=ffmpeg_executable,
                source_path=source,
                output_path=output,
                start_seconds=start,
                clip_seconds=clip_seconds,
            )
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if completed.returncode != 0 or not output.exists():
                raise AudioSegmentError("ffmpeg failed to extract a recognition segment.")
            segments.append(AudioSegment(index=index, start_seconds=start, path=output))
        yield segments
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _is_windows() -> bool:
    return os.name == "nt"
