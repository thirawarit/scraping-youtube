"""YouTube scraping package.

Extracts metadata and original-language transcripts and downloads best-quality
WAV audio for a YouTube playlist or video, writing a combined JSONL output.
"""

from scraper.config import (ScraperConfig, check_ffmpeg, setup_logging)
from scraper.pipeline import run

__all__: list = [
    "ScraperConfig",
    "check_ffmpeg",
    "setup_logging",
    "run",
]
