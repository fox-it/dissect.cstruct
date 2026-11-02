from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar

from dissect.cstruct.exception import ArraySizeError
from dissect.cstruct.types.base import EOF, BaseArray, BaseType, _is_seekable, _read_null_terminated

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import Endianness


class WcharArray(str, BaseArray):
    """Wide-character array type for reading and writing UTF-16 strings."""

    __slots__ = ()

    @classmethod
    def __default__(cls) -> WcharArray:
        return type.__call__(cls, "\x00" * (0 if cls.__dynamic__ or cls.__null_terminated__ else cls.__num_entries__))

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> WcharArray:
        return type.__call__(cls, super()._read(stream, context=context, endian=endian))

    @classmethod
    def _write(cls, stream: BinaryIO, data: str, *, endian: Endianness) -> int:
        if cls.__null_terminated__:
            data += "\x00"

        if not cls.__dynamic__ and (remaining := cls.__num_entries__ - (actual_size := len(data))):
            if remaining < 0:
                raise ArraySizeError(f"Expected static array size {cls.__num_entries__}, got {actual_size} instead.")
            data += "\x00" * remaining

        return stream.write(data.encode(Wchar.__encoding_map__[endian]))


class Wchar(str, BaseType):
    """Wide-character type for reading and writing UTF-16 characters."""

    __ArrayType__ = WcharArray

    __slots__ = ()
    __encoding_map__: ClassVar[dict[Endianness, str]] = {
        "@": f"utf-16-{sys.byteorder[0]}e",
        "=": f"utf-16-{sys.byteorder[0]}e",
        "<": "utf-16-le",
        ">": "utf-16-be",
        "!": "utf-16-be",
    }

    @classmethod
    def __default__(cls) -> Wchar:
        return type.__call__(cls, "\x00")

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Wchar:
        return cls._read_array(stream, 1, context=context, endian=endian)

    @classmethod
    def _read_array(
        cls, stream: BinaryIO, count: int, *, context: dict[str, Any] | None = None, endian: Endianness
    ) -> Wchar:
        if count == 0:
            return type.__call__(cls, "")

        if count != EOF:
            count *= 2

        data = stream.read(-1 if count == EOF else count)
        if count != EOF and len(data) != count:
            raise EOFError(f"Read {len(data)} bytes, but expected {count}")

        return type.__call__(cls, str(data, cls.__encoding_map__[endian]))

    @classmethod
    def _read_0(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Wchar:
        if _is_seekable(stream):
            return type.__call__(cls, _read_null_terminated(stream, 2).decode(cls.__encoding_map__[endian]))

        buf = []
        while True:
            point = stream.read(2)
            if (bytes_read := len(point)) != 2:
                raise EOFError(f"Read {bytes_read} bytes, but expected 2")

            if point == b"\x00\x00":
                break

            buf.append(point)

        return type.__call__(cls, b"".join(buf).decode(cls.__encoding_map__[endian]))

    @classmethod
    def _write(cls, stream: BinaryIO, data: str, *, endian: Endianness) -> int:
        return stream.write(data.encode(cls.__encoding_map__[endian]))
