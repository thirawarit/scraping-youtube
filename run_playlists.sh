#!/usr/bin/env bash
#
# run_playlists.sh — Batch-run the YouTube scraper over a list of playlists.
#
# Playlist URLs are read from a text file (default: data/input/playlists.txt),
# one URL per line. Blank lines and lines starting with '#' are ignored.
#
# Transcripts are OFF for this batch (the --transcripts flag is omitted), so
# transcripts come only from yt_dlp auto-subtitles. Add --transcripts to the
# python invocation below to enable youtube_transcript_api (and Webshare proxy
# via .env).
#
# Usage:
#   ./run_playlists.sh
#   PLAYLISTS_FILE=my-list.txt ./run_playlists.sh
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
OUTPUT_DIR="data/output"
WORKERS=4
PLAYLISTS_FILE="${PLAYLISTS_FILE:-data/input/playlists.txt}"
# -----------------------------------------------------------------------------

if [[ ! -f "$PLAYLISTS_FILE" ]]; then
  echo "Error: playlists file not found: ${PLAYLISTS_FILE}" >&2
  echo "Create it with one YouTube playlist URL per line." >&2
  exit 1
fi

# Read URLs from the file, skipping blank lines and '#' comments.
PLAYLISTS=()
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"                       # strip trailing CR (CRLF files)
  line="${line#"${line%%[![:space:]]*}"}"    # ltrim
  line="${line%"${line##*[![:space:]]}"}"    # rtrim
  [[ -z "$line" || "$line" == \#* ]] && continue
  PLAYLISTS+=("$line")
done < "$PLAYLISTS_FILE"

if [[ ${#PLAYLISTS[@]} -eq 0 ]]; then
  echo "Error: no playlist URLs found in ${PLAYLISTS_FILE}" >&2
  exit 1
fi

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
