"""Typed data structures and helpers for scraper output records.

Defines the :class:`VideoRecord` schema written to ``metadata.jsonl`` (one object
per line), along with the intermediate :class:`PlaylistEntry` and
:class:`TranscriptSnippet` shapes and small helpers for building records.
"""

from typing import (Any, Dict, List, Optional, TypedDict)


class TranscriptSnippet(TypedDict):
    """A single transcript line with timing, in seconds."""

    text: str
    start: float
    duration: float


class PlaylistEntry(TypedDict):
    """An enumerated playlist item awaiting processing."""

    index: int
    video_id: str
    url: str


class VideoRecord(TypedDict):
    """One fully processed video, serialized as a line in ``metadata.jsonl``."""

    index: int
    video_id: str
    url: str
    title: Optional[str]
    title_raw: Optional[str]
    channel: Optional[str]
    channel_id: Optional[str]
    upload_date: Optional[str]
    duration_sec: Optional[int]
    view_count: Optional[int]
    like_count: Optional[int]
    language: Optional[str]
    transcript: Optional[List[TranscriptSnippet]]
    transcript_source: Optional[str]
    audio_path: Optional[str]
    status: str
    error: Optional[str]


def error_record(entry: PlaylistEntry, message: str) -> VideoRecord:
    """Build a failure record for a video that could not be processed.

    All metadata fields are set to ``None`` and ``status`` is ``"error"`` so
    failed videos still appear in ``metadata.jsonl`` without aborting the run.

    Args:
        entry: The playlist entry that failed.
        message: A human-readable error message.

    Returns:
        A :class:`VideoRecord` with ``status="error"``.
    """
    record: VideoRecord = {
        "index": entry["index"],
        "video_id": entry["video_id"],
        "url": entry["url"],
        "title": None,
        "title_raw": None,
        "channel": None,
        "channel_id": None,
        "upload_date": None,
        "duration_sec": None,
        "view_count": None,
        "like_count": None,
        "language": None,
        "transcript": None,
        "transcript_source": None,
        "audio_path": None,
        "status": "error",
        "error": message,
    }
    return record


def metadata_fields(info: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalize the metadata fields used in a record.

    Pulls channel, dates, duration, and counts out of a raw yt_dlp info dict,
    reformatting ``upload_date`` from ``YYYYMMDD`` to ``YYYY-MM-DD`` and
    falling back to alternative keys (e.g. ``uploader``) where appropriate.

    Args:
        info: The raw info dictionary returned by yt_dlp.

    Returns:
        A dict with keys ``channel``, ``channel_id``, ``upload_date``,
        ``duration_sec``, ``view_count``, ``like_count``, and ``language``.
    """
    upload_date_raw: Optional[str] = info.get("upload_date")
    upload_date: Optional[str] = None
    if upload_date_raw and len(upload_date_raw) == 8:
        upload_date = f"{upload_date_raw[0:4]}-{upload_date_raw[4:6]}-{upload_date_raw[6:8]}"

    fields: Dict[str, Any] = {
        "channel": info.get("channel") or info.get("uploader"),
        "channel_id": info.get("channel_id") or info.get("uploader_id"),
        "upload_date": upload_date,
        "duration_sec": info.get("duration"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "language": info.get("language"),
    }
    return fields
