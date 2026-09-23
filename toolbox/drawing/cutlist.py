"""
A printable cut list, on a page that matches the drawing so the two can be printed
on either side of one sheet.
"""

from __future__ import annotations

import re
import typing
from collections import Counter
from dataclasses import dataclass, field

from build123d import (
    IN,
    Compound,
    Curve,
    Draft,
    Edge,
    FontStyle,
    Pos,
    Text,
    TextAlign,
    Vector,
    Wire,
    trace,
)
from build123d.topology import Shape

from toolbox.drawing.page import (
    Frame,
    Page,
    DrawingOrientation,
    DrawingView,
    format_length,
    place,
)

if typing.TYPE_CHECKING:
    from toolbox.drawing.compound import DrawingCompound


@dataclass(frozen=True)
class Dimensions:
    """
    A part's finished size, as its class defines it. It's used instead of the bounding
    box because the length is along the grain, whichever way the part is placed.
    """

    thickness: float
    width: float
    length: float

    @classmethod
    def of(cls, part: Shape) -> Dimensions:
        try:
            return cls(
                thickness=part.thickness,  # type: ignore[attr-defined]
                width=part.width,  # type: ignore[attr-defined]
                length=part.length,  # type: ignore[attr-defined]
            )
        except AttributeError:
            raise ValueError(
                f"{type(part).__name__} needs a length, width & thickness for the "
                "cut list"
            ) from None


@dataclass(frozen=True)
class BoardKind:
    """Boards that share a row on the cut list: the same class, size & material"""

    cls: type
    dimensions: Dimensions
    material: str


@dataclass
class CutListRow:
    code: str
    name: str
    quantity: int
    dimensions: Dimensions
    material: str
    depth: int  # 0 for a part, 1 for a board that's glued up into the part above it


def part_code(cls: type) -> str:
    """The capital letters of the class name, e.g. LA for LongApron"""
    return "".join(c for c in cls.__name__ if c.isupper())


def part_name(cls: type) -> str:
    """The class name as words, e.g. Long Apron for LongApron"""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cls.__name__)


def material_name(part: Shape) -> str:
    """
    The part's species, e.g. American Cherry. bd_materials names a material by its kind
    and species, e.g. Hardwood_AMERICAN_CHERRY.
    """
    material = getattr(part, "material", None)
    if material is None:
        return ""
    return material.name.split("_", 1)[-1].replace("_", " ").title()


def cut_list_rows(obj: Compound) -> list[CutListRow]:
    """
    A row for each kind of part in obj, in the order they first appear, followed by a
    row for each size of board it's glued up from.

    Parts are the same kind when they're the same class. Their boards are combined
    when they're the same class, size & material.
    """
    kinds: dict[type, list[Shape]] = {}
    for child in obj.children:
        kinds.setdefault(type(child), []).append(child)

    rows = []
    codes: dict[str, type] = {}
    for cls, parts in kinds.items():
        code = part_code(cls)
        if code in codes:
            raise ValueError(
                f"{cls.__name__} and {codes[code].__name__} have the same part code "
                f"{code!r}, rename one of them"
            )
        codes[code] = cls

        dimensions = Dimensions.of(parts[0])
        if any(Dimensions.of(part) != dimensions for part in parts[1:]):
            raise ValueError(f"The {cls.__name__} parts aren't all the same size")
        rows.append(
            CutListRow(
                code=code,
                name=part_name(cls),
                quantity=len(parts),
                dimensions=dimensions,
                material=material_name(parts[0]),
                depth=0,
            )
        )

        boards: Counter[BoardKind] = Counter()
        for part in parts:
            for board in part.children:
                if board.children:
                    raise NotImplementedError(
                        f"{type(board).__name__} in {cls.__name__} is made of parts, "
                        "only one level of glue-up is supported"
                    )
                boards[
                    BoardKind(
                        cls=type(board),
                        dimensions=Dimensions.of(board),
                        material=material_name(board),
                    )
                ] += 1
        for kind, quantity in boards.items():
            rows.append(
                CutListRow(
                    code=code,
                    name=part_name(kind.cls),
                    quantity=quantity,
                    dimensions=kind.dimensions,
                    material=kind.material,
                    depth=1,
                )
            )
    return rows


@dataclass
class Column:
    """A column of the table, and the text of each of its cells"""

    header: str
    cells: list[str]
    centered: bool = False
    # Whether a board's text is indented under its part
    indented: bool = False
    width: float = 0.0


# Space between the frame and the table, and around the isometric view
DEFAULT_PADDING = 0.25 * IN

# The isometric view's share of the width & height below the title
DEFAULT_VIEW_WIDTH = 0.4
DEFAULT_VIEW_HEIGHT = 0.5

# Check boxes wrap onto another line after this many
BOXES_PER_LINE = 10


@dataclass
class Table:
    """The table of rows, spanning left to right, below top"""

    rows: list[CutListRow]
    left: float
    right: float
    top: float
    drafting_options: Draft

    shapes: list[Shape] = field(init=False)

    def __post_init__(self):
        pad = self.drafting_options.pad_around_text
        indent = self.drafting_options.font_size
        box = self.drafting_options.font_size * 0.7
        box_gap = box / 3

        text_columns = [
            Column("Code", [row.code for row in self.rows]),
            Column("Part", [row.name for row in self.rows], indented=True),
            Column("Qty", [str(row.quantity) for row in self.rows], centered=True),
            Column(
                "T",
                [
                    format_length(row.dimensions.thickness, self.drafting_options)
                    for row in self.rows
                ],
                centered=True,
            ),
            Column(
                "W",
                [
                    format_length(row.dimensions.width, self.drafting_options)
                    for row in self.rows
                ],
                centered=True,
            ),
            Column(
                "L",
                [
                    format_length(row.dimensions.length, self.drafting_options)
                    for row in self.rows
                ],
                centered=True,
            ),
            Column("Mat'l", [row.material for row in self.rows]),
        ]
        check_columns = [Column("Rough", []), Column("Final", [])]
        notes = Column("Notes", [])
        columns = [*text_columns, *check_columns, notes]

        def text(value: str, centered: bool, bold: bool = False) -> Shape:
            # Aligned by the font's line rather than the glyphs, so all the text in a
            # row shares a baseline
            return Text(
                value,
                font_size=self.drafting_options.font_size,
                font=self.drafting_options.font,
                font_style=FontStyle.BOLD if bold else self.drafting_options.font_style,
                text_align=(
                    TextAlign.CENTER if centered else TextAlign.LEFT,
                    TextAlign.CENTER,
                ),
                align=None,
            )

        # The font's line is centered, which includes room for descenders and
        # accents, so capitals sit above the middle. This shift puts the middle of a
        # capital where the text is placed.
        capital = text("H", centered=False).bounding_box()
        center_capitals = Pos(0, -(capital.min.Y + capital.max.Y) / 2)

        def indent_for(column: Column, row: CutListRow) -> float:
            return indent if column.indented and row.depth else 0.0

        # The text is built first, to size the columns to fit it
        headers = [
            text(column.header, column.centered, bold=True) for column in columns
        ]
        cells = [
            [text(value, column.centered) for value in column.cells]
            for column in text_columns
        ]
        for column, header, column_cells in zip(text_columns, headers, cells):
            column.width = 2 * pad + max(
                header.bounding_box().size.X,
                *(
                    cell.bounding_box().size.X + indent_for(column, row)
                    for cell, row in zip(column_cells, self.rows)
                ),
            )
        most_boxes = min(max(row.quantity for row in self.rows), BOXES_PER_LINE)
        for column, header in zip(check_columns, headers[len(text_columns) :]):
            column.width = 2 * pad + max(
                header.bounding_box().size.X,
                most_boxes * box + (most_boxes - 1) * box_gap,
            )
        notes.width = (
            self.right - self.left - sum(column.width for column in columns[:-1])
        )
        if notes.width < headers[-1].bounding_box().size.X + 2 * pad:
            raise ValueError("The cut list table is too wide for the page")

        lines = [self.left]
        for column in columns:
            lines.append(lines[-1] + column.width)

        def x(i: int, row: CutListRow | None = None) -> float:
            """Where the text in column i goes, which is aligned by its text_align"""
            column = columns[i]
            if column.centered:
                return (lines[i] + lines[i + 1]) / 2
            return lines[i] + pad + (indent_for(column, row) if row else 0.0)

        text_height = self.drafting_options.font_size + 2 * pad
        self.shapes: list[Shape] = []

        y = self.top
        for i, header in enumerate(headers):
            self.shapes.append(
                Pos(x(i), y - text_height / 2) * center_capitals * header
            )
        row_lines = [y]
        y -= text_height

        # Rows are taller when their check boxes wrap onto more lines
        for r, row in enumerate(self.rows):
            box_lines = -(-row.quantity // BOXES_PER_LINE)
            boxes_height = box_lines * box + (box_lines - 1) * box_gap
            height = max(text_height, boxes_height + 2 * pad)
            middle = y - height / 2
            for i, column_cells in enumerate(cells):
                self.shapes.append(
                    Pos(x(i, row), middle) * center_capitals * column_cells[r]
                )
            for i in range(len(text_columns), len(text_columns) + len(check_columns)):
                self.shapes.extend(
                    self.check_boxes(
                        row.quantity,
                        Vector(lines[i] + pad, middle + boxes_height / 2),
                        box,
                        box_gap,
                        self.drafting_options.line_width,
                    )
                )
            row_lines.append(y)
            y -= height
        row_lines.append(y)

        # Grid lines, with a heavier line under the header
        for i, row_y in enumerate(row_lines):
            width = self.drafting_options.line_width * (2 if i == 1 else 1)
            self.shapes.append(
                trace(Edge.make_line((self.left, row_y), (self.right, row_y)), width)
            )
        for column_x in lines:
            self.shapes.append(
                trace(
                    Edge.make_line((column_x, row_lines[0]), (column_x, row_lines[-1])),
                    self.drafting_options.line_width,
                )
            )

    def check_boxes(
        self,
        count: int,
        top_left: Vector,
        box: float,
        gap: float,
        line_width: float,
    ) -> list[Shape]:
        """count empty boxes from top_left, in lines of boxes_per_line"""
        shapes: list[Shape] = []
        for n in range(count):
            line, column = divmod(n, BOXES_PER_LINE)
            x = top_left.X + column * (box + gap)
            y = top_left.Y - line * (box + gap)
            corners = [(x, y), (x + box, y), (x + box, y - box), (x, y - box)]
            shapes.append(trace(Wire.make_polygon(corners), line_width))
        return shapes


class CutListPage(Page):
    """
    A page listing the parts to cut for a Compound object, with an isometric view of
    it in the bottom right corner.

    The page matches the drawing's size, orientation, frame & title, so they can be
    printed on either side of one sheet. The table is at the top, and the space
    below it is left for notes.

    Each part has a row, with the boards it's glued up from indented below it. The
    Rough & Final columns have a box to check off for each piece, as it's laid out on
    the lumber and as it's cut to its finished size.
    """

    @classmethod
    def for_object(
        cls,
        obj: DrawingCompound,
        page_frame: Frame,
    ) -> CutListPage:
        region = page_frame.region
        table = Table(
            cut_list_rows(obj),
            region.min.X + DEFAULT_PADDING,
            region.max.X - DEFAULT_PADDING,
            region.max.Y - DEFAULT_PADDING,
            page_frame.drafting_options,
        )

        # The isometric view is as large as it fits in the bottom right corner
        isometric_region = Wire.make_polygon(
            [
                (region.max.X - region.size.X * DEFAULT_VIEW_WIDTH, region.min.Y),
                (region.max.X, region.min.Y + region.size.Y * DEFAULT_VIEW_HEIGHT),
            ]
        ).bounding_box()
        outline = DrawingView(DrawingOrientation.Isometric).project(obj)[0]
        extent = Curve(outline).bounding_box()
        scale = min(
            (isometric_region.size.X - 2 * DEFAULT_PADDING) / extent.size.X,
            (isometric_region.size.Y - 2 * DEFAULT_PADDING) / extent.size.Y,
        )
        isometric_view = place(outline, extent, scale, isometric_region.center())

        return cls(
            children=[*page_frame.shapes, *table.shapes, *isometric_view],
            svg_path=cls.svg_path_for(obj, with_suffix=".cutlist.svg"),
        )
