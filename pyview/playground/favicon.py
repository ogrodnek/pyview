"""Favicon generation utilities for PyView playground."""

from dataclasses import dataclass


@dataclass
class Favicon:
    """Configuration for auto-generated favicon."""

    bg_color: str = "#3b82f6"
    text_color: str = "#ffffff"


def generate_favicon_svg(
    text: str,
    bg_color: str = "#3b82f6",
    text_color: str = "#ffffff",
) -> str:
    """Generate a rounded square SVG favicon with initials.

    Args:
        text: Text to extract initials from (e.g., app title)
        bg_color: Background color (hex)
        text_color: Text color (hex)

    Returns:
        SVG string
    """
    words = text.strip().split()
    if len(words) >= 2:
        initials = (words[0][0] + words[1][0]).upper()
    else:
        initials = words[0][0].upper() if words else "A"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="15" fill="{bg_color}"/>
  <text x="50" y="50" font-family="sans-serif" font-size="52" font-weight="bold"
        fill="{text_color}" text-anchor="middle" dominant-baseline="central">{initials}</text>
</svg>'''
