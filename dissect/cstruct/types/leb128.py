from __future__ import annotations

from typing import Any, BinaryIO

from dissect.cstruct.types.base import BaseType


class LEB128(int, BaseType):
    """Variable-length code compression to store an arbitrarily large integer in a small number of bytes.
    See https://en.wikipedia.org/wiki/LEB128 for more information and an explanation of the algorithm."""

    signed: bool

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> LEB128:
        result = 0
        shift = 0
        while True:
            b = ord(stream.read(1))
            result |= (b & 0x7F) << shift
            shift += 7
            if (b & 0x80) == 0:
                break
        if cls.signed:
            if b & 0x40 != 0:
                result |= ~0 << shift
        return result
