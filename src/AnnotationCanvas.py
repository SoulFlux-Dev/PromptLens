"""AnnotationCanvas entry point and compatibility facade for PromptLens (SNIP-006).

Exposes:
- AnnotationItem
- AnnotationCanvas
- AnnotationCanvasView
- AnnotationReviewWindow
- main
"""

from __future__ import annotations

import sys
from annotation_canvas import (
    AnnotationItem,
    AnnotationCanvas,
    AnnotationCanvasView,
    AnnotationReviewWindow,
    main,
)

__all__ = [
    "AnnotationItem",
    "AnnotationCanvas",
    "AnnotationCanvasView",
    "AnnotationReviewWindow",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
