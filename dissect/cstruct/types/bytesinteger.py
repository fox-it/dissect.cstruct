from __future__ import annotations

from typing import BinaryIO, List, TYPE_CHECKING

from dissect.cstruct.types import RawType
from dissect.cstruct.exceptions import ValueOutOfBounds

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class BytesInteger(RawType):
    """Implements an integer type that can span an arbitrary amount of bytes."""

    def __init__(self, cstruct: cstruct, name: str, size: int, signed: bool, alignment: int = None):
        self.signed = signed
        super().__init__(cstruct, name, size, alignment)

    @staticmethod
    def parse(buf: BinaryIO, size: int, count: int, signed: bool, endian: str) -> List[int]:
        nums = []

        for c in range(count):
            num = 0
            data = buf[c * size : (c + 1) * size]
            if endian == "<":  # little-endian (LE)
                data = b"".join(data[i : i + 1] for i in reversed(range(len(data))))

            ints = list(data)
            for i in ints:
                num = (num << 8) | i

            if signed and (num & (1 << (size * 8 - 1))):
                bias = 1 << (size * 8 - 1)
                num -= bias * 2

            nums.append(num)

        return nums

    @staticmethod
    def pack(data: List[int], size: int, endian: str, signed: bool) -> bytes:
        buf = []
        for i in data:
            bits = size * 8
            unsignedMin = 0
            unsignedMax = (2**bits) - 1
            signedMax = (2 ** (bits - 1)) - 1
            signedMin = -(2 ** (bits - 1))

            if signed and (i < signedMin or i > signedMax):
                raise ValueOutOfBounds
            elif not signed and (i < unsignedMin or i > unsignedMax):
                raise ValueOutOfBounds

            num = int(i)
            if num < 0:
                num += 1 << (size * 8)

            d = [b"\x00"] * size
            i = size - 1

            while i >= 0:
                b = num & 255
                d[i] = bytes((b,))
                num >>= 8
                i -= 1

            if endian == "<":
                d = b"".join(d[i : i + 1][0] for i in reversed(range(len(d))))
            else:
                d = b"".join(d)

            buf.append(d)

        return b"".join(buf)

    def _read(self, stream: BinaryIO) -> int:
        return self.parse(stream.read(self.size * 1), self.size, 1, self.signed, self.cstruct.endian)[0]

    def _read_array(self, stream: BinaryIO, count: int) -> List[int]:
        return self.parse(
            stream.read(self.size * count),
            self.size,
            count,
            self.signed,
            self.cstruct.endian,
        )

    def _read_0(self, stream: BinaryIO) -> List[int]:
        result = []

        while True:
            v = self._read(stream)
            if v == 0:
                break

            result.append(v)

        return result

    def _write(self, stream: BinaryIO, data: int) -> int:
        return stream.write(self.pack([data], self.size, self.cstruct.endian, self.signed))

    def _write_array(self, stream: BinaryIO, data: List[int]) -> int:
        return stream.write(self.pack(data, self.size, self.cstruct.endian, self.signed))

    def _write_0(self, stream: BinaryIO, data: List[int]) -> int:
        return self._write_array(stream, data + [0])

    def default(self) -> int:
        return 0

    def default_array(self, count: int) -> List[int]:
        return [0] * count
