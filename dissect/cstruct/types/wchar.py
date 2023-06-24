from __future__ import annotations

import sys
from typing import Any, BinaryIO

from dissect.cstruct.types.base import ArrayMetaType, BaseType


class Wchar(str, BaseType):
    """Wide-character type for reading and writing UTF-16 characters."""

    __encoding_map__ = {
        "@": f"utf-16-{sys.byteorder[0]}e",
        "=": f"utf-16-{sys.byteorder[0]}e",
        "<": "utf-16-le",
        ">": "utf-16-be",
        "!": "utf-16-be",
    }

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Wchar:
        return cls._read_array(stream, 1, context)

    @classmethod
    def _read_array(cls, stream: BinaryIO, count: int, context: dict[str, Any] = None) -> Wchar:
        count *= 2
        if count == 0:
            return ""

        data = stream.read(count)
        if len(data) != count:
            raise EOFError(f"Read {len(data)} bytes, but expected {count}")

        return type.__call__(cls, data.decode(cls.__encoding_map__[cls.cs.endian]))

    @classmethod
    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Wchar:
        buf = []
        while True:
            point = stream.read(2)
            if len(point) != 2:
                raise EOFError("Read 0 bytes, but expected 2")

            if point == b"\x00\x00":
                break

            buf.append(point)

        return type.__call__(cls, b"".join(buf).decode(cls.__encoding_map__[cls.cs.endian]))

    @classmethod
    def _write(cls, stream: BinaryIO, data: str) -> int:
        return stream.write(data.encode(cls.__encoding_map__[cls.cs.endian]))


class WcharArray(str, BaseType, metaclass=ArrayMetaType):
    """Wide-character array type for reading and writing UTF-16 strings."""

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> WcharArray:
        return type.__call__(cls, ArrayMetaType._read(cls, stream, context))

    @classmethod
    def _write(cls, stream: BinaryIO, data: str) -> int:
        if cls.null_terminated:
            data += "\x00"
        return stream.write(data.encode(Wchar.__encoding_map__[cls.cs.endian]))