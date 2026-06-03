"""Orchestration of the scrape: concurrency, resume, and per-video isolation.

Ties the modules together: lists entries, skips already-done videos, processes
each video (metadata, transcript, WAV) concurrently with a thread pool, and
merges results into the combined ``data.jsonl``. A failure in one video is
logged and recorded without aborting the run.
"""

import logging
from concurrent.futures import (Future, ThreadPoolExecutor, as_completed)
from pathlib import Path
from typing import (Any, Dict, List, Optional, Set)

from scraper.config import ScraperConfig
from scraper.extractor import (download_wav, fetch_metadata, list_entries,
                              playlist_title)
from scraper.models import (PlaylistEntry, TranscriptSnippet, VideoRecord,
                            error_record, metadata_fields)
from scraper.normalize import (normalize_title, slugify)
from scraper.store import (load_done_ids, write_merged)
from scraper.transcripts import fetch_transcript

logger: logging.Logger = logging.getLogger(__name__)


def _file_stem(index: int, video_id: str, width: int) -> str:
    """Build a ``{zero-padded index}_{video_id}`` filename stem."""
    return f"{index:0{width}d}_{video_id}"


def process_video(
    entry: PlaylistEntry,
    audio_dir: Path,
    run_dir: Path,
    width: int,
    auth_opts: Optional[Dict[str, Any]] = None,
) -> VideoRecord:
    """Process a single video into a complete record.

    Fetches metadata, retrieves the transcript, downloads and converts the
    audio to WAV, and assembles a :class:`VideoRecord`. Any exception is caught
    and converted into an ``status="error"`` record so one failure never aborts
    the overall run.

    Args:
        entry: The playlist entry to process.
        audio_dir: Directory where the WAV file is written.
        run_dir: The run root, used to compute the relative ``audio_path``.
        width: Zero-padding width for the filename index.
        auth_opts: Optional extra yt_dlp options (e.g. cookies) to merge in.

    Returns:
        A successful record, or an error record on failure.
    """
    try:
        info: Dict[str, Any] = fetch_metadata(entry["url"], auth_opts)

        title_raw: Optional[str] = info.get("title")
        snippets: Optional[List[TranscriptSnippet]]
        language: Optional[str]
        source: Optional[str]
        snippets, language, source = fetch_transcript(entry["video_id"], info)

        stem: str = _file_stem(entry["index"], entry["video_id"], width)
        wav_path: Path = download_wav(entry["url"], audio_dir, stem, auth_opts)
        audio_rel: str = str(wav_path.relative_to(run_dir))

        meta: Dict[str, Any] = metadata_fields(info)
        record: VideoRecord = {
            "index": entry["index"],
            "video_id": entry["video_id"],
            "url": entry["url"],
            "title": normalize_title(title_raw),
            "title_raw": title_raw,
            "channel": meta["channel"],
            "channel_id": meta["channel_id"],
            "upload_date": meta["upload_date"],
            "duration_sec": meta["duration_sec"],
            "view_count": meta["view_count"],
            "like_count": meta["like_count"],
            "language": language or meta["language"],
            "transcript": snippets,
            "transcript_source": source,
            "audio_path": audio_rel,
            "status": "ok",
            "error": None,
        }
        logger.info("Processed [%d] %s", entry["index"], entry["video_id"])
        return record
    except Exception as exc:  # noqa: BLE001 - per-video isolation: log & continue
        logger.error("Failed [%d] %s: %s", entry["index"], entry["video_id"], exc)
        return error_record(entry, str(exc))


def run(config: ScraperConfig) -> List[VideoRecord]:
    """Execute a full scrape for the configured URL.

    Lists entries, derives the run slug, skips already-processed videos (unless
    ``config.force``), processes the rest concurrently with a thread pool, and
    merges the results into ``data.jsonl``.

    Args:
        config: The resolved runtime configuration.

    Returns:
        The records produced this run (excludes skipped videos).
    """
    auth_opts: Dict[str, Any] = config.auth_opts()

    logger.info("Listing entries for %s", config.url)
    entries: List[PlaylistEntry] = list_entries(config.url, auth_opts)
    logger.info("Found %d video(s)", len(entries))

    title: Optional[str] = playlist_title(config.url, auth_opts)
    if not title and entries:
        # Single video fallback: name the run from the video's own title.
        title = fetch_metadata(entries[0]["url"], auth_opts).get("title")
    slug: str = slugify(title, fallback=entries[0]["video_id"] if entries else "video")

    run_dir: Path
    data_path: Path
    audio_dir: Path
    run_dir, data_path, audio_dir = config.paths_for(slug)
    run_dir.mkdir(parents=True, exist_ok=True)

    done: Set[str] = set() if config.force else load_done_ids(data_path)
    pending: List[PlaylistEntry] = [e for e in entries if e["video_id"] not in done]
    skipped: int = len(entries) - len(pending)
    if skipped:
        logger.info("Skipping %d already-processed video(s)", skipped)

    width: int = max(3, len(str(len(entries))))
    results: List[VideoRecord] = []

    if pending:
        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            futures: Dict[Future, PlaylistEntry] = {
                executor.submit(process_video, entry, audio_dir, run_dir, width, auth_opts): entry
                for entry in pending
            }
            for future in as_completed(futures):
                results.append(future.result())

    write_merged(data_path, results)

    ok: int = sum(1 for r in results if r["status"] == "ok")
    errors: int = len(results) - ok
    logger.info(
        "Done. processed=%d ok=%d error=%d skipped=%d output=%s",
        len(results), ok, errors, skipped, data_path,
    )
    return results
