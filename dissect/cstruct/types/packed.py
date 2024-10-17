from __future__ import annotations

from functools import lru_cache
from struct import Struct
from typing import Any, BinaryIO

from dissect.cstruct.types.base import EOF, BaseType


@lru_cache(1024)
def _struct(endian: str, packchar: str) -> Struct:
    return Struct(f"{endian}{packchar}")


class Packed(BaseType):
    """Packed type for Python struct (un)packing."""

    packchar: str

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> Packed:
        return cls._read_array(stream, 1, context)[0]

    @classmethod
    def _read_array(cls, stream: BinaryIO, count: int, context: dict[str, Any] | None = None) -> list[Packed]:
        if count == EOF:
            data = stream.read()
            length = len(data)
            count = length // cls.size
        else:
            length = cls.size * count
            data = stream.read(length)

        fmt = _struct(cls.cs.endian, f"{count}{cls.packchar}")

        if len(data) != length:
            raise EOFError(f"Read {len(data)} bytes, but expected {length}")

        return [cls.__new__(cls, value) for value in fmt.unpack(data)]

    @classmethod
    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> Packed:
        result = []

        fmt = _struct(cls.cs.endian, cls.packchar)
        while True:
            data = stream.read(cls.size)

            if len(data) != cls.size:
                raise EOFError(f"Read {len(data)} bytes, but expected {cls.size}")

            if (value := fmt.unpack(data)[0]) == 0:
                break

            result.append(cls.__new__(cls, value))

        return result

    @classmethod
    def _write(cls, stream: BinaryIO, data: Packed) -> int:
        return stream.write(_struct(cls.cs.endian, cls.packchar).pack(data))

    @classmethod
    def _write_array(cls, stream: BinaryIO, data: list[Packed]) -> int:
        return stream.write(_struct(cls.cs.endian, f"{len(data)}{cls.packchar}").pack(*data))
