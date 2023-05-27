from __future__ import annotations

from enum import IntFlag
from typing import Union

from dissect.cstruct.types.base import BaseType
from dissect.cstruct.types.enum import EnumMetaType


class Flag(BaseType, IntFlag, metaclass=EnumMetaType):
    """Flag type supercharged with cstruct functionality.

    Flags are (mostly) compatible with the Python 3 standard library ``IntFlag`` with some notable differences:
        - Flag members are only considered equal if the flag class is the same

    Flags can be made using any integer type.

    Example:
        When using the default C-style parser, the following syntax is supported:

            flag <name> [: <type>] {
                <values>
            };

        For example, a flag that has A=1, B=4 and C=8 could be written like so:

            flag Test : uint16 {
                A, B=4, C
            };
    """

    def __repr__(self) -> str:
        result = super().__repr__()
        if not self.__class__.__name__:
            result = f"<{result[2:]}"
        return result

    def __str__(self) -> str:
        result = super().__str__()
        if not self.__class__.__name__:
            result = f"<{result[1:]}"
        return result

    def __eq__(self, other: Union[int, Flag]) -> bool:
        if isinstance(other, Flag) and other.__class__ is not self.__class__:
            return False

        # Python <= 3.10 compatibility
        if isinstance(other, Flag):
            other = other.value

        return self.value == other

    def __ne__(self, value: Union[int, Flag]) -> bool:
        return not self.__eq__(value)

    def __hash__(self) -> int:
        return hash((self.__class__, self.name, self.value))
