"""Thin wrappers around yt_dlp for listing, metadata, and audio download.

Provides the project's interface to ``yt_dlp.YoutubeDL``: enumerating playlist
(or single-video) entries, fetching per-video metadata, and downloading
best-quality audio converted to WAV via ffmpeg.
"""

import logging
from pathlib import Path
from typing import (Any, Dict, List, Optional, cast)

from yt_dlp import YoutubeDL

from scraper.models import PlaylistEntry

logger: logging.Logger = logging.getLogger(__name__)

_WATCH_URL: str = "https://www.youtube.com/watch?v={video_id}"
_COMMON_OPTS: Dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "ignoreerrors": True,
    "retries": 5,
    "fragment_retries": 5,
}


def _merge_opts(base: Dict[str, Any], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge optional extra yt_dlp options (e.g. cookies) over a base dict."""
    merged: Dict[str, Any] = dict(base)
    if extra:
        merged.update(extra)
    return merged


def _extract(opts: Dict[str, Any], url: str) -> Optional[Dict[str, Any]]:
    """Run ``YoutubeDL.extract_info`` without downloading and return the dict."""
    with YoutubeDL(cast(Any, opts)) as ydl:
        info: Any = ydl.extract_info(url, download=False)
    return cast(Optional[Dict[str, Any]], info)


def list_entries(url: str, auth_opts: Optional[Dict[str, Any]] = None) -> List[PlaylistEntry]:
    """Enumerate the videos for a playlist or single-video URL.

    Uses flat extraction so playlists are listed cheaply. Single videos yield
    one entry at index 1; playlist entries are numbered by their position
    among playable items.

    Args:
        url: A YouTube playlist or video URL.
        auth_opts: Optional extra yt_dlp options (e.g. cookies) to merge in.

    Returns:
        Ordered playlist entries, each with ``index``, ``video_id``, ``url``.

    Raises:
        RuntimeError: If no information or no playable videos can be extracted.
    """
    opts: Dict[str, Any] = _merge_opts(
        {**_COMMON_OPTS, "extract_flat": "in_playlist"}, auth_opts
    )
    info: Optional[Dict[str, Any]] = _extract(opts, url)

    if info is None:
        raise RuntimeError(f"Could not extract any information from URL: {url}")

    raw_entries: Optional[List[Optional[Dict[str, Any]]]] = info.get("entries")
    entries: List[PlaylistEntry] = []

    if raw_entries is None:
        # Single video.
        video_id: Optional[str] = info.get("id")
        if not video_id:
            raise RuntimeError(f"No video id found for URL: {url}")
        entries.append(
            {"index": 1, "video_id": video_id, "url": _WATCH_URL.format(video_id=video_id)}
        )
        return entries

    position: int = 0
    for raw in raw_entries:
        if raw is None:
            continue
        video_id = raw.get("id")
        if not video_id:
            continue
        position += 1
        entries.append(
            {
                "index": position,
                "video_id": video_id,
                "url": raw.get("url") or _WATCH_URL.format(video_id=video_id),
            }
        )

    if not entries:
        raise RuntimeError(f"No playable videos found for URL: {url}")
    return entries


def playlist_title(url: str, auth_opts: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Return the playlist (or video) title for a URL, if available.

    Extracts only the first item to keep the lookup cheap.

    Args:
        url: A YouTube playlist or video URL.
        auth_opts: Optional extra yt_dlp options (e.g. cookies) to merge in.

    Returns:
        The title string, or ``None`` if it cannot be determined.
    """
    opts: Dict[str, Any] = _merge_opts(
        {**_COMMON_OPTS, "extract_flat": "in_playlist", "playlist_items": "1"}, auth_opts
    )
    info: Optional[Dict[str, Any]] = _extract(opts, url)
    if info is None:
        return None
    return info.get("title")


def fetch_metadata(video_url: str, auth_opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetch the full metadata info dict for a single video (no download).

    Args:
        video_url: The YouTube video URL.
        auth_opts: Optional extra yt_dlp options (e.g. cookies) to merge in.

    Returns:
        The raw info dictionary returned by yt_dlp.

    Raises:
        RuntimeError: If metadata cannot be extracted.
    """
    info: Optional[Dict[str, Any]] = _extract(_merge_opts(_COMMON_OPTS, auth_opts), video_url)
    if info is None:
        raise RuntimeError(f"Failed to fetch metadata for {video_url}")
    return info


def download_wav(
    video_url: str,
    audio_dir: Path,
    file_stem: str,
    auth_opts: Optional[Dict[str, Any]] = None,
) -> Path:
    """Download best-quality audio and convert it to WAV.

    Selects the best available audio (falling back to a muxed stream when no
    audio-only format is exposed) and runs the ffmpeg post-processor to produce
    a ``.wav`` file named ``<file_stem>.wav`` inside ``audio_dir``.

    Args:
        video_url: The YouTube video URL to download.
        audio_dir: Directory where the WAV file is written (created if needed).
        file_stem: Filename stem, e.g. ``001_dQw4w9WgXcQ``.
        auth_opts: Optional extra yt_dlp options (e.g. cookies) to merge in.

    Returns:
        Path to the produced ``.wav`` file.

    Raises:
        RuntimeError: If the expected WAV file was not produced.
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    outtmpl: str = str(audio_dir / f"{file_stem}.%(ext)s")
    opts: Dict[str, Any] = _merge_opts(
        {
            **_COMMON_OPTS,
            "ignoreerrors": False,  # raise so the pipeline records the error per video
            # Prefer audio-only; fall back to any audio-bearing/muxed stream so
            # extraction still works when no audio-only format is exposed.
            "format": "bestaudio/bestaudio*/best",
            "outtmpl": outtmpl,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "wav"},
            ],
        },
        auth_opts,
    )
    with YoutubeDL(cast(Any, opts)) as ydl:
        ydl.download([video_url])

    expected: Path = audio_dir / f"{file_stem}.wav"
    if not expected.exists():
        raise RuntimeError(f"Expected WAV not produced: {expected}")
    return expected
