"""Transcript retrieval with a two-tier strategy.

Fetches the original-language transcript via ``youtube_transcript_api`` first;
when no captions are available there, falls back to yt_dlp's auto-generated
subtitles (parsed from the ``json3`` format). No translation is performed.
"""

import json
import logging
import urllib.request
from typing import (Any, Dict, List, Optional, Tuple)

from youtube_transcript_api import (NoTranscriptFound, TranscriptsDisabled,
                                    YouTubeTranscriptApi)
from youtube_transcript_api._errors import CouldNotRetrieveTranscript

from scraper.models import TranscriptSnippet

logger: logging.Logger = logging.getLogger(__name__)

# (transcript snippets | None, language code | None, source | None)
TranscriptResult = Tuple[Optional[List[TranscriptSnippet]], Optional[str], Optional[str]]


def _from_api(video_id: str) -> TranscriptResult:
    """Fetch the original-language transcript via ``youtube_transcript_api``.

    Prefers a manually created transcript over an auto-generated one; never
    translates.

    Args:
        video_id: The 11-character YouTube video id.

    Returns:
        A ``(snippets, language_code, "youtube_transcript_api")`` tuple, or
        ``(None, None, None)`` if no transcript is available.
    """
    api: YouTubeTranscriptApi = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)

    # "Original only": prefer a manually created transcript, else the first
    # (typically auto-generated) one. No translation is applied.
    chosen = None
    for transcript in transcript_list:
        if not transcript.is_generated:
            chosen = transcript
            break
    if chosen is None:
        for transcript in transcript_list:
            chosen = transcript
            break
    if chosen is None:
        return (None, None, None)

    fetched = chosen.fetch()
    raw: List[Dict[str, Any]] = fetched.to_raw_data()
    snippets: List[TranscriptSnippet] = [
        {
            "text": item.get("text", ""),
            "start": float(item.get("start", 0.0)),
            "duration": float(item.get("duration", 0.0)),
        }
        for item in raw
    ]
    return (snippets, chosen.language_code, "youtube_transcript_api")


def _parse_json3(data: Dict[str, Any]) -> List[TranscriptSnippet]:
    """Parse YouTube ``json3`` caption data into transcript snippets.

    Args:
        data: A decoded ``json3`` payload containing an ``events`` list.

    Returns:
        Transcript snippets with timing converted from milliseconds to
        seconds; events without text are skipped.
    """
    snippets: List[TranscriptSnippet] = []
    for event in data.get("events", []):
        segs: Optional[List[Dict[str, Any]]] = event.get("segs")
        if not segs:
            continue
        text: str = "".join(seg.get("utf8", "") for seg in segs).strip()
        if not text:
            continue
        start_ms: int = int(event.get("tStartMs", 0))
        dur_ms: int = int(event.get("dDurationMs", 0))
        snippets.append(
            {
                "text": text,
                "start": start_ms / 1000.0,
                "duration": dur_ms / 1000.0,
            }
        )
    return snippets


def _from_yt_dlp_auto(info: Dict[str, Any]) -> TranscriptResult:
    """Fetch auto-generated captions from a yt_dlp info dict.

    Looks in ``info["automatic_captions"]`` for the video's declared language
    (or the first available), downloads its ``json3`` track, and parses it.

    Args:
        info: The raw info dictionary returned by yt_dlp.

    Returns:
        A ``(snippets, language_code, "yt_dlp_auto")`` tuple, or
        ``(None, None, None)`` if no usable auto captions are found.
    """
    # yt_dlp puts auto captions in `automatic_captions`: {lang: [formats...]}.
    auto: Dict[str, Any] = info.get("automatic_captions") or {}
    if not auto:
        return (None, None, None)

    # Prefer the video's declared language; otherwise take the first available.
    preferred: Optional[str] = info.get("language")
    lang: Optional[str] = preferred if preferred in auto else next(iter(auto), None)
    if lang is None:
        return (None, None, None)

    formats: List[Dict[str, Any]] = auto[lang]
    json3: Optional[Dict[str, Any]] = next(
        (fmt for fmt in formats if fmt.get("ext") == "json3"), None
    )
    if json3 is None or not json3.get("url"):
        return (None, None, None)

    try:
        with urllib.request.urlopen(json3["url"], timeout=30) as resp:
            payload: Dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - network/parse failures are non-fatal
        logger.warning("Failed to fetch yt_dlp auto subtitles for %s: %s", lang, exc)
        return (None, None, None)

    snippets: List[TranscriptSnippet] = _parse_json3(payload)
    if not snippets:
        return (None, None, None)
    return (snippets, lang, "yt_dlp_auto")


def fetch_transcript(video_id: str, info: Dict[str, Any]) -> TranscriptResult:
    """Fetch a transcript, preferring captions over auto-generated subtitles.

    Tries ``youtube_transcript_api`` first; on missing/disabled captions or a
    retrieval error, falls back to yt_dlp auto subtitles. All failures are
    logged and result in an empty result rather than an exception.

    Args:
        video_id: The 11-character YouTube video id.
        info: The raw yt_dlp info dict, used for the fallback path.

    Returns:
        A ``(snippets, language_code, source)`` tuple where ``source`` is
        ``"youtube_transcript_api"``, ``"yt_dlp_auto"``, or ``None``. When no
        transcript exists, returns ``(None, None, None)``.
    """
    try:
        result: TranscriptResult = _from_api(video_id)
        if result[0]:
            return result
    except (NoTranscriptFound, TranscriptsDisabled):
        logger.info("No youtube_transcript_api captions for %s", video_id)
    except CouldNotRetrieveTranscript as exc:
        logger.warning("youtube_transcript_api error for %s: %s", video_id, exc)

    logger.info("Falling back to yt_dlp auto subtitles for %s", video_id)
    return _from_yt_dlp_auto(info)
