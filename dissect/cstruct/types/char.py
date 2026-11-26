from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any, BinaryIO

from dissect.cstruct.exception import EOFError, WriteError
from dissect.cstruct.types.base import (
    _BUFFER_TYPES,
    EOF,
    BaseArray,
    BaseType,
    MetaType,
    _is_buffer_type,
    _is_seekable,
    _read_null_terminated,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from typing_extensions import Self

    from dissect.cstruct.cstruct import Endianness


class CharMetaType(MetaType):
    """Metaclass for character and character array types."""

    def __call__(cls, *args, **kwargs) -> Char | CharArray:
        if len(args) == 1 and not kwargs:
            # Handle a few fast path cases
            obj = args[0]
            if isinstance(obj, bytes):
                if len(obj) == (size := cls.__size__):
                    # E.g. char[4](b"abcd")
                    return bytes.__new__(cls, obj)

                # Take the data up to the static size
                if size is not None:
                    if len(obj) < size:
                        # E.g. char[4](b"ab")
                        raise EOFError(f"Read {len(obj)} bytes, but expected {size}")

                    # E.g. char[4](b"abcdef")
                    return bytes.__new__(cls, obj[:size])

            if isinstance(obj, list) and len(obj) == cls.__size__:
                # E.g. char[2]([1, 2])
                return bytes.__new__(cls, obj)

            if isinstance(obj, (int, list)):
                # E.g. char(0x41) or char[4]([1, 2])
                return cls.__new__(cls, obj)

            if type(obj) in _BUFFER_TYPES:
                # E.g. char[None](b"ab\x00") or char[4](bytearray(b"abcd"))
                return cls._read(BytesIO(obj), endian=cls.__cs__.endian)

            if hasattr(obj, "read") and not isinstance(obj, cls):
                # E.g. char[4](fh)
                return cls._read(obj, endian=cls.__cs__.endian)

            if not _is_buffer_type(obj):
                # E.g. char[4]((1, 2))
                return cls.__new__(cls, obj)

        elif not args and not kwargs:
            # Default value
            # E.g. char[4]()
            return cls.__default__()

        # Everything else
        # E.g. char[4](b"abcd", endian=">")
        return MetaType.__call__(cls, *args, **kwargs)

    def _normalize(cls, value: Any) -> Char | CharArray:
        if isinstance(value, _BUFFER_TYPES):
            # The bytes of a char field are its value, e.g. b"ab" is b"ab\x00\x00" for a char[4] field
            return cls.__new__(cls, value)
        return cls(value)


class CharArray(bytes, BaseArray, metaclass=CharMetaType):
    """Character array type for reading and writing byte strings."""

    def __new__(cls, value: bytes | bytearray | memoryview | Iterable[int]) -> Self:
        if isinstance(value, int):
            raise TypeError(f"Cannot create {cls.__name__} from {type(value).__name__}")

        if isinstance(value, str):
            raise TypeError(f"Cannot create {cls.__name__} from {type(value).__name__}, encode to bytes first")

        result = bytes.__new__(cls, value)

        if not cls.__dynamic__ and (remaining := cls.__num_entries__ - (actual_size := len(result))):
            if remaining < 0:
                raise ValueError(f"Expected static array size {cls.__num_entries__}, got {actual_size} instead.")
            result = bytes.__new__(cls, result + b"\x00" * remaining)

        return result

    def __bytes__(self) -> bytes:
        # A char array is a bytes object, so give its content without the null terminator, like bytes does.
        # Python 3.11 and newer use bytes.__bytes__ without this, but 3.10 would use BaseType.__bytes__.
        return bytes(memoryview(self))

    @classmethod
    def __default__(cls) -> Self:
        return bytes.__new__(cls, b"\x00" * (0 if cls.__dynamic__ or cls.__null_terminated__ else cls.__num_entries__))

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Self:
        return bytes.__new__(cls, super()._read(stream, context=context, endian=endian))

    @classmethod
    def _write(cls, stream: BinaryIO, data: bytes | bytearray | memoryview, *, endian: Endianness) -> int:
        # Convert other bytes-like data to bytes, so adding the null terminator and padding doesn't modify it in place
        if isinstance(data, (bytearray, memoryview)):
            data = bytes(data)
        elif not isinstance(data, bytes):
            raise TypeError(f"Expected bytes, got {type(data).__name__}")

        if cls.__null_terminated__:
            data += b"\x00"

        if not cls.__dynamic__ and (remaining := cls.__num_entries__ - (actual_size := len(data))):
            if remaining < 0:
                raise WriteError(f"Expected static array size {cls.__num_entries__}, got {actual_size} instead.")
            data += b"\x00" * remaining

        return stream.write(data)


class Char(bytes, BaseType, metaclass=CharMetaType):
    """Character type for reading and writing bytes."""

    __ArrayType__ = CharArray

    def __new__(cls, value: bytes | int | Iterable[int]) -> Self:
        # Convert an int to a single character
        if isinstance(value, int):
            return bytes.__new__(cls, (value,))

        if isinstance(value, str):
            raise TypeError(f"Cannot create {cls.__name__} from {type(value).__name__}, encode to bytes first")

        result = bytes.__new__(cls, value)

        if (actual_size := len(result)) > 1:
            raise ValueError(f"Expected a single character, got {actual_size} instead.")

        return result or cls.__default__()

    def __bytes__(self) -> bytes:
        return bytes(memoryview(self))

    @classmethod
    def __default__(cls) -> Self:
        return bytes.__new__(cls, b"\x00")

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Self:
        return bytes.__new__(cls, cls._read_array(stream, 1, context=context, endian=endian))

    @classmethod
    def _read_array(
        cls, stream: BinaryIO, count: int, *, context: dict[str, Any] | None = None, endian: Endianness
    ) -> bytes:
        if count == 0:
            return b""

        try:
            data = stream.read(-1 if count == EOF else count)
        except OverflowError:
            raise EOFError(f"Read 0 bytes, but expected {count}") from None

        if count != EOF and len(data) != count:
            raise EOFError(f"Read {len(data)} bytes, but expected {count}")

        return data

    @classmethod
    def _read_0(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> bytes:
        if _is_seekable(stream):
            return _read_null_terminated(stream, 1)

        buf = []
        while True:
            byte = stream.read(1)
            if byte == b"":
                raise EOFError("Read 0 bytes, but expected 1")

            if byte == b"\x00":
                break

            buf.append(byte)

        return b"".join(buf)

    @classmethod
    def _write(cls, stream: BinaryIO, data: bytes, *, endian: Endianness) -> int:
        if not isinstance(data, _BUFFER_TYPES):
            raise TypeError(f"Expected bytes, got {type(data).__name__}")

        if (actual_size := len(data)) > 1:
            raise WriteError(f"Expected a single character, got {actual_size} instead.")

        return stream.write(data or b"\x00")
