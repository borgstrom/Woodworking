import itertools
from copy import copy

from build123d import *

from toolbox.ocp_vscode import show_with_autoreload_in_vscode
from toolbox.wood import GluedBoardsWidth, GluedBoardsThickness, PoplarBoard


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
    length = sum(Top.widths) - (2 * Top.overhang) - (2 * sum(Leg.thicknesses))
    width = 3.5 * IN
    thickness = 0.75 * IN


class ShakerTable(Compound):
    def __init__(self) -> None:
        top = Pos(0, 0, Leg.length + Top.thickness / 2) * Top()
        top.label = "top"

        leg = Rotation(0, 90, 0) * Rotation(90, 0, 0) * Leg()

        dx = top.length / 2 - top.overhang - leg.thickness / 2
        dy = top.width / 2 - top.overhang - leg.width / 2

        legs = []
        for sx, sy in itertools.product((-1, 1), repeat=2):
            legN = Pos(sx * dx, sy * dy, leg.length / 2) * copy(leg)
            legN.label = f"leg_{'N' if sy > 0 else 'S'}{'E' if sx > 0 else 'W'}"
            legs.append(legN)

        aprons = []
        for Apron, name, x, y, y_rotation in (
            (LongApron, "N", 0, dy, 0),
            (LongApron, "S", 0, -dy, 0),
            (ShortApron, "E", dx, 0, 90),
            (ShortApron, "W", -dx, 0, 90),
        ):
            apron = (
                Pos(x, y, leg.length - Apron.width / 2)
                * Rotation(90, y_rotation, 0)
                * Apron()
            )
            apron.label = f"apron_{name}"
            aprons.append(apron)

        super().__init__(
            children=[
                top,
            ]
            + legs
            + aprons
        )


table = ShakerTable()
show_with_autoreload_in_vscode(table, names=["table"], render_joints=True)
