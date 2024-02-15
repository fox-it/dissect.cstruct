from __future__ import annotations

from typing import Any, BinaryIO

from dissect.cstruct.types.base import BaseType


class LEB128(int, BaseType):
    """Variable-length code compression to store an arbitrarily large integer in a small number of bytes.

    See https://en.wikipedia.org/wiki/LEB128 for more information and an explanation of the algorithm.
    """

    signed: bool

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> LEB128:
        result = 0
        shift = 0
        while True:
            b = stream.read(1)
            if b == b"":
                raise EOFError("EOF reached, while final LEB128 byte was not yet read.")

            b = ord(b)
            result |= (b & 0x7F) << shift
            shift += 7
            if (b & 0x80) == 0:
                break

        if cls.signed:
            if b & 0x40 != 0:
                result |= ~0 << shift

        return result

    @classmethod
    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] = None) -> LEB128:
        result = []

        while True:
            if (value := cls._read(stream, context)) == 0:
                break

            result.append(value)

        return result
