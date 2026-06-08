"""Reading and writing the combined ``metadata.jsonl`` output.

Supports resume (collecting already-completed video ids) and an atomic,
deterministic merge-write that combines existing and new records, ordered by
playlist index, via a temp file plus replace.
"""

import json
import logging
from pathlib import Path
from typing import (Dict, Iterable, List, Set)

from scraper.models import VideoRecord

logger: logging.Logger = logging.getLogger(__name__)


def load_done_ids(data_path: Path) -> Set[str]:
    """Collect video ids already successfully processed in an output file.

    Args:
        data_path: Path to an existing ``metadata.jsonl`` (may not exist).

    Returns:
        The set of ``video_id`` values whose record has ``status == "ok"`` and a
        non-empty ``transcript``. Records with a null/empty transcript are left
        out so a re-run re-transcribes them (e.g. after a transient IP block).
        Returns an empty set if the file is missing.
    """
    done: Set[str] = set()
    if not data_path.exists():
        return done
    with data_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record: Dict = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSONL line in %s", data_path)
                continue
            if (
                record.get("status") == "ok"
                and record.get("video_id")
                and record.get("transcript")
            ):
                done.add(record["video_id"])
    return done


def load_existing_records(data_path: Path) -> List[VideoRecord]:
    """Load all records from an existing ``metadata.jsonl`` file.

    Args:
        data_path: Path to an existing ``metadata.jsonl`` (may not exist).

    Returns:
        The parsed records; malformed lines are skipped. Empty if missing.
    """
    records: List[VideoRecord] = []
    if not data_path.exists():
        return records
    with data_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def write_merged(data_path: Path, records: Iterable[VideoRecord]) -> None:
    """Merge new records into ``metadata.jsonl`` and rewrite it atomically.

    Existing records are loaded and combined with ``records`` keyed by
    ``video_id`` (new records win), sorted by playlist ``index``, and written
    to a temp file that atomically replaces the target. This avoids interleaved
    writes from concurrent workers and yields deterministic ordering.

    Args:
        data_path: Destination ``metadata.jsonl`` path.
        records: Newly produced records to merge in.
    """
    # Merge by video_id (new records win), then sort by playlist index for
    # deterministic ordering. Written atomically via a temp file + replace.
    by_id: Dict[str, VideoRecord] = {}
    for record in load_existing_records(data_path):
        vid: str = record.get("video_id", "")
        if vid:
            by_id[vid] = record
    for record in records:
        by_id[record["video_id"]] = record

    ordered: List[VideoRecord] = sorted(by_id.values(), key=lambda r: r.get("index", 0))

    data_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path = data_path.with_suffix(data_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for record in ordered:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    tmp_path.replace(data_path)
    logger.info("Wrote %d records to %s", len(ordered), data_path)
