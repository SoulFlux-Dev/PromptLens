"""
Pre-configured annotation card templates for PromptLens Notation Editor.
Provides quick structured comment templates for Bug Reports, UI Reviews,
Code Audits, and Feature Walkthroughs.
"""

from typing import Any, Dict, List, Optional

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "bug_report": {
        "id": "bug_report",
        "name": "Bug Report",
        "description": "Structured defect reproduction template",
        "default_color": "#F38BA8",
        "template_text": "**Observed**:\n**Expected**:\n**Steps**:\n1. ",
    },
    "ui_review": {
        "id": "ui_review",
        "name": "UI Review",
        "description": "Design feedback, layout alignment, visual polish",
        "default_color": "#FAB387",
        "template_text": "**Design Feedback**:\n**Alignment**:\n**Action Item**:\n- ",
    },
    "code_audit": {
        "id": "code_audit",
        "name": "Code Audit",
        "description": "Architectural finding, risk severity, recommended fix",
        "default_color": "#CBA6F7",
        "template_text": "**Finding**:\n**Risk / Impact**:\n**Recommended Fix**:\n- ",
    },
    "walkthrough": {
        "id": "walkthrough",
        "name": "Walkthrough",
        "description": "Step-by-step user guide or tutorial sequence",
        "default_color": "#89B4FA",
        "template_text": "**Step Goal**:\n**User Action**:\n**Validation**:\n",
    },
}


def list_template_ids() -> List[str]:
    """Return all supported template identifier keys."""
    return list(TEMPLATES.keys())


def get_template(template_id: str) -> Dict[str, Any]:
    """Retrieve template definition by identifier, falling back to bug_report."""
    cleaned = (template_id or "").strip().lower()
    return TEMPLATES.get(cleaned, TEMPLATES["bug_report"]).copy()


def apply_template(item: Any, template_id: str) -> bool:
    """
    Apply template text and color defaults to an annotation item.
    Appends template text if item already has notes, otherwise replaces.
    """
    if not item:
        return False
    tmpl = get_template(template_id)
    existing_comment = getattr(item, "comment", "")
    if existing_comment and existing_comment.strip():
        item.comment = existing_comment.strip() + "\n\n" + tmpl["template_text"]
    else:
        item.comment = tmpl["template_text"]

    if not getattr(item, "color", None):
        item.color = tmpl["default_color"]

    return True
