"""
Automatic voice-to-text insertion logic for PromptLens Notation Editor.
Formats transcribed voice commentary and inserts it directly into review margin cards.
"""

from typing import Any, Optional


def format_transcription_for_card(
    existing_comment: Optional[str],
    transcription: Optional[str],
    prefix: str = "🎙️ "
) -> str:
    """
    Format transcribed text cleanly into an existing comment block.
    Appends nicely if existing text is present, or initializes comment if empty.
    """
    clean_trans = (transcription or "").strip()
    if not clean_trans:
        return (existing_comment or "").strip()

    note_line = f"{prefix}{clean_trans}" if prefix else clean_trans
    clean_existing = (existing_comment or "").strip()

    if not clean_existing:
        return note_line
    return f"{clean_existing}\n\n{note_line}"


def insert_transcription_into_item(
    item: Any,
    transcription: Optional[str],
    prefix: str = "🎙️ "
) -> str:
    """
    Update an AnnotationItem's comment and its active Tkinter text widget with transcribed audio.
    """
    if not item:
        return ""

    curr_comment = getattr(item, "comment", "")
    updated = format_transcription_for_card(curr_comment, transcription, prefix=prefix)
    item.comment = updated

    widget = getattr(item, "text_widget", None)
    if widget is not None:
        try:
            widget.delete("1.0", "end")
            widget.insert("1.0", updated)
        except Exception:
            pass

    return updated
