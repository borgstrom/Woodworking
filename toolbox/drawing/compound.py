from collections.abc import Sequence
from fnmatch import fnmatchcase

from build123d import Color, Compound, Draft

from toolbox.drawing.cutlist import CutListPage
from toolbox.drawing.page import DrawingOrientation, Frame
from toolbox.drawing.technical import DrawingAnnotation, TechnicalDrawing


class DrawingCompound(Compound):
    drafting_options: Draft

    annotations: dict[DrawingOrientation, Sequence[DrawingAnnotation]]

    # Fill colors for direct children, by fnmatch pattern on their label.
    # The last matching pattern wins, and children that don't match aren't filled.
    fill_colors: dict[str, Color] = {}

    @property
    def drawing_title(self) -> str:
        if self.__doc__:
            return self.__doc__.strip()
        return "Add a docstring to " + self.__class__.__name__

    def technical_drawing(self) -> TechnicalDrawing:
        return TechnicalDrawing.for_object(
            obj=self,
            page_frame=Frame(
                title=self.drawing_title,
                drafting_options=self.drafting_options,
            ),
        )

    def cutlist(self) -> CutListPage:
        return CutListPage.for_object(
            obj=self,
            page_frame=Frame(
                title=f"{self.drawing_title} — Cut List",
                drafting_options=self.drafting_options,
            ),
        )

    def fill_color(self, label: str) -> Color | None:
        color = None
        for pattern, pattern_color in self.fill_colors.items():
            if fnmatchcase(label, pattern):
                color = pattern_color
        return color

    def annotate(self, annotation: DrawingAnnotation):
        pass
