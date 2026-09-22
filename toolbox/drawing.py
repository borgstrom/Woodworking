from enum import Enum

from build123d import (
    IN,
    MM,
    Align,
    Compound,
    Draft,
    Edge,
    FontStyle,
    PageSize,
    Pos,
    TechnicalDrawing,
    Box,
    Text,
    Wire,
    trace,
)


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


class DrawingAnnotation:
    pass


class Across(DrawingAnnotation):
    def __init__(
        self,
        name: str,
        axis: AcrossAxis,
        place: DrawingPlacement = DrawingPlacement.INSIDE,
    ):
        pass


class Between(DrawingAnnotation):
    pass


class Overall(DrawingAnnotation):
    pass


class DrawingPage(Compound):
    """
    A page displaying a Compound object in front, side & iso view.

    The page is shown in landscape orientation.

    The page is divided 40, 40, 20 for front, side, and iso views respectively.

    Under the iso view metadata is displayed.
    """

    def __init__(
        self,
        *objects: DrawingCompound,
        title: str,
        title_font_size: float | None = None,
        page_size: PageSize | None = None,
        page_margin: float | None = None,
        drafting_options: Draft | None = None,
    ):
        if len(objects) != 1:
            raise ValueError("DrawingPage requires exactly one DrawingCompound object.")

        title_font_size = title_font_size or 0.25 * IN
        page_size = page_size or PageSize.LETTER
        page_margin = page_margin or 0.25 * IN
        drafting_options = drafting_options or Draft()

        page_h, page_w = TechnicalDrawing.page_sizes[page_size]
        frame_width = page_w - 2 * page_margin
        frame_height = page_h - 2 * page_margin

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

        visible_lines, hidden_lines = [], []

        # Front view
        v, h = objects[0].project_to_viewport(
            (0, -100, 0),
            (0, 0, 1),
            look_at=(0, 0, 0),
        )

        visible_lines.extend(v)
        hidden_lines.extend(h)

        super().__init__(
            children=[
                border,
                title_text,
                title_underline,
            ]
            + visible_lines
        )


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
