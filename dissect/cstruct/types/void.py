from __future__ import annotations

from typing import Any, BinaryIO

from dissect.cstruct.types.base import BaseType


class Void(BaseType):
    """Void type."""

    def __bool__(self) -> bool:
        return False

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Void:
        return cls.__new__(cls)

    @classmethod
    def _write(cls, stream: BinaryIO, data: Void) -> int:
        return 0
