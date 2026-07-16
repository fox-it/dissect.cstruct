from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO

from dissect.cstruct.types.base import BaseType
from dissect.cstruct.util import ENDIANNESS_TO_BYTEORDER_MAP

if TYPE_CHECKING:
    from typing_extensions import Self

    from dissect.cstruct.cstruct import Endianness


class Int(int, BaseType):
    """Integer type that can span an arbitrary amount of bytes."""

    signed: bool

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Self:
        data = stream.read(cls.__size__)

        if len(data) != cls.__size__:
            raise EOFError(f"Read {len(data)} bytes, but expected {cls.__size__}")

        return cls.from_bytes(data, ENDIANNESS_TO_BYTEORDER_MAP[endian], signed=cls.signed)

    @classmethod
    def _read_0(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Self:
        result = []

        while True:
            if (value := cls._read(stream, context=context, endian=endian)) == 0:
                break

            result.append(value)

        return result

    @classmethod
    def _write(cls, stream: BinaryIO, data: int, *, endian: Endianness) -> int:
        return stream.write(data.to_bytes(cls.__size__, ENDIANNESS_TO_BYTEORDER_MAP[endian], signed=cls.signed))
