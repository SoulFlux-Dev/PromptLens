"""
Automatic punctuation restoration and filler word cleanup for PromptLens.
Cleans verbal disfluencies (um, uh, er, ah, you know) and normalizes punctuation
and sentence capitalization for natural, publication-ready review notes.
"""

import re
from typing import Optional


FILLER_REGEX = re.compile(
    r"\b(um|uh|er|ah|you know|sort of|kind of)\b(?:\s*,\s*|\s*)?",
    re.IGNORECASE
)

DUPLICATE_WORDS_REGEX = re.compile(
    r"\b([a-zA-Z]+)\s+\1\b",
    re.IGNORECASE
)


def clean_filler_words(text: Optional[str]) -> str:
    """
    Remove verbal fillers and stuttered duplicate words.
    Cleans up resulting whitespace and dangling commas.
    """
    if not text:
        return ""

    cleaned = FILLER_REGEX.sub(" ", text)
    # Remove repeated immediate words ("the the" -> "the")
    cleaned = DUPLICATE_WORDS_REGEX.sub(r"\1", cleaned)

    # Normalize weird comma and punctuation artifacts (e.g. ", ,")
    cleaned = re.sub(r"\s*,\s*,+", ",", cleaned)
    cleaned = re.sub(r"^\s*,\s*", "", cleaned)
    cleaned = re.sub(r"\s*,\s*\.", ".", cleaned)
    cleaned = re.sub(r"\s*,\s*$", "", cleaned)
    cleaned = re.sub(r"\s*,\s*([a-zA-Z])", r", \1", cleaned)

    # Normalize multiple whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    # Strip leading/trailing dangling commas
    cleaned = cleaned.strip(",").strip()
    return cleaned


def restore_punctuation(text: Optional[str]) -> str:
    """
    Restore capitalization at sentence boundaries and ensure terminal punctuation.
    """
    if not text:
        return ""

    s = text.strip()
    if not s:
        return ""

    # Capitalize the first letter
    s = s[0].upper() + s[1:] if len(s) > 1 else s.upper()

    # Capitalize after sentence-ending punctuation (. ! ?)
    def cap_after_punct(match):
        punct = match.group(1)
        ws = match.group(2)
        letter = match.group(3)
        return f"{punct}{ws}{letter.upper()}"

    s = re.sub(r"([\.\!\?])(\s+)([a-z])", cap_after_punct, s)

    # Ensure terminal punctuation if missing and not ending with colon or markdown syntax
    if s and s[-1] not in (".", "!", "?", ":", ";", "`", "*"):
        s = s + "."

    return s


def post_process_transcript(text: Optional[str]) -> str:
    """
    Full pipeline: strips filler disfluencies, normalizes punctuation, and restores sentence casing.
    """
    if not text:
        return ""
    cleaned = clean_filler_words(text)
    return restore_punctuation(cleaned)
