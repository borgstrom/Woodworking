from __future__ import annotations

import typing
from copy import replace
from enum import Enum

from build123d import (
    IN,
    Align,
    Arrow,
    BoundBox,
    Compound,
    Curve,
    Draft,
    Edge,
    Location,
    Pos,
    Rot,
    Sketch,
    Text,
    Vector,
)
from build123d.topology import Shape

from toolbox.drawing.page import (
    DrawingOrientation,
    DrawingView,
    Frame,
    Page,
    format_length,
    place,
)

if typing.TYPE_CHECKING:
    from toolbox.drawing.compound import DrawingCompound

VIEW_PADDING = 0.75 * IN


class FLOOR:
    """The bottom of the whole object, for measuring to with Between"""


class TechnicalDrawing(Page):
    """
    A page displaying a Compound object in front & side view.

    The page is shown in landscape orientation, with the title centered at the top.

    Below the title the front and side views are drawn at the same scale, as large as
    they and their annotations fit.
    """

    @classmethod
    def for_object(
        cls,
        obj: DrawingCompound,
        page_frame: Frame,
        view_padding: float | None = None,
    ) -> TechnicalDrawing:
        view_padding = view_padding or VIEW_PADDING

        # Below the title, the front & side views share a scale, and are sized and
        # placed to fit the space as large as possible
        views = [
            ViewContent(obj, orientation)
            for orientation in (DrawingOrientation.Front, DrawingOrientation.Side)
        ]
        scale, centers = best_fit(
            views, page_frame.region, view_padding, page_frame.drafting_options
        )

        view_shapes: list[Shape] = []
        for view, center in zip(views, centers):
            view_shapes.extend(place(view.shapes(), view.extent, scale, center))

        return cls(
            children=[*page_frame.shapes, *view_shapes],
            svg_path=cls.svg_path_for(obj),
        )


class ViewContent:
    """
    Everything drawn in one view, at full size in the view's 2D coordinates.
    """

    def __init__(self, obj: DrawingCompound, orientation: DrawingOrientation):
        self.obj = obj
        self.view = DrawingView(orientation)
        self.outline = self.view.project(obj)[0]
        self.geometry = Curve(self.outline).bounding_box()
        self.fills = visible_fills(obj, self.view)
        self.annotations: list[Shape] = []
        self.extent = self.geometry

    def annotate(self, draft: Draft, scale: float) -> None:
        """Build the annotations for a scale, and the view's extent including them"""
        view_draft = scaled_draft(draft, scale)
        self.annotations = [
            annotation.build(self.obj, self.view, view_draft, scale)
            for annotation in self.obj.annotations.get(self.view.orientation, [])
        ]
        self.extent = Compound([*self.outline, *self.annotations]).bounding_box()

    def overhang(self, scale: float) -> tuple[float, float, float, float]:
        """
        How far the annotations reach past the geometry on paper: left, right, top &
        bottom. Annotation sizes are set on paper, so this barely changes with scale.
        """
        geometry, extent = self.geometry, self.extent
        return (
            (geometry.min.X - extent.min.X) * scale,
            (extent.max.X - geometry.max.X) * scale,
            (extent.max.Y - geometry.max.Y) * scale,
            (geometry.min.Y - extent.min.Y) * scale,
        )

    def shapes(self) -> list[Shape]:
        # Fills come first so the outlines draw over them in the SVG
        return [*self.fills, *self.outline, *self.annotations]


class AcrossAxis(Enum):
    X = "X"
    Y = "Y"
    Z = "Z"


class DrawingPlacement(Enum):
    INSIDE = "INSIDE"
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


# The page direction of each placement outside a part
PLACEMENT_DIRECTIONS = {
    DrawingPlacement.ABOVE: Vector(0, 1),
    DrawingPlacement.BELOW: Vector(0, -1),
    DrawingPlacement.LEFT: Vector(-1, 0),
    DrawingPlacement.RIGHT: Vector(1, 0),
}


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

    label is an optional template for the text, where {} is the measurement.
    """

    # Distance between the part and the dimension line, on paper
    offset = 0.25 * IN

    def __init__(
        self,
        name: str,
        axis: AcrossAxis,
        place: DrawingPlacement = DrawingPlacement.INSIDE,
        label: str | None = None,
    ):
        self.name = name
        self.axis = axis
        self.place = place
        self.label = label

    def build(
        self, obj: Compound, view: DrawingView, draft: Draft, scale: float
    ) -> Shape:
        return outside_dimension(
            view.bounding_box_2d(find_child(obj, self.name)),
            is_horizontal(self.axis, view),
            self.place,
            self.offset / scale,
            draft,
            self.label,
        )


class Overall(DrawingAnnotation):
    """
    Dimension the whole object across its extent along a model axis.

    label is an optional template for the text, where {} is the measurement.
    """

    # Distance between the object and the dimension line, on paper. It's further out
    # than Across so the two don't collide when they're on the same side.
    offset = 0.5 * IN

    def __init__(
        self, axis: AcrossAxis, place: DrawingPlacement, label: str | None = None
    ):
        self.axis = axis
        self.place = place
        self.label = label

    def build(
        self, obj: Compound, view: DrawingView, draft: Draft, scale: float
    ) -> Shape:
        return outside_dimension(
            view.bounding_box_2d(obj),
            is_horizontal(self.axis, view),
            self.place,
            self.offset / scale,
            draft,
            self.label,
        )


class Side(Enum):
    """A side of a part, as seen on the page"""

    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"
    BOTTOM = "BOTTOM"

    @property
    def is_vertical(self) -> bool:
        """LEFT & RIGHT are vertical edges, so they're measured horizontally"""
        return self in (Side.LEFT, Side.RIGHT)

    @property
    def direction(self) -> Vector:
        """The page direction pointing out of the part from this side"""
        return {
            Side.LEFT: Vector(-1, 0),
            Side.RIGHT: Vector(1, 0),
            Side.TOP: Vector(0, 1),
            Side.BOTTOM: Vector(0, -1),
        }[self]

    def position(self, bbox: BoundBox) -> float:
        """Where this side of bbox is: an X for LEFT & RIGHT, a Y for TOP & BOTTOM"""
        return {
            Side.LEFT: bbox.min.X,
            Side.RIGHT: bbox.max.X,
            Side.TOP: bbox.max.Y,
            Side.BOTTOM: bbox.min.Y,
        }[self]


class Between(DrawingAnnotation):
    """
    Dimension the distance between a side of one part and a side of another, or the
    floor. e.g. the inside span between two legs.

    The dimension line runs a short distance out from the near side, and the
    measurement is written on that same side of the line.

    label is an optional template for the text, where {} is the measurement.
    """

    # Distance between the near side and the dimension line, on paper
    offset = 0.25 * IN

    def __init__(
        self,
        name: str,
        side: Side,
        to: str | type[FLOOR],
        to_side: Side | None = None,
        *,
        near: tuple[str, Side],
        label: str | None = None,
    ):
        if to is not FLOOR and to_side is None:
            raise ValueError("to_side is required, unless measuring to FLOOR")
        self.name = name
        self.side = side
        self.to = to
        self.to_side = to_side
        self.near = near
        self.label = label

    def build(
        self, obj: Compound, view: DrawingView, draft: Draft, scale: float
    ) -> Shape:
        if self.to is FLOOR:
            to_bbox, to_side = view.bounding_box_2d(obj), Side.BOTTOM
        else:
            assert self.to_side is not None
            to_bbox, to_side = (
                view.bounding_box_2d(find_child(obj, str(self.to))),
                self.to_side,
            )
        near_name, near_side = self.near

        if self.side.is_vertical != to_side.is_vertical:
            raise ValueError(
                f"Can't measure between {self.side.name} and {to_side.name} sides"
            )
        if near_side.is_vertical == self.side.is_vertical:
            valid = "TOP or BOTTOM" if self.side.is_vertical else "LEFT or RIGHT"
            raise ValueError(
                "near is the side the dimension line runs along, so measuring between "
                f"{self.side.name} and {to_side.name} sides needs a {valid} side, "
                f"not {near_side.name}"
            )

        start = self.side.position(view.bounding_box_2d(find_child(obj, self.name)))
        end = to_side.position(to_bbox)
        direction = near_side.direction
        line = near_side.position(view.bounding_box_2d(find_child(obj, near_name))) + (
            self.offset / scale
        ) * (direction.X + direction.Y)

        if self.side.is_vertical:
            start_point, end_point = Vector(start, line), Vector(end, line)
        else:
            start_point, end_point = Vector(line, start), Vector(line, end)
        return dimension(start_point, end_point, direction, draft, self.label)


def best_fit(
    views: list[ViewContent],
    region: BoundBox,
    spacing: float,
    draft: Draft,
) -> tuple[float, list[Vector]]:
    """
    Find the largest scale, shared by all views, that fits them in region with their
    annotations, and where each view's center goes.

    The views are laid out either in a row, standing on the same floor line, or in a
    column. Whichever allows the larger scale wins. Leftover space is shared evenly
    between the views and the region's edges.

    The annotations' size on paper depends slightly on the scale (e.g. short
    dimensions put their arrows outside), so the fit is repeated with the annotations
    rebuilt at each new scale until it settles.
    """
    width, height = region.size.X, region.size.Y
    count = len(views)

    def solve(overhangs: list[tuple[float, float, float, float]]) -> tuple[float, bool]:
        sizes = [(view.geometry.size.X, view.geometry.size.Y) for view in views]
        # Row: widths add up, and heights share the floor line
        max_bottom = max(bottom for _, _, _, bottom in overhangs)
        row = min(
            (width - (count + 1) * spacing - sum(l + r for l, r, _, _ in overhangs))
            / sum(w for w, _ in sizes),
            *(
                (height - 2 * spacing - max_bottom - top) / h
                for (_, h), (_, _, top, _) in zip(sizes, overhangs)
            ),
        )
        # Column: heights add up, and each view is centered across
        column = min(
            (height - (count + 1) * spacing - sum(t + b for _, _, t, b in overhangs))
            / sum(h for _, h in sizes),
            *(
                (width - 2 * spacing - left - right) / w
                for (w, _), (left, right, _, _) in zip(sizes, overhangs)
            ),
        )
        return (row, True) if row >= column else (column, False)

    # Start from the geometry alone, then refine with the annotations built to scale
    scale, _ = solve([(0.0, 0.0, 0.0, 0.0)] * count)
    best: tuple[float, bool] | None = None
    built_at = None
    for _ in range(10):
        for view in views:
            view.annotate(draft, scale)
        built_at = scale
        solved, in_row = solve([view.overhang(scale) for view in views])
        fits = solved >= scale * (1 - 1e-9)
        if fits and (best is None or scale > best[0]):
            best = (scale, in_row)
        if fits and solved <= scale * (1 + 1e-9):
            break
        scale = solved
    if best is None:
        raise RuntimeError("Couldn't fit the views and their annotations on the page")
    scale, in_row = best
    if built_at != scale:
        for view in views:
            view.annotate(draft, scale)

    # Place each view's full extent, including annotations
    overhangs = [view.overhang(scale) for view in views]
    sizes = [
        (
            view.geometry.size.X * scale + left + right,
            view.geometry.size.Y * scale + top + bottom,
        )
        for view, (left, right, top, bottom) in zip(views, overhangs)
    ]
    centers = []
    if in_row:
        gap = (width - sum(w for w, _ in sizes)) / (count + 1)
        max_bottom = max(bottom for _, _, _, bottom in overhangs)
        row_height = max_bottom + max(
            view.geometry.size.Y * scale + top
            for view, (_, _, top, _) in zip(views, overhangs)
        )
        floor = region.min.Y + (height - row_height) / 2 + max_bottom
        x = region.min.X
        for (w, h), (_, _, _, bottom) in zip(sizes, overhangs):
            x += gap
            centers.append(Vector(x + w / 2, floor - bottom + h / 2))
            x += w
    else:
        gap = (height - sum(h for _, h in sizes)) / (count + 1)
        y = region.max.Y
        for w, h in sizes:
            y -= gap
            centers.append(Vector(region.center().X, y - h / 2))
            y -= h
    return scale, centers


def scaled_draft(draft: Draft, scale: float) -> Draft:
    """The draft's sizes, which are on paper, as full size model units at this scale"""
    return replace(
        draft,
        font_size=draft.font_size / scale,
        arrow_length=draft.arrow_length / scale,
        line_width=draft.line_width / scale,
        pad_around_text=draft.pad_around_text / scale,
        extension_gap=draft.extension_gap / scale,
    )


def visible_fills(obj: DrawingCompound, view: DrawingView) -> list[Sketch]:
    """
    The filled parts of obj in this view, each clipped to what's visible.

    Parts are visited nearest first, and each part's fill has everything nearer to the
    viewer cut away. Parts without a fill color still hide the fills behind them.
    """
    parts = sorted(
        obj.children,
        key=lambda part: part.bounding_box().center().dot(view.plane.z_dir),
        reverse=True,
    )
    if all(obj.fill_color(part.label) is None for part in parts):
        return []

    fills = []
    covered: Sketch | None = None
    for part in parts:
        silhouette = view.silhouette(part)
        color = obj.fill_color(part.label)
        if color is not None:
            visible = silhouette if covered is None else silhouette - covered
            if visible.faces():
                visible.color = color
                fills.append(visible)
        covered = (
            silhouette if covered is None else Sketch((covered + silhouette).faces())
        )
    return fills


def label(
    text: str, at: Vector, side: Vector, draft: Draft, rotated: bool = False
) -> Shape:
    """
    Text placed next to the point at, towards side. The text's edge nearest the point
    is aligned to it, e.g. its bottom when side points up.

    Rotated text is turned 90 degrees to read from bottom to top.
    """
    text_shape = Text(
        text,
        font_size=draft.font_size,
        font=draft.font,
        font_style=draft.font_style,
        align=(Align.CENTER, Align.CENTER),
    )
    if rotated:
        text_shape = Rot(0, 0, 90) * text_shape

    # Align after rotating, using the rotated text's extent
    bbox = text_shape.bounding_box()

    def shift(direction: float, low: float, high: float) -> float:
        if direction > 0:
            return -low
        if direction < 0:
            return -high
        return -(low + high) / 2

    return (
        Pos(
            at
            + side.normalized() * draft.pad_around_text
            + Vector(
                shift(side.X, bbox.min.X, bbox.max.X),
                shift(side.Y, bbox.min.Y, bbox.max.Y),
            )
        )
        * text_shape
    )


def dimension(
    start: Vector,
    end: Vector,
    label_side: Vector,
    draft: Draft,
    text: str | None = None,
) -> Sketch:
    """
    A dimension from start to end: a line with an arrow head at each end, and the
    measurement written beside the line, towards label_side.

    text is an optional template for the label, where {} is replaced by the
    measurement, e.g. "2 × {}" gives 2 × 0.75".
    """
    length = (end - start).length
    middle = (start + end) / 2

    # Arrows run from the middle out to each end. When the dimension is too short
    # for both arrow heads, they're outside instead, pointing in at the ends.
    if length >= 2 * draft.arrow_length:
        shafts = [Edge.make_line(middle, tip) for tip in (start, end)]
    else:
        direction = (end - start).normalized()
        shafts = [
            Edge.make_line(start - direction * 2 * draft.arrow_length, start),
            Edge.make_line(end + direction * 2 * draft.arrow_length, end),
        ]
    arrows = [
        Arrow(
            draft.arrow_length,
            shaft,
            draft.line_width,
            head_at_start=False,
            head_type=draft.head_type,
        )
        for shaft in shafts
    ]

    # Text on a vertical dimension runs along the line
    direction = end - start
    rotated = abs(direction.Y) > abs(direction.X)
    measurement = format_length(length, draft)
    written = measurement if text is None else text.format(measurement)
    text_shape = label(written, middle, label_side, draft, rotated)
    return Sketch([face for shape in (*arrows, text_shape) for face in shape.faces()])


def outside_dimension(
    bbox: BoundBox,
    horizontal: bool,
    place: DrawingPlacement,
    offset: float,
    draft: Draft,
    text: str | None = None,
) -> Sketch:
    """
    Dimension bbox across its width (horizontal) or height, with the dimension line
    offset outside it on the place side. text is a label template, as for dimension.
    """
    direction = PLACEMENT_DIRECTIONS.get(place)
    # A width is dimensioned above or below, and a height to the left or right
    if direction is None or (direction.X != 0) == horizontal:
        raise NotImplementedError(
            f"{place.name} for a {'horizontal' if horizontal else 'vertical'} "
            "dimension"
        )
    if horizontal:
        y = (bbox.max.Y if direction.Y > 0 else bbox.min.Y) + direction.Y * offset
        start, end = Vector(bbox.min.X, y), Vector(bbox.max.X, y)
    else:
        x = (bbox.max.X if direction.X > 0 else bbox.min.X) + direction.X * offset
        start, end = Vector(x, bbox.min.Y), Vector(x, bbox.max.Y)
    return dimension(start, end, direction, draft, text)


def is_horizontal(axis: AcrossAxis, view: DrawingView) -> bool:
    """Whether the model axis runs horizontally (or else vertically) in the view"""
    axis_direction = Vector(**{a.value: int(a == axis) for a in AcrossAxis})
    if abs(axis_direction.dot(view.plane.x_dir)) > 1 - 1e-6:
        return True
    if abs(axis_direction.dot(view.plane.y_dir)) > 1 - 1e-6:
        return False
    raise ValueError(
        f"Axis {axis.value} is not parallel to the {view.orientation.name} view's page"
    )


def find_child(obj: Compound, path: str) -> Shape:
    """
    Find a labeled part by its path of labels, e.g. "top" or "top/board_2", placed
    where it is in obj.

    A child's location is relative to its parent (moving a Compound doesn't move its
    children objects), so every ancestor's location is applied to the part.
    """
    shape: Shape = obj
    location = Location()
    for name in path.split("/"):
        location = location * shape.location
        matches = [child for child in shape.children if child.label == name]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one child labeled {name!r} for {path!r}, "
                f"found {len(matches)}"
            )
        shape = matches[0]
    return location * shape
