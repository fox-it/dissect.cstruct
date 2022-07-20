from __future__ import annotations

import struct
from typing import BinaryIO, List, TYPE_CHECKING

from dissect.cstruct.types import RawType

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class PackedType(RawType):
    """Implements a packed type that uses Python struct packing characters."""

    def __init__(self, cstruct: cstruct, name: str, size: int, packchar: str, alignment: int = None):
        super().__init__(cstruct, name, size, alignment)
        self.packchar = packchar

    def _read(self, stream: BinaryIO) -> int:
        return self._read_array(stream, 1)[0]

    def _read_array(self, stream: BinaryIO, count: int) -> List[int]:
        length = self.size * count
        data = stream.read(length)
        fmt = self.cstruct.endian + str(count) + self.packchar

        if len(data) != length:
            raise EOFError(f"Read {len(data)} bytes, but expected {length}")

        return list(struct.unpack(fmt, data))

    def _read_0(self, stream: BinaryIO) -> List[int]:
        byte_array = []
        while True:
            bytes_stream = stream.read(self.size)
            unpacked_struct = struct.unpack(self.cstruct.endian + self.packchar, bytes_stream)[0]

            if unpacked_struct == 0:
                break

            byte_array.append(unpacked_struct)

        return byte_array

    def _write(self, stream: BinaryIO, data: int) -> int:
        return self._write_array(stream, [data])

    def _write_array(self, stream: BinaryIO, data: List[int]) -> int:
        fmt = self.cstruct.endian + str(len(data)) + self.packchar
        return stream.write(struct.pack(fmt, *data))

    def _write_0(self, stream: BinaryIO, data: List[int]) -> int:
        return self._write_array(stream, data + [0])

    def default(self) -> int:
        return 0

    def default_array(self, count: int) -> List[int]:
        return [0] * count
