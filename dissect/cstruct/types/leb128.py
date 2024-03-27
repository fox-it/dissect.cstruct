from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO

from dissect.cstruct.types.base import RawType

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class LEB128(RawType):
    """Variable-length code compression to store an arbitrarily large integer in a small number of bytes.

    See https://en.wikipedia.org/wiki/LEB128 for more information and an explanation of the algorithm.
    """

    signed: bool

    def __init__(self, cstruct: cstruct, name: str, size: int, signed: bool, alignment: int = 1):
        self.signed = signed
        super().__init__(cstruct, name, size, alignment)

    def _read(self, stream: BinaryIO, context: dict[str, Any] = None) -> LEB128:
        result = 0
        shift = 0
        while True:
            b = stream.read(1)
            if b == b"":
                raise EOFError("EOF reached, while final LEB128 byte was not yet read")

            b = ord(b)
            result |= (b & 0x7F) << shift
            shift += 7
            if (b & 0x80) == 0:
                break

        if self.signed:
            if b & 0x40 != 0:
                result |= ~0 << shift

        return result

    def _read_0(self, stream: BinaryIO, context: dict[str, Any] = None) -> LEB128:
        result = []

        while True:
            if (value := self._read(stream, context)) == 0:
                break

            result.append(value)

        return result

    def _write(self, stream: BinaryIO, data: int) -> int:
        # only write negative numbers when in signed mode
        if data < 0 and not self.signed:
            raise ValueError("Attempt to encode a negative integer using unsigned LEB128 encoding")

        result = bytearray()
        while True:
            # low-order 7 bits of value
            byte = data & 0x7F
            data = data >> 7

            # function works similar for signed- and unsigned integers, except for the check when to stop
            # the encoding process.
            if (self.signed and (data == 0 and byte & 0x40 == 0) or (data == -1 and byte & 0x40 != 0)) or (
                not self.signed and data == 0
            ):
                result.append(byte)
                break

            # Set high-order bit of byte
            result.append(0x80 | byte)

        stream.write(result)
        return len(result)

    def _write_0(self, stream: BinaryIO, data: list[int]) -> int:
        return self._write_array(stream, data + [0])

    def default(self) -> int:
        return 0

    def default_array(self, count: int) -> list[int]:
        return [0] * count
