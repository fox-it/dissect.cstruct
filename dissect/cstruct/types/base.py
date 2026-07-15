from __future__ import annotations

import functools
import warnings
from io import BytesIO
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar, TypeVar

from dissect.cstruct.exception import ArraySizeError
from dissect.cstruct.expression import Expression
from dissect.cstruct.util import classproperty, normalize_endianness

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Self

    from dissect.cstruct.cstruct import AllowedEndianness, Endianness, cstruct


EOF = -0xE0F  # Negative counts are illegal anyway, so abuse that for our EOF sentinel


class MetaType(type):
    """Base metaclass for cstruct type classes."""

    __cs__: cstruct
    """The cstruct instance this type class belongs to."""
    __size__: int | None
    """The size of the type in bytes. Can be ``None`` for dynamic sized types."""
    __dynamic__: bool
    """Whether or not the type is dynamically sized."""
    __alignment__: int | None
    """The alignment of the type in bytes. A value of ``None`` will be treated as 1-byte aligned."""

    # This must be the actual type, but since Array is a subclass of BaseType, we correct this at the bottom of the file
    __ArrayType__: type[BaseArray] = "Array"
    """The array type for this type class."""

    def __call__(cls, *args, **kwargs) -> Self:  # type: ignore
        """Adds support for ``TypeClass(bytes | file-like object)`` parsing syntax."""
        # TODO: add support for Type(cs) API to create new bounded type classes, similar to the old API?
        if len(args) == 1 and not isinstance(args[0], cls):
            stream = args[0]

            if _is_readable_type(stream):
                endian = (
                    normalize_endianness(endian) if (endian := kwargs.get("endian")) is not None else cls.__cs__.endian
                )
                return cls._read(stream, endian=endian)

            if issubclass(cls, bytes) and isinstance(stream, bytes) and len(stream) == cls.__size__:
                # Shortcut for char/bytes type
                return type.__call__(cls, *args, **kwargs)

            if _is_buffer_type(stream):
                return cls.reads(stream, endian=kwargs.get("endian"))

        return type.__call__(cls, *args, **kwargs)

    def __getitem__(cls, num_entries: int | Expression | None) -> type[BaseArray]:
        """Create a new array with the given number of entries."""
        return cls.__cs__._make_array(cls, num_entries)

    def __bool__(cls) -> bool:
        """Type class is always truthy."""
        return True

    def __len__(cls) -> int:
        """Return the byte size of the type."""
        if cls.__size__ is None:
            raise TypeError("Dynamic size")

        return cls.__size__

    def __default__(cls) -> Self:  # type: ignore
        """Return the default value of this type."""
        return cls()

    def reads(cls, data: bytes | memoryview | bytearray, *, endian: AllowedEndianness | None = None) -> Self:  # type: ignore
        """Parse the given data from a bytes-like object.

        Args:
            data: Bytes-like object to parse.
            endian: The endianness to use when parsing (little, big, network, <, >, !, @ or =).
                    When omitted, the cstruct instance's current endianness is used.

        Returns:
            The parsed value of this type.
        """
        endian = normalize_endianness(endian) if endian is not None else cls.__cs__.endian
        return cls._read(BytesIO(data), endian=endian)

    def read(cls, obj: BinaryIO | bytes | memoryview | bytearray, *, endian: AllowedEndianness | None = None) -> Self:  # type: ignore
        """Parse the given data.

        Args:
            obj: Data to parse. Can be a bytes-like object or a file-like object.
            endian: The endianness to use when parsing (little, big, network, <, >, !, @ or =).
                    When omitted, the cstruct instance's current endianness is used.

        Returns:
            The parsed value of this type.
        """
        if _is_buffer_type(obj):
            return cls.reads(obj, endian=endian)

        if not _is_readable_type(obj):
            raise TypeError("Invalid object type")

        endian = normalize_endianness(endian) if endian is not None else cls.__cs__.endian
        return cls._read(obj, endian=endian)

    def write(cls, stream: BinaryIO, value: Any, *, endian: AllowedEndianness | None = None) -> int:
        """Write a value to a writable file-like object.

        Args:
            stream: File-like objects that supports writing.
            value: Value to write.
            endian: The endianness to use when parsing (little, big, network, <, >, !, @ or =).
                    When omitted, the cstruct instance's current endianness is used.

        Returns:
            The amount of bytes written.
        """
        endian = normalize_endianness(endian) if endian is not None else cls.__cs__.endian
        return cls._write(stream, value, endian=endian)

    def dumps(cls, value: Any, *, endian: AllowedEndianness | None = None) -> bytes:
        """Dump a value to a byte string.

        Args:
            value: Value to dump.
            endian: The endianness to use when parsing (little, big, network, <, >, !, @ or =).
                    When omitted, the cstruct instance's current endianness is used.

        Returns:
            The raw bytes of this type.
        """
        endian = normalize_endianness(endian) if endian is not None else cls.__cs__.endian

        out = BytesIO()
        cls._write(out, value, endian=endian)
        return out.getvalue()

    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> Self:  # type: ignore
        """Internal function for reading value.

        Must be implemented per type.

        Args:
            stream: The stream to read from.
            context: Optional reading context.
            endian: The endianness to use when parsing (little, big, network, <, >, !, @ or =).
        """
        raise NotImplementedError

    def _read_array(
        cls, stream: BinaryIO, count: int, *, context: dict[str, Any] | None = None, endian: Endianness
    ) -> list[Self]:  # type: ignore
        """Internal function for reading array values.

        Allows type implementations to do optimized reading for their type.

        Args:
            stream: The stream to read from.
            count: The amount of values to read.
            context: Optional reading context.
            endian: The endianness to use when parsing (little, big, network, <, >, !, @ or =).
        """
        if count == EOF:
            result = []
            while not _is_eof(stream):
                result.append(cls._read(stream, context=context, endian=endian))
            return result

        return [cls._read(stream, context=context, endian=endian) for _ in range(count)]

    def _read_0(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> list[Self]:
        """Internal function for reading null-terminated data.

        "Null" is type specific, so must be implemented per type.

        Args:
            stream: The stream to read from.
            context: Optional reading context.
            endian: The endianness to use when parsing (little, big, network, <, >, !, @ or =).
        """
        raise NotImplementedError

    def _write(cls, stream: BinaryIO, data: Any, *, endian: Endianness) -> int:
        raise NotImplementedError

    def _write_array(cls, stream: BinaryIO, array: list[Self], *, endian: Endianness) -> int:  # type: ignore
        """Internal function for writing arrays.

        Allows type implementations to do optimized writing for their type.

        Args:
            stream: The stream to read from.
            array: The array to write.
            endian: The endianness to use when parsing (little, big, network, <, >, !, @ or =).
        """
        return sum(cls._write(stream, entry, endian=endian) for entry in array)

    def _write_0(cls, stream: BinaryIO, array: list[Self], *, endian: Endianness) -> int:  # type: ignore
        """Internal function for writing null-terminated arrays.

        Allows type implementations to do optimized writing for their type.

        Args:
            stream: The stream to read from.
            array: The array to write.
            endian: The endianness to use when parsing (little, big, network, <, >, !, @ or =).
        """
        return cls._write_array(stream, [*array, cls.__default__()], endian=endian)

    @property
    def cs(cls) -> cstruct:
        """Access the cstruct object for this type."""
        warnings.warn(
            "The 'cs' property is deprecated, use '__cs__' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.__cs__

    @property
    def size(cls) -> int | None:
        """Access the size of this type."""
        warnings.warn(
            "The 'size' property is deprecated, use '__size__', len(cls) or sizeof(cls) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.__size__

    @property
    def dynamic(cls) -> bool:
        """Access whether this type is dynamically sized."""
        warnings.warn(
            "The 'dynamic' property is deprecated, use '__dynamic__' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.__dynamic__

    @property
    def alignment(cls) -> int | None:
        """Access the alignment of this type."""
        warnings.warn(
            "The 'alignment' property is deprecated, use '__alignment__' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.__alignment__

    @property
    def ArrayType(cls) -> type[BaseArray]:
        """Access the array type of this type."""
        warnings.warn(
            "The 'ArrayType' property is deprecated, use '__ArrayType__' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.__ArrayType__


class _overload:
    """Descriptor to use on the ``write`` and ``dumps`` methods on cstruct types.

    Allows for calling these methods on both the type and instance.

    Example:
        >>> int32.dumps(123)
        b'\\x7b\\x00\\x00\\x00'
        >>> int32(123).dumps()
        b'\\x7b\\x00\\x00\\x00'
    """

    def __init__(self, func: Callable[..., Any]) -> None:
        self.func = func

    def __get__(self, instance: BaseType | None, owner: type[BaseType]) -> Callable[[], bytes]:
        if instance is None:
            return functools.partial(self.func, owner)
        return functools.partial(self.func, instance.__class__, value=instance)


class BaseType(metaclass=MetaType):
    """Base class for cstruct type classes."""

    dumps = _overload(MetaType.dumps)
    write = _overload(MetaType.write)

    def __len__(self) -> int:
        """Return the byte size of the type."""
        if self.__class__.__size__ is None:
            raise TypeError("Dynamic size")

        return self.__class__.__size__


T = TypeVar("T", bound=BaseType)


class BaseArray(BaseType):
    """Implements a fixed or dynamically sized array type.

    Example:
        When using the default C-style parser, the following syntax is supported:

            x[3] -> 3 -> static length.
            x[] -> None -> null-terminated.
            x[expr] -> expr -> dynamic length.
    """

    __type__: ClassVar[type[BaseType]]
    __num_entries__: ClassVar[int | Expression | None]
    __null_terminated__: ClassVar[bool]

    @classmethod
    def __default__(cls) -> BaseType:
        return type.__call__(
            cls, [cls.__type__.__default__()] * (cls.__num_entries__ if isinstance(cls.__num_entries__, int) else 0)
        )

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> list[BaseType]:
        if cls.__null_terminated__:
            return cls.__type__._read_0(stream, context=context, endian=endian)

        if isinstance(cls.__num_entries__, int):
            num = max(0, cls.__num_entries__)
        elif cls.__num_entries__ is None:
            num = EOF
        elif isinstance(cls.__num_entries__, Expression):
            try:
                num = max(0, cls.__num_entries__.evaluate(cls.__cs__, context))
            except Exception:
                if cls.__num_entries__.expression != "EOF":
                    raise
                num = EOF

        return cls.__type__._read_array(stream, num, context=context, endian=endian)

    @classmethod
    def _write(cls, stream: BinaryIO, data: list[Any], *, endian: Endianness) -> int:
        if cls.__null_terminated__:
            return cls.__type__._write_0(stream, data, endian=endian)

        if not cls.__dynamic__ and (remaining := cls.__num_entries__ - (actual_size := len(data))):
            if remaining < 0:
                raise ArraySizeError(f"Expected static array size {cls.__num_entries__}, got {actual_size} instead.")
            data = data + [cls.__type__.__default__()] * remaining

        return cls.__type__._write_array(stream, data, endian=endian)

    @classproperty
    def type(cls) -> type[BaseType]:
        """Access the array element type."""
        warnings.warn(
            "The 'type' property is deprecated, use '__type__' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.__type__

    @classproperty
    def num_entries(cls) -> int | Expression | None:
        """Access the number of entries for this array type."""
        warnings.warn(
            "The 'num_entries' property is deprecated, use '__num_entries__' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.__num_entries__

    @classproperty
    def null_terminated(cls) -> bool:
        """Access whether this array type is null-terminated."""
        warnings.warn(
            "The 'null_terminated' property is deprecated, use '__null_terminated__' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.__null_terminated__


class Array(list[T], BaseArray):
    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness) -> list[T]:
        return cls(super()._read(stream, context=context, endian=endian))


def _is_readable_type(value: object) -> bool:
    return hasattr(value, "read")


def _is_buffer_type(value: object) -> bool:
    return isinstance(value, (bytes, memoryview, bytearray))


def _is_eof(stream: BinaryIO) -> bool:
    """Check if the stream has reached EOF."""
    pos = stream.tell()
    stream.read(1)

    if stream.tell() == pos:
        return True

    stream.seek(pos)
    return False


# As mentioned in the BaseType class, we correctly set the type here
MetaType.__ArrayType__ = Array
