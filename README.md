# scraping-youtube

A YouTube scraping tool built on [`yt_dlp`](https://github.com/yt-dlp/yt-dlp) and
[`youtube_transcript_api`](https://github.com/jdepoix/youtube-transcript-api). Give it a
**single playlist URL** or a **single video URL**; it extracts metadata + the
original-language transcript and downloads best-quality **WAV** audio, writing everything
into a combined `metadata.jsonl` per run.

> Intended to be combined with another project downstream. Output is multi-language
> (English, Thai, Chinese).

---

## Requirements

- **Python 3.10+** (developed on 3.10.20)
- **ffmpeg** on your `PATH` — required to convert audio to WAV
  (`brew install ffmpeg` on macOS; `apt install ffmpeg` on Debian/Ubuntu)

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Pinned dependencies (`requirements.txt`):

| Package | Version |
|---|---|
| `yt_dlp` | `2026.3.17` |
| `youtube_transcript_api` | `1.2.4` |

> **Heads-up:** `yt_dlp` releases frequently to keep up with YouTube changes. If extraction
> suddenly breaks (e.g. HTTP 403), the first thing to try is `pip install -U yt_dlp`.

---

## Usage

```bash
python main.py "<YOUTUBE_PLAYLIST_OR_VIDEO_URL>" [options]
```

### Examples

```bash
# A single video
python main.py "https://www.youtube.com/watch?v=<id>"

# A playlist, 2 worker threads, loading cookies from Firefox (gets past bot/age/region walls)
python main.py "https://youtube.com/playlist?list=<id>" --workers 2 --cookies-from-browser firefox

# Force re-processing of videos already in the output
python main.py "<url>" --force
```

### Options

| Option | Default | Description |
|---|---|---|
| `url` (positional) | — | A YouTube **playlist** URL or a single **video** URL. Required. |
| `--output-dir DIR` | `data/output/` | Base output directory. Each run writes to `data/output/<slug>/`. |
| `--workers N` | `4` | Number of concurrent worker threads. Use `1–2` if you hit rate limits. |
| `--force` | off | Re-process videos even if already present in the output. |
| `--cookies FILE` | none | Path to a Netscape-format `cookies.txt`. Use to get past region/age/bot walls (HTTP 403). |
| `--cookies-from-browser NAME` | none | Load cookies directly from a browser (`chrome`, `safari`, `firefox`, …). |

---

## Output

Each run is named by a normalized slug of the playlist/video title:

```
data/output/
└── <slug>/
    ├── metadata.jsonl        # one JSON record per video (combined metadata + transcript)
    └── audio/
        ├── 001_<video_id>.wav
        ├── 002_<video_id>.wav
        └── ...
```

### `metadata.jsonl` record schema

One JSON object per line:

```jsonc
{
  "index": 1,                       // playlist position
  "video_id": "a1b2c3d4",
  "url": "https://www.youtube.com/watch?v=a1b2c3d4",
  "title": "Normalized title",      // emoji/special chars stripped
  "title_raw": "Original title 🎬",
  "channel": "Channel name",
  "channel_id": "UC...",
  "upload_date": "2024-01-31",      // YYYY-MM-DD
  "duration_sec": 3221,
  "view_count": 12345,
  "like_count": 678,
  "language": "th",
  "transcript": [                   // null if none could be fetched
    { "text": "…", "start": 0.199, "duration": 6.761 }
  ],
  "transcript_source": "youtube_transcript_api",  // or "yt_dlp_auto" / null
  "audio_path": "audio/001_a1b2c3d4.wav",      // relative to the run dir
  "status": "ok",                   // "ok" or "error"
  "error": null                     // message when status == "error"
}
```

A failed video is still recorded with `status: "error"` and a message — one failure never
aborts the run.

---

## How it works

`main.py` parses args → `scraper/pipeline.py:run()` orchestrates:

1. **List** playlist entries (`scraper/extractor.py`).
2. **Resume:** skip videos already completed (see below).
3. **Process** each pending video concurrently in a thread pool: fetch metadata →
   fetch transcript (`scraper/transcripts.py`) → download + convert audio to WAV
   (`download_wav`).
4. **Merge** results atomically into `metadata.jsonl`, ordered by playlist index.

### Module map

| File | Responsibility |
|---|---|
| `main.py` | CLI entry point, `get_parser()`, logging + ffmpeg checks |
| `scraper/config.py` | `ScraperConfig`, logging setup (Bangkok TZ), `check_ffmpeg()` |
| `scraper/pipeline.py` | Orchestration, concurrency, resume, per-video isolation |
| `scraper/extractor.py` | yt_dlp wrappers: list entries, fetch metadata, `download_wav` |
| `scraper/transcripts.py` | Transcript fetch (API first, yt_dlp auto-subs fallback) |
| `scraper/normalize.py` | Title normalization + slugify |
| `scraper/store.py` | Read/write `metadata.jsonl` (resume + atomic merge) |
| `scraper/models.py` | `VideoRecord` / `PlaylistEntry` / `TranscriptSnippet` types |

### Resume behavior

Re-running the same URL is safe and resumes where it left off:

- Videos already recorded as `status: "ok"` in `metadata.jsonl` are skipped.
- **Audio files already on disk are skipped** even if a prior run was interrupted before
  `metadata.jsonl` was written — `download_wav` returns early when a non-empty `<stem>.wav`
  already exists. Incomplete/zero-byte files are re-downloaded.
- Use `--force` to override and re-process everything.

This makes a **transcript-only top-up run** cheap: existing WAVs are skipped and only
missing transcripts are re-fetched.

---

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `ffmpeg was not found on PATH` | Install ffmpeg (`brew install ffmpeg`). |
| **HTTP 403** on download | Bot/age/region wall. Pass `--cookies-from-browser firefox` (or `--cookies cookies.txt`). If it persists, `pip install -U yt_dlp`. |
| **HTTP 429 / "YouTube is blocking requests from your IP"** on transcripts | Rate limit / temporary IP block. Lower `--workers` (1–2), wait, or run behind a **VPN/proxy** (a different IP is the reliable fix). Audio downloads are unaffected; you can finish audio first and fetch transcripts later. |
| Transcript is `null` for many videos | Usually the 429 IP block above, or the video genuinely has no captions. |
| Run seems to re-download existing audio | Should not happen anymore — `download_wav` skips existing non-empty WAVs. Check the file isn't zero-byte / `.part`. |

> ⚠️ **WAV is uncompressed and large.** Roughly ~0.6 GB per hour of audio — a 100+ video
> playlist can be **tens of GB**. Watch free disk space before large runs.

---

## Logging

Logs go to stderr with timestamps in the **Asia/Bangkok** timezone:

```
2026-06-08 13:59:43 | INFO | scraper.config:71 | Found ffmpeg at /opt/homebrew/bin/ffmpeg
```

Format: `asctime | levelname | name:lineno | message`.

---

## Conventions (for contributors)

- All variables/functions are **type-annotated** (`typing`); typecheck with
  `mypy --ignore-missing-imports scraper main.py` before finishing changes.
- Imports of more than one object use brackets: `from foo import (a, b)`.
- Use `logging`, not `print`, for system messages.
- Pin/update versions in `requirements.txt` when adding dependencies.
- See `SPEC.md` for the full specification and `CLAUDE.md` for working guidelines.
