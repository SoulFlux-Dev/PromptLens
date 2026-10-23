"""
LLM Prompt Template Manager (MAN-006).
Provides one-click prompt templates ("Fix Bug", "Implement UI", "Refactor Architecture", "Security Audit")
prepended to exported notation manifests for direct AI consumption.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class PromptTemplate:
    id: str
    title: str
    instruction: str
    category: str = "general"


DEFAULT_TEMPLATES: Dict[str, PromptTemplate] = {
    "bug": PromptTemplate(
        id="bug",
        title="Fix Bug",
        instruction=(
            "You are an expert software engineer. Review the annotated screenshot, "
            "notated callouts, and coordinates below. Diagnose the root cause of this bug, "
            "explain why it occurs, and provide the exact minimal code fix."
        ),
        category="debugging"
    ),
    "ui": PromptTemplate(
        id="ui",
        title="Implement UI",
        instruction=(
            "You are a senior frontend and UI engineer. Inspect the layout, bounding boxes, "
            "and visual styling indicated in the attached annotations. Implement the UI components "
            "matching this specification with clean styling and accessible ergonomics."
        ),
        category="frontend"
    ),
    "refactor": PromptTemplate(
        id="refactor",
        title="Refactor Architecture",
        instruction=(
            "You are a principal software architect. Review the highlighted architecture components "
            "and notated critiques. Propose a decoupled, high-performance refactoring plan "
            "preserving all existing engine invariants and behavioral contracts."
        ),
        category="architecture"
    ),
    "audit": PromptTemplate(
        id="audit",
        title="Code & Security Audit",
        instruction=(
            "You are a security and reliability auditor. Review the highlighted sections for logic flaws, "
            "concurrency hazards, state leaks, and invariant violations. Provide an actionable checklist "
            "with prioritized remediation steps."
        ),
        category="quality"
    )
}

_CUSTOM_TEMPLATES: Dict[str, PromptTemplate] = {}


def list_templates() -> List[PromptTemplate]:
    """Returns all built-in and registered custom prompt templates."""
    all_templates = list(DEFAULT_TEMPLATES.values()) + list(_CUSTOM_TEMPLATES.values())
    return all_templates


def get_template(template_id: str) -> Optional[PromptTemplate]:
    """Retrieves a prompt template by ID."""
    t_id = template_id.lower().strip()
    if t_id in _CUSTOM_TEMPLATES:
        return _CUSTOM_TEMPLATES[t_id]
    return DEFAULT_TEMPLATES.get(t_id)


def register_custom_template(
    template_id: str,
    title: str,
    instruction: str,
    category: str = "custom"
) -> PromptTemplate:
    """Registers a user-defined prompt template."""
    t_id = template_id.lower().strip()
    tmpl = PromptTemplate(id=t_id, title=title, instruction=instruction, category=category)
    _CUSTOM_TEMPLATES[t_id] = tmpl
    return tmpl


def format_prompt_header(
    template_id: str,
    target_repo: Optional[str] = None,
    extra_instructions: Optional[str] = None
) -> str:
    """
    Renders the formatted Markdown prompt block for prepend to export manifests.
    """
    tmpl = get_template(template_id)
    if not tmpl:
        return ""

    lines = [
        f"> [!IMPORTANT] AI Assistant Task: {tmpl.title}",
        f"> {tmpl.instruction}"
    ]

    if target_repo:
        lines.append(f"> **Target Codebase**: `{target_repo}`")
    if extra_instructions:
        lines.append(f"> **Additional Instructions**: {extra_instructions.strip()}")

    lines.append("")
    return "\n".join(lines)


def prepend_template_to_markdown(
    markdown_text: str,
    template_id: str,
    target_repo: Optional[str] = None,
    extra_instructions: Optional[str] = None
) -> str:
    """
    Prepends the prompt template banner before the first heading of a Markdown manifest.
    """
    header = format_prompt_header(template_id, target_repo, extra_instructions)
    if not header:
        return markdown_text

    return f"{header}\n{markdown_text}"
