from typing import Any, BinaryIO

from dissect.cstruct.types import RawType


class VoidType(RawType):
    """Implements a void type."""

    def __init__(self):
        super().__init__(None, "void")

    def _read(self, stream: BinaryIO, context: dict[str, Any] = None) -> None:
        return None
