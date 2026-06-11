#!/usr/bin/env bash
#
# run_playlists.sh — Batch-run the YouTube scraper over a list of playlists.
#
# Transcripts are OFF for this batch (the --transcripts flag is omitted), so
# transcripts come only from yt_dlp auto-subtitles. Add --transcripts to the
# python invocation below to enable youtube_transcript_api (and Webshare proxy
# via .env).
#
# Usage:
#   ./run_playlists.sh
#
set -euo pipefail

# Resolve repo root so the script works from any directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate the virtualenv if present.
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

# --- Configuration -----------------------------------------------------------
OUTPUT_DIR="output"
WORKERS=4

# Replace these placeholder URLs with your actual YouTube playlist URLs.
# One URL per line; keep the surrounding parentheses.
PLAYLISTS=(
  "https://www.youtube.com/playlist?list=PLACEHOLDER_PLAYLIST_ID_1"
  "https://www.youtube.com/playlist?list=PLACEHOLDER_PLAYLIST_ID_2"
  "https://www.youtube.com/playlist?list=PLACEHOLDER_PLAYLIST_ID_3"
)
# -----------------------------------------------------------------------------

total=${#PLAYLISTS[@]}
failed=0
index=0

for url in "${PLAYLISTS[@]}"; do
  index=$((index + 1))
  echo "==================================================================="
  echo "[${index}/${total}] Scraping: ${url}"
  echo "==================================================================="

  # Continue to the next playlist on failure; record a non-zero overall exit.
  if python main.py "$url" --output-dir "$OUTPUT_DIR" --workers "$WORKERS"; then
    echo "[${index}/${total}] Done: ${url}"
  else
    echo "[${index}/${total}] FAILED: ${url}" >&2
    failed=$((failed + 1))
  fi
done

echo "==================================================================="
echo "Batch complete. total=${total} ok=$((total - failed)) failed=${failed}"
echo "==================================================================="

if [[ "$failed" -gt 0 ]]; then
  exit 1
fi
