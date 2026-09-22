from collections.abc import Callable
from typing import Any


class classproperty[T]:
    """
    A read-only property that works on both the class and its instances.

    The getter always receives the class, so it can only use class attributes.
    """

    def __init__(self, fget: Callable[[Any], T]) -> None:
        self.fget = fget

    def __get__(self, obj: object, owner: type) -> T:
        return self.fget(owner)
