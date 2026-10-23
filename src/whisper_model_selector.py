"""
Whisper model selector and configuration helper for PromptLens.
Provides model options (tiny.en, base, small), performance profiles, and validation
so users can balance speed versus accuracy in the settings GUI.
"""

from typing import Any, Dict, List, Optional

WHISPER_MODELS: Dict[str, Dict[str, Any]] = {
    "tiny.en": {
        "id": "tiny.en",
        "display_name": "Tiny (English - Ultra Fast)",
        "disk_mb": 75,
        "ram_mb": 390,
        "speed_rating": "5/5",
        "accuracy_rating": "3/5",
        "multilingual": False,
        "recommended_for": "Quick voice notes and low-spec machines",
    },
    "base": {
        "id": "base",
        "display_name": "Base (Multilingual - Balanced)",
        "disk_mb": 142,
        "ram_mb": 500,
        "speed_rating": "4/5",
        "accuracy_rating": "4/5",
        "multilingual": True,
        "recommended_for": "Everyday reviews and non-English commentary",
    },
    "small": {
        "id": "small",
        "display_name": "Small (Multilingual - Accurate)",
        "disk_mb": 466,
        "ram_mb": 1000,
        "speed_rating": "3/5",
        "accuracy_rating": "5/5",
        "multilingual": True,
        "recommended_for": "Technical terms, code snippets, and noisy audio",
    },
}


def list_selectable_models() -> List[str]:
    """Return available model identifier keys."""
    return list(WHISPER_MODELS.keys())


def get_model_profile(model_id: str) -> Dict[str, Any]:
    """Retrieve metadata profile for a given model, defaulting to base."""
    cleaned = (model_id or "").strip().lower()
    return WHISPER_MODELS.get(cleaned, WHISPER_MODELS["base"]).copy()


def validate_model_choice(model_id: Optional[str]) -> str:
    """Validate and return safe model choice string."""
    cleaned = (model_id or "").strip().lower()
    if cleaned in WHISPER_MODELS:
        return cleaned
    return "base"
