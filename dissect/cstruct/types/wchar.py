from __future__ import annotations

import sys
from io import BytesIO
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar

from dissect.cstruct.exception import EOFError, WriteError
from dissect.cstruct.types.base import EOF, BaseArray, BaseType, MetaType, _is_seekable, _read_null_terminated

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import Endianness


class WcharMetaType(MetaType):
    """Metaclass for wide-character and wide-character array types."""

    def __call__(cls, *args, **kwargs) -> Wchar | WcharArray:
        if len(args) == 1 and not kwargs:
            # Handle a few fast path cases
            obj = args[0]
            if (tp := type(obj)) is str:
                return type.__call__(cls, obj)

            if tp is bytes:
                return cls._read(BytesIO(obj), endian=cls.__cs__.endian)

            # Writing doesn't accept an int either, and str() would give its decimal digits
            if isinstance(obj, int):
                raise TypeError(f"Cannot create {cls.__name__} from an int")

        return MetaType.__call__(cls, *args, **kwargs)


class WcharArray(str, BaseArray, metaclass=WcharMetaType):
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

        buf = data.encode(Wchar.__encoding_map__[endian], "surrogatepass")

        # A surrogate pair is a single character that takes up two entries of the array
        if not cls.__dynamic__ and (remaining := cls.__num_entries__ - (actual_size := len(buf) // 2)):
            if remaining < 0:
                raise WriteError(f"Expected static array size {cls.__num_entries__}, got {actual_size} instead.")
            buf += b"\x00\x00" * remaining

        return stream.write(buf)


class Wchar(str, BaseType, metaclass=WcharMetaType):
    """Wide-character type for reading and writing UTF-16 characters."""

    __ArrayType__ = WcharArray

    __slots__ = ()
    # Decode with "surrogatepass" so lone surrogates are handled correctly
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
        return type.__call__(cls, cls._read_array(stream, 1, context=context, endian=endian))

    @classmethod
    def _read_array(
        cls, stream: BinaryIO, count: int, *, context: dict[str, Any] | None = None, endian: Endianness
    ) -> str:
        if count == 0:
            return ""

        if count == EOF:
            data = stream.read()
            if len(data) % 2:
                raise EOFError("Read 1 bytes, but expected 2")
        else:
            length = count * 2

            try:
                data = stream.read(length)
            except OverflowError:
                raise EOFError(f"Read 0 bytes, but expected {length}") from None

            if len(data) != length:
                raise EOFError(f"Read {len(data)} bytes, but expected {length}")

        return str(data, cls.__encoding_map__[endian], "surrogatepass")

    @classmethod
    def _read_0(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> str:
        if _is_seekable(stream):
            data = _read_null_terminated(stream, 2)
            return data.decode(cls.__encoding_map__[endian], "surrogatepass")

        buf = []
        while True:
            point = stream.read(2)
            if (bytes_read := len(point)) != 2:
                raise EOFError(f"Read {bytes_read} bytes, but expected 2")

            if point == b"\x00\x00":
                break

            buf.append(point)

        return b"".join(buf).decode(cls.__encoding_map__[endian], "surrogatepass")

    @classmethod
    def _write(cls, stream: BinaryIO, data: str, *, endian: Endianness) -> int:
        buf = data.encode(cls.__encoding_map__[endian], "surrogatepass")

        # A surrogate pair is a single character that doesn't fit in a single wchar
        if (actual_size := len(buf) // 2) > 1:
            raise WriteError(f"Expected a single character, got {actual_size} instead.")

        return stream.write(buf or b"\x00\x00")
