from build123d import *
from bd_materials import wood, core

from toolbox.assembly import centers

POPLAR = wood.custom_wood(
    name="Hardwood_POPLAR",
    density=455,  # kg/m³
    family="maple",  # closest shipped grain texture
    modulus_of_elasticity=10.9,  # GPa, along grain
    modulus_of_rupture=70,  # MPa
    compressive_strength_parallel=38.2,  # MPa
    janka_hardness=2400,  # N, side hardness
    specific_heat_capacity=core.Range(1200, 1700),
    thermal_conductivity=core.Range(0.11, 0.16),
)


class PoplarBoard(BasePartObject):
    """
    A single board of S6S poplar wood.
    """

    MAX_LENGTH = 32 * IN
    MAX_WIDTH = 4 * IN
    MAX_THICKNESS = 0.75 * IN

    def __init__(
        self,
        length: float | None = None,
        width: float | None = None,
        thickness: float | None = None,
        rotation: RotationLike = (0, 0, 0),
        align: None | Align | tuple[Align, Align, Align] = (
            Align.CENTER,
            Align.CENTER,
            Align.CENTER,
        ),
    ):
        if length is not None:
            self.length = length
        if width is not None:
            self.width = width
        if thickness is not None:
            self.thickness = thickness

        assert self.length is not None, "Length must be specified"
        assert self.width is not None, "Width must be specified"
        assert self.thickness is not None, "Thickness must be specified"

        assert (
            self.length <= self.MAX_LENGTH
        ), f"Length {self.length} exceeds maximum {self.MAX_LENGTH}"
        assert (
            self.width <= self.MAX_WIDTH
        ), f"Width {self.width} exceeds maximum {self.MAX_WIDTH}"
        assert (
            self.thickness <= self.MAX_THICKNESS
        ), f"Thickness {self.thickness} exceeds maximum {self.MAX_THICKNESS}"

        box = Box(self.length, self.width, self.thickness)

        # RigidJoint("left", box, Location((0, -width / 2, 0)))
        # RigidJoint("right", box, Location((0, width / 2, 0)))
        # RigidJoint("top", box, Location((0, 0, -thickness / 2)))
        # RigidJoint("bottom", box, Location((0, 0, thickness / 2)))
        # Front/Back ends? I don't know why I'd ever connect boards at the ends...

        super().__init__(
            part=box,
            rotation=rotation,
            align=align,
        )
        self.material = POPLAR


class GluedBoardsWidth(Compound):
    length: float
    widths: list[float]
    thickness: float

    @property
    def width(self) -> float:
        return sum(self.widths)

    def __init__(self) -> None:
        assert len(self.widths) > 1, "You must provide at least two widths"

        boards: list[PoplarBoard] = []
        for i, (width, y) in enumerate(
            zip(self.widths, centers(self.widths, self.width)), start=1
        ):
            board = PoplarBoard(
                length=self.length,
                width=width,
                thickness=self.thickness,
            )
            board.label = f"board_{i}"
            board.move(Location((0, y, 0)))
            boards.append(board)

        super().__init__(children=boards)


class GluedBoardsThickness(Compound):
    length: float
    width: float
    thicknesses: list[float]

    @property
    def thickness(self) -> float:
        return sum(self.thicknesses)

    def __init__(self) -> None:
        assert len(self.thicknesses) > 1, "You must provide at least two thicknesses"

        boards: list[PoplarBoard] = []
        for i, (thickness, z) in enumerate(
            zip(self.thicknesses, centers(self.thicknesses, self.thickness)),
            start=1,
        ):
            board = PoplarBoard(
                length=self.length,
                width=self.width,
                thickness=thickness,
            )
            board.label = f"board_{i}"
            board.move(Location((0, 0, z)))
            boards.append(board)

        super().__init__(children=boards)
