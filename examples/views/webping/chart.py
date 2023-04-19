from dataclasses import dataclass
from pyview.vendor.ibis import filters
from markupsafe import Markup


@dataclass
class Point:
    x: float
    y: float


@filters.register
def svg_chart(points: list[Point], width: int, height: int) -> Markup:
    def format_points():
        min_x = min([p.x for p in points])
        max_x = max([p.x for p in points])
        min_y = min([p.y for p in points])
        max_y = max([p.y for p in points])

        def point_svg(p: Point) -> str:
            scale_x = (max_x - min_x) if max_x - min_x > 0 else 1
            scale_y = (max_y - min_y) if max_y - min_y > 0 else 1
            x = (p.x - min_x) / scale_x * width
            y = (p.y - min_y) / scale_y * height

            y = height - y

            return f"{x},{y}"

        return " ".join([point_svg(p) for p in points])

    formatted_points = format_points() if len(points) > 0 else "0,0"

    return Markup(
        """
    <svg viewBox="0 0 {width} {height}" height="{height}" width="{width}">s
        <polyline points="{points}" stroke="#fb79a0" stroke-width="1" fill="none" />
    </svg>
    """
    ).format(width=width, height=height, points=formatted_points)
