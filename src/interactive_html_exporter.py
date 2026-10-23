"""
Interactive HTML Export Report Generator (MAN-013).
Generates a self-contained, single-file HTML review report with zoomable/pannable
canvas, synchronized annotation callouts, and embedded audio player.
"""

from __future__ import annotations
import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from base64_data_uri_exporter import file_to_data_uri
except ImportError:
    from .base64_data_uri_exporter import file_to_data_uri


def audio_file_to_data_uri(audio_path: Union[str, Path]) -> str:
    """Encodes local WAV or MP3 audio file into a Base64 data URI."""
    p = Path(audio_path)
    if not p.exists():
        return ""
    data = p.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    ext = p.suffix.lower().lstrip(".")
    mime = "audio/wav" if ext == "wav" else f"audio/{ext}"
    return f"data:{mime};base64,{encoded}"


def generate_html_report(
    base_name: str,
    clean_image_path: Union[str, Path],
    annotated_image_path: Union[str, Path],
    annotations: List[Any],
    embed_media: bool = True
) -> str:
    """
    Renders a standalone interactive HTML5 report string.
    """
    if embed_media:
        clean_src = file_to_data_uri(clean_image_path, max_dimension=1568)
        annotated_src = file_to_data_uri(annotated_image_path, max_dimension=1568)
    else:
        clean_src = Path(clean_image_path).name
        annotated_src = Path(annotated_image_path).name

    cards_html = []
    card_data = []

    for idx, item in enumerate(annotations):
        badge = getattr(item, "badge_label", f"[{chr(65 + idx % 26)}]")
        title = getattr(item, "title", f"Note {idx + 1}")
        comment = getattr(item, "comment", "") or ""
        item_type = getattr(item, "item_type", "box")
        coords = getattr(item, "coords", [])
        voice_file = getattr(item, "voice_file", None)
        voice_duration = getattr(item, "voice_duration", 0.0)

        audio_player_html = ""
        if voice_file and os.path.exists(voice_file):
            audio_src = audio_file_to_data_uri(voice_file) if embed_media else Path(voice_file).name
            audio_player_html = f"""
            <div class="audio-box">
                <audio controls src="{audio_src}" preload="none"></audio>
                <span class="audio-dur">({voice_duration:.1f}s)</span>
            </div>
            """

        card_html = f"""
        <div class="card" id="card-{idx}" onclick="selectCard({idx})">
            <div class="card-header">
                <span class="badge">{badge}</span>
                <span class="card-title">{title}</span>
            </div>
            <div class="card-body">
                <p class="comment">{comment if comment else "<i>(No text notes)</i>"}</p>
                {audio_player_html}
                <div class="coords">Type: {item_type.capitalize()} | {coords}</div>
            </div>
        </div>
        """
        cards_html.append(card_html)
        card_data.append({
            "index": idx,
            "badge": badge,
            "title": title,
            "type": item_type,
            "coords": coords
        })

    json_annotations = json.dumps(card_data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Review Notation: {base_name}</title>
<style>
  :root {{
    --bg-main: #0D1117;
    --bg-panel: #161B22;
    --border: #30363D;
    --text: #C9D1D9;
    --accent: #58A6FF;
    --accent-bg: #1F6FEB22;
    --card-bg: #21262D;
    --badge-bg: #FFCC00;
    --badge-fg: #000000;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg-main);
    color: var(--text);
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }}
  header {{
    background: var(--bg-panel);
    border-bottom: 1px solid var(--border);
    padding: 12px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  header h1 {{ font-size: 18px; color: #FFFFFF; font-weight: 600; }}
  .toolbar {{ display: flex; gap: 8px; }}
  .btn {{
    background: var(--card-bg);
    color: var(--text);
    border: 1px solid var(--border);
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    transition: background 0.15s;
  }}
  .btn:hover {{ background: var(--border); }}
  .btn.active {{ background: var(--accent); color: #FFF; border-color: var(--accent); }}
  .container {{
    display: flex;
    flex: 1;
    overflow: hidden;
  }}
  .canvas-panel {{
    flex: 1;
    background: #010409;
    position: relative;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: grab;
  }}
  .canvas-panel:active {{ cursor: grabbing; }}
  #viewport-img {{
    max-width: 95%;
    max-height: 95%;
    object-fit: contain;
    transition: transform 0.05s ease-out;
    user-select: none;
    pointer-events: none;
  }}
  .sidebar {{
    width: 380px;
    background: var(--bg-panel);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    padding: 16px;
    gap: 12px;
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
  }}
  .card:hover {{ border-color: var(--accent); }}
  .card.selected {{
    border-color: var(--accent);
    background: var(--accent-bg);
  }}
  .card-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
  .badge {{
    background: var(--badge-bg);
    color: var(--badge-fg);
    font-weight: bold;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 12px;
  }}
  .card-title {{ font-size: 14px; font-weight: 600; color: #FFF; }}
  .comment {{ font-size: 13px; line-height: 1.4; margin-bottom: 8px; }}
  .coords {{ font-size: 11px; color: #8B949E; font-family: monospace; }}
  .audio-box {{ display: flex; align-items: center; gap: 8px; margin: 8px 0; }}
  audio {{ height: 28px; width: 100%; }}
  .audio-dur {{ font-size: 11px; color: #8B949E; }}
</style>
</head>
<body>
<header>
  <h1>{base_name}</h1>
  <div class="toolbar">
    <button class="btn active" id="btn-annotated" onclick="switchView('annotated')">Annotated View</button>
    <button class="btn" id="btn-clean" onclick="switchView('clean')">Clean View</button>
    <button class="btn" onclick="resetZoom()">Reset Zoom</button>
  </div>
</header>
<div class="container">
  <div class="canvas-panel" id="canvas-panel" onwheel="handleWheel(event)" onmousedown="startPan(event)">
    <img id="viewport-img" src="{annotated_src}" alt="Screenshot View">
  </div>
  <div class="sidebar">
    {"".join(cards_html) if cards_html else "<p><i>No annotations recorded.</i></p>"}
  </div>
</div>
<script>
  let scale = 1.0;
  let panX = 0, panY = 0;
  let isPanning = false;
  let startX = 0, startY = 0;
  const imgEl = document.getElementById('viewport-img');
  const cleanSrc = "{clean_src}";
  const annotatedSrc = "{annotated_src}";
  const annotations = {json_annotations};

  function updateTransform() {{
    imgEl.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{scale}})`;
  }}
  function handleWheel(e) {{
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    scale = Math.min(Math.max(0.2, scale * factor), 5.0);
    updateTransform();
  }}
  function startPan(e) {{
    isPanning = true;
    startX = e.clientX - panX;
    startY = e.clientY - panY;
    window.addEventListener('mousemove', doPan);
    window.addEventListener('mouseup', stopPan);
  }}
  function doPan(e) {{
    if (!isPanning) return;
    panX = e.clientX - startX;
    panY = e.clientY - startY;
    updateTransform();
  }}
  function stopPan() {{
    isPanning = false;
    window.removeEventListener('mousemove', doPan);
    window.removeEventListener('mouseup', stopPan);
  }}
  function resetZoom() {{
    scale = 1.0; panX = 0; panY = 0;
    updateTransform();
  }}
  function switchView(mode) {{
    document.getElementById('btn-annotated').classList.toggle('active', mode === 'annotated');
    document.getElementById('btn-clean').classList.toggle('active', mode === 'clean');
    imgEl.src = (mode === 'annotated') ? annotatedSrc : cleanSrc;
  }}
  function selectCard(idx) {{
    document.querySelectorAll('.card').forEach(c => c.classList.remove('selected'));
    const target = document.getElementById(`card-${{idx}}`);
    if (target) target.classList.add('selected');
  }}
</script>
</body>
</html>"""
    return html


def save_html_report(
    html_content: str,
    output_path: Union[str, Path]
) -> Path:
    """Writes interactive HTML report to disk."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(html_content, encoding="utf-8")
    return out_p
