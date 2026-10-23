"""
Side-by-side composite visual export engine for PromptLens.
Combines clean original capture screenshots with full review margin notes
into a single publication-ready PNG image for AI vision agents and human reviews.
"""

import os
import textwrap
from typing import Any, List, Optional
from PIL import Image, ImageDraw, ImageFont, ImageColor


def _draw_dashed_rectangle(draw: ImageDraw.ImageDraw, box, color, width: int = 2, dash: int = 7, gap: int = 4) -> None:
    """Draw a dashed rectangular outline using only Pillow primitives."""
    x1, y1, x2, y2 = box
    left, right = min(x1, x2), max(x1, x2)
    top, bottom = min(y1, y2), max(y1, y2)
    for y in (top, bottom):
        pos = left
        while pos < right:
            next_pos = min(pos + dash, right)
            draw.line([(pos, y), (next_pos, y)], fill=color, width=width)
            pos += dash + gap
    for x in (left, right):
        pos = top
        while pos < bottom:
            next_pos = min(pos + dash, bottom)
            draw.line([(x, pos), (x, next_pos)], fill=color, width=width)
            pos += dash + gap


def compute_card_height(item: Any, line_width: int = 44) -> int:
    """
    Calculate required vertical pixel height for a review margin card.
    """
    notes = getattr(item, "comment", "") or "(No written notes)"
    wrapped = textwrap.wrap(notes, width=line_width) or ["(No written notes)"]
    display_lines = len(wrapped[:6])
    has_ellipsis = 1 if len(wrapped) > 6 else 0
    total_text_lines = display_lines + has_ellipsis
    voice_file = getattr(item, "voice_file", None)
    voice_extra = 28 if voice_file else 0
    content_h = 44 + total_text_lines * 18 + voice_extra
    return max(content_h, 90 if voice_file else 70)


def render_composite_image(
    orig_image: Image.Image,
    annotations: List[Any],
    margin_width: int = 440
) -> Image.Image:
    """
    Render a high-resolution side-by-side composite image with the clean capture
    on the left and the review margin cards on the right.
    """
    img_w, img_h = orig_image.size
    margin_w = max(320, int(margin_width))
    comp_w = img_w + margin_w

    card_heights = [compute_card_height(it) for it in annotations]
    total_margin_h = 60 + sum(h + 12 for h in card_heights) + 40
    comp_h = max(img_h, total_margin_h)

    # Initialize composite canvas with dark slate background
    annotated_left = orig_image.convert("RGBA").copy()
    left_draw = ImageDraw.Draw(annotated_left)

    try:
        font_bold = ImageFont.truetype("segoeuib.ttf", 13)
        font = ImageFont.truetype("segoeui.ttf", 11)
        font_sm = ImageFont.truetype("segoeui.ttf", 10)
    except Exception:
        font_bold = ImageFont.load_default()
        font = ImageFont.load_default()
        font_sm = ImageFont.load_default()

    # Draw visual annotations onto annotated_left if item has coords
    for idx, item in enumerate(annotations):
        coords = getattr(item, "coords", None)
        if not coords:
            continue
        itype = getattr(item, "item_type", "box")
        badge = getattr(item, "badge_label", f"[{idx+1}]")
        try:
            if itype == "box" and len(coords) == 4:
                x1, y1, x2, y2 = coords
                bx1, by1, bx2, by2 = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
                col = getattr(item, "color", None) or "#00E5FF"
                width = getattr(item, "stroke_width", 2)
                if getattr(item, "line_style", "solid") == "dashed":
                    _draw_dashed_rectangle(left_draw, (bx1, by1, bx2, by2), col, width=width)
                else:
                    left_draw.rectangle([bx1, by1, bx2, by2], outline=col, width=width)
                left_draw.rectangle([bx1, max(0, by1 - 18), bx1 + 32, max(18, by1)], fill=col, outline="#11111b")
                left_draw.text((bx1 + 4, max(0, by1 - 17)), badge, fill="#11111b", font=font_sm)
            elif itype == "arrow" and len(coords) == 4:
                x1, y1, x2, y2 = coords
                col = getattr(item, "color", None) or "#CBA6F7"
                left_draw.line([(x1, y1), (x2, y2)], fill=col, width=getattr(item, "stroke_width", 2))
                try:
                    from arrow_annotator import calculate_arrowhead
                    head = calculate_arrowhead(x1, y1, x2, y2, head_len=16)
                    left_draw.polygon(head, fill=col)
                    if getattr(item, "arrow_style", "single") == "double":
                        left_draw.polygon(calculate_arrowhead(x2, y2, x1, y1, head_len=16), fill=col)
                except Exception:
                    pass
                left_draw.rectangle([x1 + 4, max(0, y1 - 20), x1 + 42, max(18, y1 - 2)], fill=col, outline="#11111b")
                left_draw.text((x1 + 8, max(0, y1 - 19)), badge, fill="#11111b", font=font_sm)
            elif itype == "shape" and len(coords) == 4:
                st = getattr(item, "shape_type", "rectangle")
                col = getattr(item, "color", None) or "#00E5FF"
                try:
                    from geometric_shapes import draw_geometric_shape_pil
                    annotated_left = draw_geometric_shape_pil(annotated_left, st, coords, color=col, width=getattr(item, "stroke_width", 2))
                    left_draw = ImageDraw.Draw(annotated_left)
                except Exception:
                    pass
            elif (
                itype == "pen"
                and isinstance(coords, (tuple, list))
                and len(coords) == 4
                and all(isinstance(c, (int, float)) for c in coords)
            ):
                x1, y1, x2, y2 = coords
                bx1, by1, bx2, by2 = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
                col = getattr(item, "color", None) or "#A6E3A1"
                alpha = {"light": 70, "medium": 125, "bold": 180}.get(getattr(item, "opacity", "medium"), 125)
                rgb = ImageColor.getrgb(col)
                overlay = Image.new("RGBA", annotated_left.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                border_width = int(getattr(item, "stroke_width", 2))
                overlay_draw.rectangle(
                    [bx1, by1, bx2, by2], fill=(*rgb, alpha),
                    outline=(*rgb, 255) if border_width else None, width=border_width
                )
                annotated_left = Image.alpha_composite(annotated_left, overlay)
                left_draw = ImageDraw.Draw(annotated_left)
                left_draw.rectangle([bx1, max(0, by1 - 18), bx1 + 34, max(18, by1)], fill=col, outline="#11111b")
                left_draw.text((bx1 + 4, max(0, by1 - 17)), getattr(item, "badge_label", f"[H{idx + 1}]"), fill="#11111b", font=font_sm)
            elif itype == "pen" and isinstance(coords, list) and len(coords) >= 2:
                pmode = getattr(item, "pen_mode", "highlighter")
                try:
                    from freehand_pen import render_freehand_stroke_pil
                    if pmode == "pen":
                        annotated_left = render_freehand_stroke_pil(annotated_left, coords, mode="pen", color=ImageColor.getrgb(getattr(item, "color", None) or "#00E5FF"), width=getattr(item, "stroke_width", 2))
                    else:
                        highlight_rgb = ImageColor.getrgb(getattr(item, "color", None) or "#A6E3A1")
                        alpha = {"light": 70, "medium": 125, "bold": 180}.get(getattr(item, "opacity", "medium"), 125)
                        annotated_left = render_freehand_stroke_pil(annotated_left, coords, mode="highlighter", color=highlight_rgb, width=18, alpha=alpha)
                    left_draw = ImageDraw.Draw(annotated_left)
                except Exception:
                    pass
            elif itype == "text" and len(coords) == 2:
                txt = getattr(item, "comment", "") or f"Callout #{getattr(item, 'index', idx+1)}"
                try:
                    from text_callout import render_text_callout_pil
                    text_rgb = ImageColor.getrgb(getattr(item, "color", None) or "#CDD6F4")
                    text_size = {"small": 11, "medium": 14, "large": 18}.get(getattr(item, "size_preset", "medium"), 14)
                    annotated_left = render_text_callout_pil(
                        annotated_left, top_left=coords, text=txt, font_size=text_size,
                        text_color=(*text_rgb, 255), border_color=(*text_rgb, 255)
                    )
                    left_draw = ImageDraw.Draw(annotated_left)
                except Exception:
                    pass
            elif itype == "step" and len(coords) == 2:
                try:
                    from step_sequence import draw_step_badge_pil
                    step_rgb = ImageColor.getrgb(getattr(item, "color", None) or "#89B4FA")
                    annotated_left = draw_step_badge_pil(annotated_left, center=coords, step_num=getattr(item, "index", idx+1), radius={"small": 12, "medium": 16, "large": 22}.get(getattr(item, "size_preset", "medium"), 16), bg_color=(*step_rgb, 255))
                    left_draw = ImageDraw.Draw(annotated_left)
                except Exception:
                    pass
            elif itype == "stamp" and len(coords) == 2:
                try:
                    from stamp_library import draw_stamp_pil
                    radius = {"small": 12, "medium": 16, "large": 22}.get(getattr(item, "size_preset", "medium"), 16)
                    draw_stamp_pil(left_draw, getattr(item, "stamp_type", "check"), coords, radius=radius, custom_color=getattr(item, "color", None))
                except Exception:
                    pass
            elif itype == "poi" and len(coords) == 2:
                px, py = coords
                col = getattr(item, "color", None) or "#FAB387"
                radius = {"small": 12, "medium": 16, "large": 24}.get(getattr(item, "size_preset", "medium"), 16)
                left_draw.ellipse([px - radius, py - radius, px + radius, py + radius], outline=col, width=2)
                left_draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=col, outline="#11111b")
                left_draw.rectangle([px + 6, max(0, py - 20), px + 42, max(18, py - 2)], fill=col, outline="#11111b")
                left_draw.text((px + 10, max(0, py - 19)), badge, fill="#11111b", font=font_sm)
        except Exception:
            pass

    composite = Image.new("RGBA", (comp_w, comp_h), "#181825")
    composite.paste(annotated_left, (0, 0))

    draw = ImageDraw.Draw(composite)
    margin_x = img_w

    # Vertical divider border
    draw.rectangle([margin_x, 0, comp_w, comp_h], fill="#1e1e2e")
    draw.line([(margin_x, 0), (margin_x, comp_h)], fill="#313244", width=2)

    # Header banner
    draw.text((margin_x + 16, 14), "REVIEW NOTATIONS MARGIN", fill="#CDD6F4", font=font_bold)
    count_text = f"{len(annotations)} item{'s' if len(annotations) != 1 else ''}"
    draw.text((comp_w - 70, 16), count_text, fill="#A6ADC8", font=font_sm)

    card_y = 52
    for idx, item in enumerate(annotations):
        itype = getattr(item, "item_type", "box")
        color = getattr(item, "color", None) or ("#00E5FF" if itype == "box" else "#FAB387")
        badge_label = getattr(item, "badge_label", f"[{idx+1}]")
        title = getattr(item, "title", f"Item {idx+1}")
        notes = getattr(item, "comment", "") or "(No written notes)"

        wrapped = textwrap.wrap(notes, width=44) or ["(No written notes)"]
        display_lines = wrapped[:6]
        c_height = card_heights[idx]

        # Card container rectangle
        draw.rectangle([margin_x + 12, card_y, comp_w - 12, card_y + c_height], fill="#252538", outline="#3b3b54")

        # Badge pill
        draw.rectangle([margin_x + 16, card_y + 8, margin_x + 50, card_y + 26], fill=color)
        draw.text((margin_x + 20, card_y + 8), badge_label, fill="#11111b", font=font_bold)
        draw.text((margin_x + 58, card_y + 8), title, fill="#CDD6F4", font=font_bold)

        # Comment note lines
        line_y = card_y + 34
        for line in display_lines:
            draw.text((margin_x + 18, line_y), line, fill="#A6ADC8", font=font)
            line_y += 18
        if len(wrapped) > 6:
            draw.text((margin_x + 18, line_y), "...", fill="#A6ADC8", font=font)
            line_y += 18

        # Inline voice indicator
        voice_file = getattr(item, "voice_file", None)
        voice_dur = float(getattr(item, "voice_duration", 0.0))
        if voice_file:
            v_text = f"🎙️ Voice Memo: {os.path.basename(voice_file)} ({voice_dur:.1f}s)"
            draw.text((margin_x + 18, line_y + 2), v_text, fill="#A6E3A1", font=font_sm)

        card_y += c_height + 12

    return composite


def save_composite_export(
    orig_image: Image.Image,
    annotations: List[Any],
    output_path: str,
    margin_width: int = 440
) -> str:
    """
    Render and save side-by-side composite PNG to output_path.
    """
    comp = render_composite_image(orig_image, annotations, margin_width=margin_width)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    comp.save(output_path, "PNG")
    return output_path
