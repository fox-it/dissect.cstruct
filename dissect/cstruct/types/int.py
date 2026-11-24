from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, BinaryIO

from dissect.cstruct.exception import EOFError
from dissect.cstruct.types.base import EOF, BaseType, MetaType
from dissect.cstruct.util import ENDIANNESS_TO_BYTEORDER_MAP, classproperty

if TYPE_CHECKING:
    from typing_extensions import Self

    from dissect.cstruct.cstruct import Endianness


class Int(int, BaseType):
    """Integer type that can span an arbitrary amount of bytes."""

    __signed__: bool

    @classmethod
    def _normalize(cls, value: int) -> Self:
        if not isinstance(value, int):
            raise TypeError(f"Cannot create {cls.__name__} from {type(value).__name__}")
        return type.__call__(cls, value)

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Self:
        data = stream.read(cls.__size__)

        if len(data) != cls.__size__:
            raise EOFError(f"Read {len(data)} bytes, but expected {cls.__size__}")

        return type.__call__(cls, int.from_bytes(data, ENDIANNESS_TO_BYTEORDER_MAP[endian], signed=cls.__signed__))

    @classmethod
    def _read_array(
        cls, stream: BinaryIO, count: int, *, context: dict[str, Any] | None = None, endian: Endianness
    ) -> list[Self]:
        if count == EOF:
            return MetaType._read_array(cls, stream, count, context=context, endian=endian)

        size = cls.__size__
        length = size * count

        try:
            data = stream.read(length)
        except OverflowError:
            raise EOFError(f"Read 0 bytes, but expected {length}") from None

        if len(data) != length:
            raise EOFError(f"Read {len(data) % size} bytes, but expected {size}")

        byteorder = ENDIANNESS_TO_BYTEORDER_MAP[endian]
        return [
            type.__call__(cls, int.from_bytes(data[i : i + size], byteorder, signed=cls.__signed__))
            for i in range(0, length, size)
        ]

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
        return stream.write(data.to_bytes(cls.__size__, ENDIANNESS_TO_BYTEORDER_MAP[endian], signed=cls.__signed__))

    @classproperty
    def signed(cls) -> bool:
        """Access whether this integer type is signed."""
        warnings.warn(
            "The 'signed' property is deprecated, use '__signed__' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.__signed__
