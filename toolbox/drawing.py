from collections.abc import Sequence
from dataclasses import replace
from enum import Enum

from build123d import (
    IN,
    Align,
    BoundBox,
    Color,
    Compound,
    Curve,
    Draft,
    Edge,
    ExtensionLine,
    FontStyle,
    PageSize,
    Plane,
    Pos,
    ShapeList,
    TechnicalDrawing,
    Text,
    Vector,
    Wire,
    trace,
)
from build123d.topology import Shape


class DrawingOrientation(Enum):
    Front = (0, -100, 0)
    Side = (100, 0, 0)
    Isometric = (-100, -100, 100)


class AcrossAxis(Enum):
    X = "X"
    Y = "Y"
    Z = "Z"


class DrawingPlacement(Enum):
    INSIDE = "INSIDE"
    ABOVE = "ABOVE"
    RIGHT = "RIGHT"


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


class DrawingAnnotation:
    def build(
        self, obj: Compound, view: DrawingView, draft: Draft, scale: float
    ) -> Shape:
        """
        Build the annotation in the view's full size 2D coordinates.

        The draft is already adjusted for the scale, so its sizes are in model units.
        The scale is provided for any other sizes that are specified on paper.
        """
        raise NotImplementedError


class Across(DrawingAnnotation):
    """
    Dimension a labeled part across its extent along a model axis.
    """

    # Distance between the part and the dimension line, on paper
    offset = 0.25 * IN

    def __init__(
        self,
        name: str,
        axis: AcrossAxis,
        place: DrawingPlacement = DrawingPlacement.INSIDE,
    ):
        self.name = name
        self.axis = axis
        self.place = place

    def build(
        self, obj: Compound, view: DrawingView, draft: Draft, scale: float
    ) -> Shape:
        matches = [child for child in obj.children if child.label == self.name]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one child labeled {self.name!r}, found {len(matches)}"
            )
        part = matches[0]

        # Which 2D direction does the model axis run in this view?
        axis_direction = Vector(**{a.value: int(a == self.axis) for a in AcrossAxis})
        if abs(axis_direction.dot(view.plane.x_dir)) > 1 - 1e-6:
            horizontal = True
        elif abs(axis_direction.dot(view.plane.y_dir)) > 1 - 1e-6:
            horizontal = False
        else:
            raise ValueError(
                f"Axis {self.axis.value} is not parallel to the "
                f"{view.orientation.name} view's page"
            )

        bbox = view.bounding_box_2d(part)
        offset = self.offset / scale
        match self.place, horizontal:
            case DrawingPlacement.ABOVE, True:
                border = Edge.make_line(
                    (bbox.min.X, bbox.max.Y), (bbox.max.X, bbox.max.Y)
                )
                return ExtensionLine(border, offset=(0, offset), draft=draft)
            case DrawingPlacement.RIGHT, False:
                border = Edge.make_line(
                    (bbox.max.X, bbox.min.Y), (bbox.max.X, bbox.max.Y)
                )
                return ExtensionLine(border, offset=(offset, 0), draft=draft)
            case _:
                raise NotImplementedError(
                    f"Across {self.place.name} for a "
                    f"{'horizontal' if horizontal else 'vertical'} axis"
                )


class Between(DrawingAnnotation):
    pass


class Overall(DrawingAnnotation):
    pass


def fit_scale(content: BoundBox, width: float, height: float, padding: float) -> float:
    """The scale that fits content into width x height, inside padding on all sides"""
    return min(
        (width - 2 * padding) / content.size.X,
        (height - 2 * padding) / content.size.Y,
    )


def place(
    shapes: Sequence[Shape], content: BoundBox, scale: float, center: Vector
) -> list[Shape]:
    """Scale shapes about the content's center, then move that center to center"""
    # Shape.scale defaults to scaling about the shape's own location, not the origin
    return [
        Pos(center) * (Pos(-content.center()) * shape).scale(scale, about=(0, 0, 0))
        for shape in shapes
    ]


class DrawingPage(Compound):
    """
    A page displaying a Compound object in front & side view.

    The page is shown in landscape orientation, with the title centered at the top.

    Below the title the page is divided 50, 50 for the front and side views.
    """

    def __init__(
        self,
        obj: DrawingCompound,
        title: str,
        title_font_size: float | None = None,
        page_size: PageSize | None = None,
        page_margin: float | None = None,
        view_padding: float | None = None,
        drafting_options: Draft | None = None,
    ):
        title_font_size = title_font_size or 0.25 * IN
        page_size = page_size or PageSize.LETTER
        page_margin = page_margin or 0.25 * IN
        view_padding = view_padding or 0.5 * IN
        drafting_options = drafting_options or Draft()

        page_w, page_h = TechnicalDrawing.page_sizes[page_size]
        frame_width = page_w - 2 * page_margin
        frame_height = page_h - 2 * page_margin
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
        border = trace(frame_wire, 0.05 * IN)

        # Title: centered at the top of the frame, bold, and underlined.
        # FontStyle has no underline, so the underline is a separate traced line
        # just below the text's bounding box (which includes any descenders).
        title_text = Pos(0, frame_height / 2 - title_font_size) * Text(
            title,
            font_size=title_font_size,
            font=drafting_options.font,
            font_style=FontStyle.BOLD,
            align=(Align.CENTER, Align.MAX),
        )
        title_bbox = title_text.bounding_box()
        title_underline_y = title_bbox.min.Y - title_font_size / 8
        title_underline = trace(
            Edge.make_line(
                (title_bbox.min.X, title_underline_y),
                (title_bbox.max.X, title_underline_y),
            ),
            drafting_options.line_width,
        )

        # Layout: below the title, two columns of 50% each for the front & side views
        view_width = frame_width * 0.5
        view_height = title_underline_y - frame_bottom
        view_center_y = frame_bottom + view_height / 2
        front_center = Vector(frame_left + view_width / 2, view_center_y)
        side_center = Vector(frame_left + view_width * 1.5, view_center_y)

        # Front & side views share a scale, so it must fit whichever is larger
        views = {
            orientation: DrawingView(orientation)
            for orientation in (DrawingOrientation.Front, DrawingOrientation.Side)
        }
        projections = {
            orientation: view.project(obj)[0] for orientation, view in views.items()
        }
        contents = {
            orientation: Curve(edges).bounding_box()
            for orientation, edges in projections.items()
        }
        view_scale = min(
            fit_scale(content, view_width, view_height, view_padding)
            for content in contents.values()
        )

        # The drafting options are sizes on paper, but annotations are built at full
        # size and then scaled with the view
        view_draft = replace(
            drafting_options,
            font_size=drafting_options.font_size / view_scale,
            arrow_length=drafting_options.arrow_length / view_scale,
            line_width=drafting_options.line_width / view_scale,
            pad_around_text=drafting_options.pad_around_text / view_scale,
            extension_gap=drafting_options.extension_gap / view_scale,
        )

        view_shapes: list[Shape] = []
        for orientation, center in (
            (DrawingOrientation.Front, front_center),
            (DrawingOrientation.Side, side_center),
        ):
            annotations = [
                annotation.build(obj, views[orientation], view_draft, view_scale)
                for annotation in obj.annotations.get(orientation, [])
            ]
            view_shapes.extend(
                place(
                    [*projections[orientation], *annotations],
                    contents[orientation],
                    view_scale,
                    center,
                )
            )

        super().__init__(
            children=[
                border,
                title_text,
                title_underline,
            ]
            + view_shapes
        )

        # Children inherit this color, in both the CAD viewer and the SVG export
        self.color = Color("black")


class DrawingCompound(Compound):
    drafting_options: Draft

    annotations: dict[DrawingOrientation, list[DrawingAnnotation]]

    page_size: PageSize | None = None
    page_margin: float | None = None

    @property
    def drawing_title(self) -> str:
        if self.__doc__:
            return self.__doc__.strip()
        return "Add a docstring to " + self.__class__.__name__

    def drawing(self) -> DrawingPage:
        return DrawingPage(
            self,
            title=self.drawing_title,
            page_size=self.page_size,
            page_margin=self.page_margin,
            drafting_options=self.drafting_options,
        )

    def annotate(self, annotation: DrawingAnnotation):
        pass
