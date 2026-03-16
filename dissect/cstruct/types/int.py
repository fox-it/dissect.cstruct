from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO

from dissect.cstruct.types.base import BaseType
from dissect.cstruct.utils import ENDIANNESS_TO_BYTEORDER_MAP

if TYPE_CHECKING:
    from typing_extensions import Self

    from dissect.cstruct.cstruct import Endianness


class Int(int, BaseType):
    """Integer type that can span an arbitrary amount of bytes."""

    signed: bool

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness, **kwargs) -> Self:
        data = stream.read(cls.size)

        if len(data) != cls.size:
            raise EOFError(f"Read {len(data)} bytes, but expected {cls.size}")

        return cls.from_bytes(data, ENDIANNESS_TO_BYTEORDER_MAP[endian], signed=cls.signed)

    @classmethod
    def _read_0(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness, **kwargs) -> Self:
        result = []

        while True:
            if (value := cls._read(stream, context=context, endian=endian, **kwargs)) == 0:
                break

            result.append(value)

        return result

    @classmethod
    def _write(cls, stream: BinaryIO, data: int, *, endian: Endianness, **kwargs) -> int:
        return stream.write(data.to_bytes(cls.size, ENDIANNESS_TO_BYTEORDER_MAP[endian], signed=cls.signed))
