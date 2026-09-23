from dataclasses import dataclass, field
from enum import Enum
import inspect
from math import gcd
from pathlib import Path
from typing import Sequence

from build123d import (
    IN,
    MM,
    Align,
    BoundBox,
    Color,
    Compound,
    Draft,
    Edge,
    ExportSVG,
    Face,
    FontStyle,
    GeomType,
    NumberDisplay,
    PageSize,
    Plane,
    Pos,
    Sketch,
    TechnicalDrawing as B123TechnicalDrawing,
    Text,
    Unit,
    Vector,
    Wire,
    trace,
)
from build123d.topology import Shape, ShapeList

# Width of the frame's border line, which is centered on the frame
BORDER_WIDTH = 0.05 * IN

DEFAULT_MARGIN = 0.25 * IN
DEFAULT_TITLE_FONT_SIZE = 0.5 * IN
DEFAULT_PAGE_SIZE = PageSize.LETTER


class DrawingOrientation(Enum):
    Front = (0, -100, 0)
    Side = (100, 0, 0)
    Isometric = (-100, -100, 100)


class DrawingView:
    """
    The 2D coordinate system of a projected view.

    project_to_viewport places its output in the camera's coordinate system, which is
    the plane built here: origin at the viewport origin, normal pointing back at the
    viewer, and Y along the viewport up direction. Mapping model points through this
    plane lands them on the projected edges.
    """

    up = Vector(0, 0, 1)
    look_at = Vector(0, 0, 0)

    def __init__(self, orientation: DrawingOrientation):
        self.orientation = orientation
        origin = Vector(orientation.value)
        normal = (origin - self.look_at).normalized()
        self.plane = Plane(origin=origin, x_dir=self.up.cross(normal), z_dir=normal)

    def project(self, shape: Compound) -> tuple[ShapeList[Edge], ShapeList[Edge]]:
        return shape.project_to_viewport(
            self.orientation.value, self.up, look_at=self.look_at
        )

    def to_2d(self, point: Vector) -> Vector:
        relative = point - self.plane.origin
        return Vector(relative.dot(self.plane.x_dir), relative.dot(self.plane.y_dir))

    def bounding_box_2d(self, shape: Shape) -> BoundBox:
        """The 2D bounding box of a shape's 3D bounding box corners in this view"""
        bbox = shape.bounding_box()
        corners = [
            self.to_2d(Vector(x, y, z))
            for x in (bbox.min.X, bbox.max.X)
            for y in (bbox.min.Y, bbox.max.Y)
            for z in (bbox.min.Z, bbox.max.Z)
        ]
        return Wire.make_polygon(corners).bounding_box()

    def silhouette(self, part: Shape) -> Sketch:
        """The part's outline in this view, as a filled 2D shape"""
        faces = []
        for face in part.faces():
            if face.geom_type != GeomType.PLANE:
                raise NotImplementedError(
                    f"Can't fill {part.label!r}, it has a non-planar face"
                )
            if abs(face.normal_at().dot(self.plane.z_dir)) < 1e-6:
                continue  # Seen edge-on, so it covers no area
            points = [
                self.to_2d(edge.position_at(0))
                for edge in face.outer_wire().order_edges()
            ]
            faces.append(Face(Wire.make_polygon(points)))
        if len(faces) > 1:
            faces = faces[0].fuse(*faces[1:]).clean().faces()
        # The polygons' winding depends on the part's face, so normalize the normals.
        # The CAD viewer shades faces by their normal, so mixed normals look different.
        return Sketch([face if face.normal_at().Z > 0 else -face for face in faces])


@dataclass
class Frame:
    """
    The border and title of a landscape page, centered on the origin.
    """

    title: str
    drafting_options: Draft
    page_size: PageSize = DEFAULT_PAGE_SIZE
    page_margin: float = DEFAULT_MARGIN
    title_font_size: float = DEFAULT_TITLE_FONT_SIZE

    # Auto generated attributes.
    region: BoundBox = field(init=False)
    shapes: list[Shape] = field(init=False)

    def __post_init__(self) -> None:
        page_w, page_h = B123TechnicalDrawing.page_sizes[self.page_size]
        frame_width = page_w - 2 * self.page_margin
        frame_height = page_h - 2 * self.page_margin
        frame_left = -frame_width / 2
        frame_bottom = -frame_height / 2

        frame_wire = Wire.make_polygon(
            [
                (-frame_width / 2, frame_height / 2),
                (frame_width / 2, frame_height / 2),
                (frame_width / 2, -frame_height / 2),
                (-frame_width / 2, -frame_height / 2),
            ],
        )
        border = trace(frame_wire, BORDER_WIDTH)

        # Title: centered at the top of the frame, bold, and underlined.
        # FontStyle has no underline, so the underline is a separate traced line
        # just below the text's bounding box (which includes any descenders).
        title_text = Pos(0, frame_height / 2 - self.title_font_size) * Text(
            self.title,
            font_size=self.title_font_size,
            font=self.drafting_options.font,
            font_style=FontStyle.BOLD,
            align=(Align.CENTER, Align.MAX),
        )
        title_bbox = title_text.bounding_box()
        title_underline_y = title_bbox.min.Y - self.title_font_size / 8
        title_underline = trace(
            Edge.make_line(
                (title_bbox.min.X, title_underline_y),
                (title_bbox.max.X, title_underline_y),
            ),
            self.drafting_options.line_width,
        )

        self.region = Wire.make_polygon(
            [
                (frame_left, frame_bottom),
                (frame_left + frame_width, title_underline_y),
            ]
        ).bounding_box()

        self.shapes = [border, title_text, title_underline]


class Page(Compound):
    """
    A printable page of shapes, laid out at full size in page units, that exports to
    an SVG the size of the page.
    """

    svg_path: Path

    def __init__(
        self,
        children: list[Shape],
        svg_path: Path,
    ):
        # Everything without a color of its own is black, in both the CAD viewer and
        # the SVG. This is set on each child rather than on the page, because the
        # viewer applies a color on the object passed to show() to all of its
        # children.
        for child in children:
            if child.color is None:
                child.color = Color("black")

        super().__init__(children=children)
        self.svg_path = svg_path

    @classmethod
    def svg_path_for(cls, obj: object, with_suffix: str = ".svg") -> Path:
        return Path(inspect.getfile(type(obj))).with_suffix(with_suffix)

    def export_svg(self, margin: float = DEFAULT_MARGIN) -> Path:
        """
        Write the page to its SVG file. The file is the size of the page, so it
        prints at 100%.

        Returns the path written to.
        """
        # ExportSVG sizes the file to the shapes, and the outermost shape is the
        # border, which sticks out half its width past the frame. The margin makes up
        # the rest of the page. fit_to_stroke is off because it would add the line
        # weight (which is in mm) as inches.
        exporter = ExportSVG(
            unit=Unit.IN,
            scale=1 / IN,
            fit_to_stroke=False,
            margin=(margin - BORDER_WIDTH / 2) / IN,
        )
        # The children, not the page, so each keeps its own color
        exporter.add_shape(self.children)
        exporter.write(self.svg_path)
        return self.svg_path


def format_fraction(inches: float, precision: int) -> str:
    """
    Inches as a whole number and a reduced fraction, to the nearest 1/precision:
    32, 1 1/2, 3/4.

    Draft's own fractions write whole numbers as "32 0/1", and values that round up
    to the next whole number as "1/1", so they aren't used.
    """
    whole, numerator = divmod(round(inches * precision), precision)
    if numerator == 0:
        return str(whole)
    divisor = gcd(numerator, precision)
    fraction = f"{numerator // divisor}/{precision // divisor}"
    return fraction if whole == 0 else f"{whole} {fraction}"


def format_length(length: float, draft: Draft) -> str:
    """
    Format a length like Draft does, but without trailing zeros: 32", 3.5", 0.75".

    draft.decimal_precision is the most decimal places shown, and
    draft.fractional_precision the smallest fraction of an inch.
    """
    unit = Draft.unit_LUT[draft.is_metric] if draft.display_units else ""
    if draft.number_display == NumberDisplay.FRACTION and not draft.is_metric:
        return format_fraction(length / IN, draft.fractional_precision) + unit
    value = f"{length / (MM if draft.is_metric else IN):.{draft.decimal_precision}f}"
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value + unit


def place(
    shapes: Sequence[Shape], content: BoundBox, scale: float, center: Vector
) -> list[Shape]:
    """Scale shapes about the content's center, then move that center to center"""
    # Shape.scale defaults to scaling about the shape's own location, not the origin
    return [
        Pos(center) * (Pos(-content.center()) * shape).scale(scale, about=(0, 0, 0))
        for shape in shapes
    ]
