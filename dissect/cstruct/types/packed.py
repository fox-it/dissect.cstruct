from __future__ import annotations

from functools import lru_cache
from struct import Struct
from typing import TYPE_CHECKING, Any, BinaryIO, Generic, TypeVar

from dissect.cstruct.types.base import EOF, BaseType

if TYPE_CHECKING:
    from typing_extensions import Self

    from dissect.cstruct.cstruct import Endianness


@lru_cache(1024)
def _struct(endian: str, packchar: str) -> Struct:
    return Struct(f"{endian}{packchar}")


T = TypeVar("T", int, float)


class Packed(BaseType, Generic[T]):
    """Packed type for Python struct (un)packing."""

    packchar: str

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness, **kwargs) -> Self:
        return cls._read_array(stream, 1, context=context, endian=endian, **kwargs)[0]

    @classmethod
    def _read_array(
        cls, stream: BinaryIO, count: int, *, context: dict[str, Any] | None = None, endian: Endianness, **kwargs
    ) -> list[Self]:
        if count == EOF:
            data = stream.read()
            length = len(data)
            count = length // cls.size
        else:
            length = cls.size * count
            data = stream.read(length)

        fmt = _struct(endian, f"{count}{cls.packchar}")

        if len(data) != length:
            raise EOFError(f"Read {len(data)} bytes, but expected {length}")

        return [cls.__new__(cls, value) for value in fmt.unpack(data)]

    @classmethod
    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] | None = None, *, endian: Endianness) -> Self:
        result = []

        fmt = _struct(endian, cls.packchar)
        while True:
            data = stream.read(cls.size)

            if len(data) != cls.size:
                raise EOFError(f"Read {len(data)} bytes, but expected {cls.size}")

            if (value := fmt.unpack(data)[0]) == 0:
                break

            result.append(cls.__new__(cls, value))

        return result

    @classmethod
    def _write(cls, stream: BinaryIO, data: Packed[T], *, endian: Endianness, **kwargs) -> int:
        return stream.write(_struct(endian, cls.packchar).pack(data))

    @classmethod
    def _write_array(cls, stream: BinaryIO, data: list[Packed[T]], *, endian: Endianness, **kwargs) -> int:
        return stream.write(_struct(endian, f"{len(data)}{cls.packchar}").pack(*data))
