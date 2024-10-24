from __future__ import annotations

import functools
from io import BytesIO
from typing import TYPE_CHECKING, Any, BinaryIO, Callable

from dissect.cstruct.exceptions import ArraySizeError
from dissect.cstruct.expression import Expression

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


EOF = -0xE0F  # Negative counts are illegal anyway, so abuse that for our EOF sentinel


class MetaType(type):
    """Base metaclass for cstruct type classes."""

    cs: cstruct
    """The cstruct instance this type class belongs to."""
    size: int | None
    """The size of the type in bytes. Can be ``None`` for dynamic sized types."""
    dynamic: bool
    """Whether or not the type is dynamically sized."""
    alignment: int | None
    """The alignment of the type in bytes. A value of ``None`` will be treated as 1-byte aligned."""

    # This must be the actual type, but since Array is a subclass of BaseType, we correct this at the bottom of the file
    ArrayType: type[Array] = "Array"
    """The array type for this type class."""

    def __call__(cls, *args, **kwargs) -> MetaType | BaseType:
        """Adds support for ``TypeClass(bytes | file-like object)`` parsing syntax."""
        # TODO: add support for Type(cs) API to create new bounded type classes, similar to the old API?
        if len(args) == 1 and not isinstance(args[0], cls):
            stream = args[0]

            if _is_readable_type(stream):
                return cls._read(stream)

            if issubclass(cls, bytes) and isinstance(stream, bytes) and len(stream) == cls.size:
                # Shortcut for char/bytes type
                return type.__call__(cls, *args, **kwargs)

            if _is_buffer_type(stream):
                return cls.reads(stream)

        return type.__call__(cls, *args, **kwargs)

    def __getitem__(cls, num_entries: int | Expression | None) -> ArrayMetaType:
        """Create a new array with the given number of entries."""
        return cls.cs._make_array(cls, num_entries)

    def __len__(cls) -> int:
        """Return the byte size of the type."""
        if cls.size is None:
            raise TypeError("Dynamic size")

        return cls.size

    def default(cls) -> BaseType:
        """Return the default value of this type."""
        return cls()

    def reads(cls, data: bytes) -> BaseType:
        """Parse the given data from a bytes-like object.

        Args:
            data: Bytes-like object to parse.

        Returns:
            The parsed value of this type.
        """
        return cls._read(BytesIO(data))

    def read(cls, obj: BinaryIO | bytes) -> BaseType:
        """Parse the given data.

        Args:
            obj: Data to parse. Can be a bytes-like object or a file-like object.

        Returns:
            The parsed value of this type.
        """
        if _is_buffer_type(obj):
            return cls.reads(obj)

        return cls._read(obj)

    def write(cls, stream: BinaryIO, value: Any) -> int:
        """Write a value to a writable file-like object.

        Args:
            stream: File-like objects that supports writing.
            value: Value to write.

        Returns:
            The amount of bytes written.
        """
        return cls._write(stream, value)

    def dumps(cls, value: Any) -> bytes:
        """Dump a value to a byte string.

        Args:
            value: Value to dump.

        Returns:
            The raw bytes of this type.
        """
        out = BytesIO()
        cls._write(out, value)
        return out.getvalue()

    def _read(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> BaseType:
        """Internal function for reading value.

        Must be implemented per type.

        Args:
            stream: The stream to read from.
            context: Optional reading context.
        """
        raise NotImplementedError()

    def _read_array(cls, stream: BinaryIO, count: int, context: dict[str, Any] | None = None) -> list[BaseType]:
        """Internal function for reading array values.

        Allows type implementations to do optimized reading for their type.

        Args:
            stream: The stream to read from.
            count: The amount of values to read.
            context: Optional reading context.
        """
        if count == EOF:
            result = []
            while True:
                try:
                    result.append(cls._read(stream, context))
                except EOFError:
                    break
            return result

        return [cls._read(stream, context) for _ in range(count)]

    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> list[BaseType]:
        """Internal function for reading null-terminated data.

        "Null" is type specific, so must be implemented per type.

        Args:
            stream: The stream to read from.
            context: Optional reading context.
        """
        raise NotImplementedError()

    def _write(cls, stream: BinaryIO, data: Any) -> int:
        raise NotImplementedError()

    def _write_array(cls, stream: BinaryIO, array: list[BaseType]) -> int:
        """Internal function for writing arrays.

        Allows type implementations to do optimized writing for their type.

        Args:
            stream: The stream to read from.
            array: The array to write.
        """
        return sum(cls._write(stream, entry) for entry in array)

    def _write_0(cls, stream: BinaryIO, array: list[BaseType]) -> int:
        """Internal function for writing null-terminated arrays.

        Allows type implementations to do optimized writing for their type.

        Args:
            stream: The stream to read from.
            array: The array to write.
        """
        return cls._write_array(stream, array + [cls.default()])


class _overload:
    """Descriptor to use on the ``write`` and ``dumps`` methods on cstruct types.

    Allows for calling these methods on both the type and instance.

    Example:
        >>> int32.dumps(123)
        b'\\x7b\\x00\\x00\\x00'
        >>> int32(123).dumps()
        b'\\x7b\\x00\\x00\\x00'
    """

    def __init__(self, func: Callable[[Any], Any]) -> None:
        self.func = func

    def __get__(self, instance: BaseType | None, owner: MetaType) -> Callable[[Any], bytes]:
        if instance is None:
            return functools.partial(self.func, owner)
        else:
            return functools.partial(self.func, instance.__class__, value=instance)


class BaseType(metaclass=MetaType):
    """Base class for cstruct type classes."""

    dumps = _overload(MetaType.dumps)
    write = _overload(MetaType.write)

    def __len__(self) -> int:
        """Return the byte size of the type."""
        if self.__class__.size is None:
            raise TypeError("Dynamic size")

        return self.__class__.size


class ArrayMetaType(MetaType):
    """Base metaclass for array-like types."""

    type: MetaType
    num_entries: int | Expression | None
    null_terminated: bool

    def default(cls) -> BaseType:
        return type.__call__(cls, [cls.type.default()] * (cls.num_entries if isinstance(cls.num_entries, int) else 0))

    def _read(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> Array:
        if cls.null_terminated:
            return cls.type._read_0(stream, context)

        if isinstance(cls.num_entries, int):
            num = max(0, cls.num_entries)
        elif cls.num_entries is None:
            num = EOF
        elif isinstance(cls.num_entries, Expression):
            try:
                num = max(0, cls.num_entries.evaluate(context))
            except Exception:
                if cls.num_entries.expression != "EOF":
                    raise
                num = EOF

        return cls.type._read_array(stream, num, context)


class Array(list, BaseType, metaclass=ArrayMetaType):
    """Implements a fixed or dynamically sized array type.

    Example:
        When using the default C-style parser, the following syntax is supported:

            x[3] -> 3 -> static length.
            x[] -> None -> null-terminated.
            x[expr] -> expr -> dynamic length.
    """

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> Array:
        return cls(ArrayMetaType._read(cls, stream, context))

    @classmethod
    def _write(cls, stream: BinaryIO, data: list[Any]) -> int:
        if cls.null_terminated:
            return cls.type._write_0(stream, data)

        if not cls.dynamic and cls.num_entries != (actual_size := len(data)):
            raise ArraySizeError(f"Expected static array size {cls.num_entries}, got {actual_size} instead.")

        return cls.type._write_array(stream, data)


def _is_readable_type(value: Any) -> bool:
    return hasattr(value, "read")


def _is_buffer_type(value: Any) -> bool:
    return isinstance(value, (bytes, memoryview, bytearray))


# As mentioned in the BaseType class, we correctly set the type here
MetaType.ArrayType = Array
