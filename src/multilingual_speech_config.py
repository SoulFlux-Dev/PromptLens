"""
Multi-language speech recognition configuration for PromptLens.
Provides language catalogs, language code normalization, and model compatibility checks
to allow narration in non-English languages using multilingual Whisper models.
"""

from typing import Dict, List, Optional

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "auto": "Auto-Detect",
}


def list_language_codes() -> List[str]:
    """Return all supported language code identifiers."""
    return list(SUPPORTED_LANGUAGES.keys())


def get_language_display_name(code: str) -> str:
    """Return human-readable display name for language code."""
    cleaned = (code or "").strip().lower()
    return SUPPORTED_LANGUAGES.get(cleaned, "English")


def is_multilingual_model(model_name: str) -> bool:
    """
    Check if a Whisper model supports multi-language transcription.
    Models ending with .en (e.g. tiny.en, base.en) are English-only.
    """
    name = (model_name or "").strip().lower()
    return not name.endswith(".en")


def resolve_effective_model(model_name: str, language_code: str) -> str:
    """
    Ensure the model is capable of the requested language.
    If a non-English language is requested with an English-only model (.en),
    switch automatically to the corresponding multilingual model.
    """
    name = (model_name or "base").strip().lower()
    lang = (language_code or "en").strip().lower()

    if lang not in ("en", "auto") and name.endswith(".en"):
        # Strip .en suffix to use multilingual version
        base_name = name[:-3]
        return base_name if base_name else "base"
    return name


def normalize_language_code(input_str: Optional[str]) -> str:
    """
    Normalize language input string (code or name) into a valid language code.
    Defaults to 'en' if unrecognized.
    """
    if not input_str:
        return "en"
    cleaned = input_str.strip().lower()
    if cleaned in SUPPORTED_LANGUAGES:
        return cleaned

    # Check display names
    for code, name in SUPPORTED_LANGUAGES.items():
        if cleaned == name.lower():
            return code

    return "en"
