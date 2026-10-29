from __future__ import annotations

import warnings
from itertools import repeat
from typing import TYPE_CHECKING, Any, BinaryIO, Generic, TypeVar

from dissect.cstruct.types.base import EOF, BaseType, MetaType, _is_buffer_type
from dissect.cstruct.util import _struct, classproperty

if TYPE_CHECKING:
    from typing_extensions import Self

    from dissect.cstruct.cstruct import Endianness


T = TypeVar("T", int, float)


class PackedMetaType(MetaType):
    """Metaclass for packed types."""

    def __call__(cls, *args, **kwargs) -> Packed:
        if len(args) == 1 and not kwargs:
            # Handle a few fast path cases
            obj = args[0]
            if (tp := type(obj)) is bytes or tp is bytearray or (tp is memoryview and obj.c_contiguous):
                data = obj.cast("B") if tp is memoryview else obj
                if len(data) < cls.__size__:
                    raise EOFError(f"Read {len(data)} bytes, but expected {cls.__size__}")

                return cls.__new__(cls, _struct(cls.__cs__.endian, cls.__fmt__).unpack_from(data)[0])

            if hasattr(obj, "read") and not isinstance(obj, cls):
                return cls._read(obj, endian=cls.__cs__.endian)

            if not _is_buffer_type(obj):
                # E.g. initializing with a value
                return type.__call__(cls, obj)

        elif not args and not kwargs:
            # Default value
            return type.__call__(cls)

        return MetaType.__call__(cls, *args, **kwargs)


class Packed(BaseType, Generic[T], metaclass=PackedMetaType):
    """Packed type for Python struct (un)packing."""

    __fmt__: str

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Self:
        data = stream.read(cls.__size__)

        if len(data) != cls.__size__:
            raise EOFError(f"Read {len(data)} bytes, but expected {cls.__size__}")

        return cls.__new__(cls, _struct(endian, cls.__fmt__).unpack(data)[0])

    @classmethod
    def _read_array(
        cls, stream: BinaryIO, count: int, *, context: dict[str, Any] | None = None, endian: Endianness
    ) -> list[Self]:
        if count == EOF:
            data = stream.read()
            length = len(data)
            count = length // cls.__size__
        else:
            length = cls.__size__ * count
            data = stream.read(length)

        fmt = _struct(endian, f"{count}{cls.__fmt__}")

        if len(data) != length:
            raise EOFError(f"Read {len(data)} bytes, but expected {length}")

        return list(map(cls.__new__, repeat(cls), fmt.unpack(data)))

    @classmethod
    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] | None = None, *, endian: Endianness) -> Self:
        result = []

        fmt = _struct(endian, cls.__fmt__)
        while True:
            data = stream.read(cls.__size__)

            if len(data) != cls.__size__:
                raise EOFError(f"Read {len(data)} bytes, but expected {cls.__size__}")

            if (value := fmt.unpack(data)[0]) == 0:
                break

            result.append(cls.__new__(cls, value))

        return result

    @classmethod
    def _write(cls, stream: BinaryIO, data: Packed[T], *, endian: Endianness) -> int:
        return stream.write(_struct(endian, cls.__fmt__).pack(data))

    @classmethod
    def _write_array(cls, stream: BinaryIO, data: list[Packed[T]], *, endian: Endianness) -> int:
        return stream.write(_struct(endian, f"{len(data)}{cls.__fmt__}").pack(*data))

    @classproperty
    def packchar(cls) -> str:
        """Access the struct packing character of packed integer/float types."""
        warnings.warn(
            "The 'packchar' property is deprecated, use '__fmt__' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.__fmt__
