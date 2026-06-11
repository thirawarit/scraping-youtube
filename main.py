"""Command-line entry point for the YouTube scraper.

Parses arguments, configures logging, verifies ffmpeg, and runs the scrape
pipeline for a YouTube playlist or video URL.

Example:
    $ python main.py "https://www.youtube.com/watch?v=<id>" --workers 4
"""

import argparse
import logging
import sys
from pathlib import Path

from scraper.config import (ScraperConfig, check_ffmpeg, load_proxy_config,
                            setup_logging)
from scraper.pipeline import run

logger: logging.Logger = logging.getLogger(__name__)


def get_parser() -> argparse.ArgumentParser:
    """Build and return the command-line argument parser.

    Returns:
        A parser accepting a positional ``url`` and the ``--output-dir``,
        ``--workers``, and ``--force`` options.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="scraping-youtube",
        description=(
            "Scrape a YouTube playlist or video: extract metadata + original-language "
            "transcript and download best-quality WAV audio into a combined JSONL output."
        ),
    )
    parser.add_argument(
        "url",
        type=str,
        help="A YouTube playlist URL or a single video URL.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Base output directory (default: output/).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent worker threads (default: 4).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process videos even if already present in the output.",
    )
    parser.add_argument(
        "--cookies",
        type=Path,
        default=None,
        help=(
            "Path to a Netscape-format cookies.txt. Use this to get past "
            "region/age/bot walls (e.g. HTTP 403)."
        ),
    )
    parser.add_argument(
        "--cookies-from-browser",
        type=str,
        default=None,
        help=(
            "Load cookies directly from a browser (e.g. chrome, safari, firefox) "
            "to get past region/age/bot walls."
        ),
    )
    parser.add_argument(
        "--transcripts",
        action="store_true",
        help=(
            "Enable youtube_transcript_api for transcripts (default: off). "
            "Reads Webshare proxy_username/proxy_password from .env when present. "
            "Regardless of this flag, yt_dlp auto-subtitles are used as a fallback."
        ),
    )
    return parser


def main(argv: list = sys.argv[1:]) -> int:
    """Run the scraper as a CLI program.

    Args:
        argv: Argument list to parse (defaults to the process arguments).

    Returns:
        Process exit code: ``0`` on success, ``1`` on a fatal error (missing
        ffmpeg, invalid options, or an unrecoverable run failure).
    """
    parser: argparse.ArgumentParser = get_parser()
    args: argparse.Namespace = parser.parse_args(argv)

    setup_logging()

    try:
        check_ffmpeg()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    if args.workers < 1:
        logger.error("--workers must be >= 1")
        return 1

    config: ScraperConfig = ScraperConfig(
        url=args.url,
        output_dir=args.output_dir,
        workers=args.workers,
        force=args.force,
        cookies=args.cookies,
        cookies_from_browser=args.cookies_from_browser,
        transcripts=args.transcripts,
        proxy_config=load_proxy_config() if args.transcripts else None,
    )

    try:
        run(config)
    except Exception as exc:  # noqa: BLE001 - top-level guard for fatal run errors
        logger.error("Fatal error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
