from __future__ import annotations

from typing import Any, BinaryIO

from dissect.cstruct.types.base import BaseType


class Void(BaseType):
    """Void type."""

    def __bool__(self) -> bool:
        return False

    def __eq__(self, value: object) -> bool:
        return isinstance(value, Void)

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> Void:
        return cls.__new__(cls)

    @classmethod
    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> Void:
        return [cls.__new__(cls)]

    @classmethod
    def _write(cls, stream: BinaryIO, data: Void) -> int:
        return 0
