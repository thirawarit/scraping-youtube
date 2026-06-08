"""Runtime configuration, logging setup, and environment checks.

This module centralises cross-cutting concerns: the :class:`ScraperConfig`
dataclass that carries CLI options through the pipeline, Bangkok-timezone
logging configuration, and the startup ``ffmpeg`` availability check.
"""

import logging
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import (Any, Dict, Optional, Tuple)
from zoneinfo import ZoneInfo

BANGKOK_TZ: ZoneInfo = ZoneInfo("Asia/Bangkok")
LOG_DATEFMT: str = "%Y-%m-%d %H:%M:%S"
LOG_FORMAT: str = "%(asctime)s | %(levelname)s | %(name)s:%(lineno)d | %(message)s"

logger: logging.Logger = logging.getLogger(__name__)


def _bangkok_time(timestamp: Optional[float] = None) -> time.struct_time:
    """Return a ``struct_time`` for ``timestamp`` in the Bangkok timezone."""
    ts: float = time.time() if timestamp is None else timestamp
    return datetime.fromtimestamp(ts, tz=BANGKOK_TZ).timetuple()


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with a Bangkok-timezone formatter.

    Installs a single stream handler whose formatter includes asctime,
    levelname, name, lineno, and message, with timestamps rendered in the
    ``Asia/Bangkok`` timezone. Any pre-existing root handlers are removed so
    repeated calls remain idempotent.

    Args:
        level: The logging level for the root logger (default ``INFO``).
    """
    formatter: logging.Formatter = logging.Formatter(
        fmt=LOG_FORMAT,
        datefmt=LOG_DATEFMT,
    )
    formatter.converter = _bangkok_time

    handler: logging.StreamHandler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root: logging.Logger = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def check_ffmpeg() -> str:
    """Verify that ``ffmpeg`` is available on ``PATH``.

    Returns:
        The absolute path to the ``ffmpeg`` executable.

    Raises:
        RuntimeError: If ``ffmpeg`` is not found on ``PATH``.
    """
    ffmpeg_path: Optional[str] = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise RuntimeError(
            "ffmpeg was not found on PATH. It is required to convert audio to WAV. "
            "Install it (e.g. `brew install ffmpeg`) and try again."
        )
    logger.info("Found ffmpeg at %s", ffmpeg_path)
    return ffmpeg_path


@dataclass
class ScraperConfig:
    """Resolved runtime options for a single scraper invocation.

    Attributes:
        url: The YouTube playlist or video URL to scrape.
        output_dir: Base output directory; each run writes to
            ``output_dir/<slug>/``.
        workers: Number of concurrent worker threads.
        force: When ``True``, re-process videos already present in the output.
        cookies: Optional path to a Netscape-format ``cookies.txt`` used to get
            past region/age/bot walls.
        cookies_from_browser: Optional browser name (e.g. ``chrome``,
            ``safari``) to load cookies from directly.
    """

    url: str
    output_dir: Path
    workers: int
    force: bool
    cookies: Optional[Path] = None
    cookies_from_browser: Optional[str] = None

    def auth_opts(self) -> Dict[str, Any]:
        """Return yt_dlp options carrying cookie auth, empty when unset.

        Returns:
            A dict with ``cookiefile`` and/or ``cookiesfrombrowser`` set, or an
            empty dict when no cookie source was configured.
        """
        opts: Dict[str, Any] = {}
        if self.cookies is not None:
            opts["cookiefile"] = str(self.cookies)
        if self.cookies_from_browser is not None:
            opts["cookiesfrombrowser"] = (self.cookies_from_browser,)
        return opts

    def run_dir(self, slug: str) -> Path:
        """Return the per-run directory ``output_dir/<slug>``."""
        return self.output_dir / slug

    def data_path(self, slug: str) -> Path:
        """Return the path to the run's combined ``metadata.jsonl`` file."""
        return self.run_dir(slug) / "metadata.jsonl"

    def audio_dir(self, slug: str) -> Path:
        """Return the run's ``audio/`` directory for WAV files."""
        return self.run_dir(slug) / "audio"

    def paths_for(self, slug: str) -> Tuple[Path, Path, Path]:
        """Return the run directory, ``metadata.jsonl`` path, and audio directory.

        Args:
            slug: The normalized playlist/video slug naming the run.

        Returns:
            A ``(run_dir, data_path, audio_dir)`` tuple.
        """
        return self.run_dir(slug), self.data_path(slug), self.audio_dir(slug)
