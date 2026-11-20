from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO

from dissect.cstruct.exception import EOFError, WriteError
from dissect.cstruct.types.base import EOF, BaseArray, BaseType, MetaType, _is_seekable, _read_null_terminated

if TYPE_CHECKING:
    from typing_extensions import Self

    from dissect.cstruct.cstruct import Endianness


class CharArrayMetaType(MetaType):
    """Metaclass for character array types."""

    def __call__(cls, *args, **kwargs) -> CharArray:
        if len(args) == 1 and not kwargs:
            # Handle a few fast path cases
            obj = args[0]
            if type(obj) is bytes and len(obj) == cls.__size__:
                return type.__call__(cls, obj)

            # Convert a string like writing does, instead of raising a TypeError
            if isinstance(obj, str):
                return type.__call__(cls, obj.encode("latin-1"))

            # Writing doesn't accept an int either, and bytes() would give that many null bytes
            if isinstance(obj, int):
                raise TypeError(f"Cannot create {cls.__name__} from an int")

        return MetaType.__call__(cls, *args, **kwargs)


class CharArray(bytes, BaseArray, metaclass=CharArrayMetaType):
    """Character array type for reading and writing byte strings."""

    def __bytes__(self) -> bytes:
        # A char array is a bytes object, so give its content without the null terminator, like bytes does.
        # Python 3.11 and newer use bytes.__bytes__ without this, but 3.10 would use BaseType.__bytes__.
        return bytes(memoryview(self))

    @classmethod
    def __default__(cls) -> Self:
        return type.__call__(cls, b"\x00" * (0 if cls.__dynamic__ or cls.__null_terminated__ else cls.__num_entries__))

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Self:
        return type.__call__(cls, super()._read(stream, context=context, endian=endian))

    @classmethod
    def _write(cls, stream: BinaryIO, data: bytes | bytearray | str | list[int], *, endian: Endianness) -> int:
        # Convert other bytes-like data to bytes, so adding the null terminator and padding doesn't modify it in place
        if isinstance(data, (list, bytearray, memoryview)):
            data = bytes(data)
        elif isinstance(data, str):
            data = data.encode("latin-1")

        if cls.__null_terminated__:
            data += b"\x00"

        if not cls.__dynamic__ and (remaining := cls.__num_entries__ - (actual_size := len(data))):
            if remaining < 0:
                raise WriteError(f"Expected static array size {cls.__num_entries__}, got {actual_size} instead.")
            data += b"\x00" * remaining

        return stream.write(data)


class CharMetaType(MetaType):
    """Metaclass for character types."""

    def __call__(cls, *args, **kwargs) -> Char:
        if len(args) == 1 and not kwargs:
            # Handle a few fast path cases
            obj = args[0]
            if type(obj) is bytes and len(obj) == cls.__size__:
                return type.__call__(cls, obj)

            # Convert an int or string like writing does. Otherwise, bytes() gives that many null bytes for an int,
            # and raises a TypeError for a string.
            if isinstance(obj, int):
                obj = chr(obj)

            if isinstance(obj, str):
                return type.__call__(cls, obj.encode("latin-1"))

        return MetaType.__call__(cls, *args, **kwargs)


class Char(bytes, BaseType, metaclass=CharMetaType):
    """Character type for reading and writing bytes."""

    __ArrayType__ = CharArray

    def __bytes__(self) -> bytes:
        return bytes(memoryview(self))

    @classmethod
    def __default__(cls) -> Self:
        return type.__call__(cls, b"\x00")

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Self:
        return type.__call__(cls, cls._read_array(stream, 1, context=context, endian=endian))

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
    def _write(cls, stream: BinaryIO, data: bytes | int | str, *, endian: Endianness) -> int:
        if isinstance(data, int):
            data = chr(data)

        if isinstance(data, str):
            data = data.encode("latin-1")

        if (actual_size := len(data)) > 1:
            raise WriteError(f"Expected a single character, got {actual_size} instead.")

        return stream.write(data or b"\x00")
