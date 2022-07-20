from __future__ import annotations

from typing import BinaryIO, TYPE_CHECKING

from dissect.cstruct.types import RawType

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class CharType(RawType):
    """Implements a character type that can properly handle strings."""

    def __init__(self, cstruct: cstruct):
        super().__init__(cstruct, "char", size=1, alignment=1)

    def _read(self, stream: BinaryIO) -> bytes:
        return stream.read(1)

    def _read_array(self, stream: BinaryIO, count: int) -> bytes:
        if count == 0:
            return b""

        return stream.read(count)

    def _read_0(self, stream: BinaryIO) -> bytes:
        byte_array = []
        while True:
            bytes_stream = stream.read(1)
            if bytes_stream == b"":
                raise EOFError()

            if bytes_stream == b"\x00":
                break

            byte_array.append(bytes_stream)

        return b"".join(byte_array)

    def _write(self, stream: BinaryIO, data: bytes) -> int:
        if isinstance(data, int):
            data = chr(data)

        if isinstance(data, str):
            data = data.encode("latin-1")

        return stream.write(data)

    def _write_array(self, stream: BinaryIO, data: bytes) -> int:
        return self._write(stream, data)

    def _write_0(self, stream: BinaryIO, data: bytes) -> int:
        return self._write(stream, data + b"\x00")

    def default(self) -> bytes:
        return b"\x00"

    def default_array(self, count: int) -> bytes:
        return b"\x00" * count
