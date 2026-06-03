"""Title and slug normalization for multi-language YouTube content.

Strips emoji and special characters while preserving English, Thai, and
Chinese (CJK) text, so titles render cleanly and slugs stay filesystem-safe.
"""

import re
import unicodedata
from typing import Optional

# Keep: ASCII letters/digits, whitespace, and CJK + Thai script ranges.
# Strip: emoji, symbols, pictographs, and other special characters.
_ALLOWED_PATTERN: re.Pattern = re.compile(
    r"[^"
    r"0-9A-Za-z"
    r"฀-๿"          # Thai
    r"一-鿿"          # CJK Unified Ideographs
    r"㐀-䶿"          # CJK Extension A
    r"豈-﫿"          # CJK Compatibility Ideographs
    r"　-〿"          # CJK symbols/punctuation
    r"＀-￯"          # Fullwidth forms
    r"\s"
    r"]"
)
_WHITESPACE_PATTERN: re.Pattern = re.compile(r"\s+")
_SLUG_STRIP_PATTERN: re.Pattern = re.compile(r"[^0-9A-Za-z฀-๿一-鿿㐀-䶿]+")


def normalize_title(raw: Optional[str]) -> str:
    """Normalize a title by stripping emoji and special characters.

    Applies NFKC normalization, removes disallowed characters (keeping
    English/Thai/Chinese letters, digits, CJK punctuation, and whitespace),
    then collapses runs of whitespace.

    Args:
        raw: The original title, or ``None``.

    Returns:
        The cleaned title, or an empty string if ``raw`` is falsy.

    Example:
        >>> normalize_title("🔥 Hot Video!! [Official] 🎵")
        'Hot Video Official'
    """
    if not raw:
        return ""
    text: str = unicodedata.normalize("NFKC", raw)
    text = _ALLOWED_PATTERN.sub(" ", text)
    text = _WHITESPACE_PATTERN.sub(" ", text)
    return text.strip()


def slugify(title: Optional[str], fallback: str = "video") -> str:
    """Convert a title into a filesystem-safe, lowercase slug.

    Normalizes the title, replaces non-alphanumeric runs with hyphens, lowers
    the case, and truncates to 80 characters. CJK and Thai letters are
    preserved.

    Args:
        title: The title to slugify, or ``None``.
        fallback: Slug to return when the result would be empty.

    Returns:
        A slug suitable for use as a directory name.

    Example:
        >>> slugify("Me at the zoo")
        'me-at-the-zoo'
    """
    normalized: str = normalize_title(title)
    slug: str = _SLUG_STRIP_PATTERN.sub("-", normalized).strip("-").lower()
    if not slug:
        return fallback
    return slug[:80].strip("-") or fallback
