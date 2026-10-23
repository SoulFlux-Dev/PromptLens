"""
Numbered Step Sequence Badges for PromptLens Notation Editor.

Generates numbered sequence badges (Step 1, Step 2, Step 3...) to annotate
bug reproduction sequences, step-by-step walkthroughs, and UI interaction flows.
"""

from typing import Tuple, List, Optional
from PIL import Image, ImageDraw, ImageFont


STEP_CIRCLES = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩",
                "⑪", "⑫", "⑬", "⑭", "⑮", "⑯", "⑰", "⑱", "⑲", "⑳"]


def get_step_glyph(step_number: int) -> str:
    """Return circular unicode numeral or bracketed number."""
    if 1 <= step_number <= len(STEP_CIRCLES):
        return STEP_CIRCLES[step_number - 1]
    return f"[{step_number}]"


def draw_step_badge_pil(
    image: Image.Image,
    center: Tuple[int, int],
    step_num: int,
    radius: int = 16,
    bg_color: Tuple[int, int, int, int] = (137, 180, 250, 255),
    text_color: Tuple[int, int, int, int] = (17, 17, 27, 255),
    border_color: Tuple[int, int, int, int] = (255, 255, 255, 255)
) -> Image.Image:
    """
    Render a circular numbered step badge onto a PIL Image copy.
    """
    result = image.copy()
    draw = ImageDraw.Draw(result)

    cx, cy = center
    x1 = cx - radius
    y1 = cy - radius
    x2 = cx + radius
    y2 = cy + radius

    # Outer border ring
    draw.ellipse([x1 - 2, y1 - 2, x2 + 2, y2 + 2], fill=border_color)
    # Badge background circle
    draw.ellipse([x1, y1, x2, y2], fill=bg_color)

    # Step label
    label = str(step_num)
    try:
        font = ImageFont.truetype("arial.ttf", size=max(10, int(radius * 1.1)))
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw / 2
    ty = cy - th / 2 - 1

    draw.text((tx, ty), label, fill=text_color, font=font)
    return result


class StepSequenceManager:
    """
    Manages numbered step sequence ordering, auto-renumbering, and badge metadata.
    """
    def __init__(self):
        self.steps: List[dict] = []

    def add_step(self, coords: Tuple[int, int], comment: str = "") -> dict:
        step_num = len(self.steps) + 1
        step_item = {
            "step": step_num,
            "coords": coords,
            "comment": comment,
            "badge": f"[S{step_num}]",
            "glyph": get_step_glyph(step_num),
        }
        self.steps.append(step_item)
        return step_item

    def remove_step(self, step_num: int, renumber: bool = True) -> Optional[dict]:
        idx = -1
        for i, s in enumerate(self.steps):
            if s["step"] == step_num:
                idx = i
                break
        if idx == -1:
            return None

        removed = self.steps.pop(idx)
        if renumber:
            self.renumber_steps()
        return removed

    def renumber_steps(self) -> None:
        for i, s in enumerate(self.steps):
            s["step"] = i + 1
            s["badge"] = f"[S{i + 1}]"
            s["glyph"] = get_step_glyph(i + 1)

    def count(self) -> int:
        return len(self.steps)
