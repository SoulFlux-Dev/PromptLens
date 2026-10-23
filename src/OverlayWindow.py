"""OverlayWindow entry point and compatibility facade for PromptLens / PromptLens (SNIP-004).

Exposes:
- SnipOverlayState
- OverlayTheme
- CrosshairStyle
- OverlayConfig
- CrosshairConfig
- SnipSelection
- HoverTelemetry
- OverlayWindowSession
- OverlayWindow
- find_top_level_window_at_point
- create_dimmed_mask
- render_crosshairs
- render_telemetry_badge
- render_overlay_frame
- render_multi_monitor_overlays
- main
"""

from overlay_window import (
    SnipOverlayState,
    OverlayTheme,
    CrosshairStyle,
    OverlayConfig,
    CrosshairConfig,
    SnipSelection,
    HoverTelemetry,
    OverlayWindowSession,
    OverlayWindow,
    find_top_level_window_at_point,
    create_dimmed_mask,
    render_crosshairs,
    render_telemetry_badge,
    render_overlay_frame,
    render_multi_monitor_overlays,
    main,
)

__all__ = [
    "SnipOverlayState",
    "OverlayTheme",
    "CrosshairStyle",
    "OverlayConfig",
    "CrosshairConfig",
    "SnipSelection",
    "HoverTelemetry",
    "OverlayWindowSession",
    "OverlayWindow",
    "find_top_level_window_at_point",
    "create_dimmed_mask",
    "render_crosshairs",
    "render_telemetry_badge",
    "render_overlay_frame",
    "render_multi_monitor_overlays",
    "main",
]

if __name__ == "__main__":
    import sys
    sys.exit(main())
