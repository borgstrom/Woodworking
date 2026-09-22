"""
This is a roughly 32"x16"x33" Shaker table built in 2026 as part of Woodworking1
"""

from build123d import IN, Compound, Pos, Rotation, Draft, Unit
from toolbox.drawing import (
    Across,
    AcrossAxis,
    DrawingCompound,
    DrawingOrientation,
    DrawingPlacement,
)

from toolbox.ocp_vscode import show_with_autoreload_in_vscode
from toolbox.wood import GluedBoardsThickness, GluedBoardsWidth, PoplarBoard


class Top(GluedBoardsWidth):
    length = 32 * IN
    widths = [4 * IN, 2 * IN, 4 * IN, 2 * IN, 4 * IN]
    thickness = 0.75 * IN

    overhang = 1.5 * IN


class Leg(GluedBoardsThickness):
    length = 32 * IN
    width = 1.5 * IN
    thicknesses = [0.75 * IN, 0.75 * IN]


class LongApron(PoplarBoard):
    length = Top.length - 2 * Top.overhang - 2 * Leg.width
    width = 3.5 * IN
    thickness = 0.75 * IN


class ShortApron(PoplarBoard):
    length = Top.width - (2 * Top.overhang) - (2 * Leg.thickness)
    width = 3.5 * IN
    thickness = 0.75 * IN


class ShakerTable(DrawingCompound):
    """
    Woodworking1 Shaker Table
    """

    drafting_options = Draft(
        font="Helvetica",
        unit=Unit.IN,
    )

    annotations = {
        DrawingOrientation.Front: [
            Across("top", AcrossAxis.X, DrawingPlacement.ABOVE),
        ],
    }

    def __init__(self) -> None:
        top = Pos(0, 0, Leg.length + Top.thickness / 2) * Top()
        top.label = "top"

        # Calculate the offsets for positioning the legs relative to the top
        # Since the design is symmetrical we only need one calculation
        # The permutations are just combinations of positive and negative offsets
        dx = Top.length / 2 - Top.overhang - Leg.thickness / 2
        dy = Top.width / 2 - Top.overhang - Leg.width / 2

        # Create the legs
        legs = []
        for name, x, y in (
            ("NE", dx, dy),
            ("NW", -dx, dy),
            ("SE", dx, -dy),
            ("SW", -dx, -dy),
        ):
            legN = (
                Pos(x, y, Leg.length / 2)
                # Legs are oriented about their length, so we need to stand them up
                * Rotation(0, 90, 0)
                * Rotation(90, 0, 0)
                * Leg()
            )
            legN.label = f"leg_{name}"
            legs.append(legN)

        # Create the aprons
        aprons = []
        for Apron, name, x, y, y_rotation in (
            (LongApron, "N", 0, dy, 0),
            (LongApron, "S", 0, -dy, 0),
            (ShortApron, "E", dx, 0, 90),
            (ShortApron, "W", -dx, 0, 90),
        ):
            apron = (
                Pos(x, y, Leg.length - Apron.width / 2)
                * Rotation(90, y_rotation, 0)
                * Apron()
            )
            apron.label = f"apron_{name}"
            aprons.append(apron)

        super().__init__(children=[top] + legs + aprons)


table = ShakerTable()
# show_with_autoreload_in_vscode(table, names=["table"], render_joints=True)
show_with_autoreload_in_vscode(table.drawing())
