from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any, BinaryIO, Optional, Union

from dissect.cstruct.exceptions import ArraySizeError

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct
    from dissect.cstruct.expression import Expression


EOF = -0xE0F  # Negative counts are illegal anyway, so abuse that for our EOF sentinel


class MetaType(type):
    """Base metaclass for cstruct type classes."""

    cs: cstruct
    """The cstruct instance this type class belongs to."""
    size: Optional[int]
    """The size of the type in bytes. Can be ``None`` for dynamic sized types."""
    dynamic: bool
    """Whether or not the type is dynamically sized."""
    alignment: int
    """The alignment of the type in bytes."""

    def __call__(cls, *args, **kwargs) -> Union[MetaType, BaseType]:
        """Adds support for ``TypeClass(bytes | file-like object)`` parsing syntax."""
        # TODO: add support for Type(cs) API to create new bounded type classes, similar to the old API?
        if len(args) == 1 and not isinstance(args[0], cls):
            stream = args[0]

            if hasattr(stream, "read"):
                return cls._read(stream)

            if issubclass(cls, bytes) and isinstance(stream, bytes) and len(stream) == cls.size:
                # Shortcut for char/bytes type
                return type.__call__(cls, *args, **kwargs)

            if isinstance(stream, (bytes, memoryview, bytearray)):
                return cls.reads(stream)

        return type.__call__(cls, *args, **kwargs)

    def __getitem__(cls, num_entries: Optional[Union[int, Expression]]) -> ArrayMetaType:
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

    def read(cls, obj: Union[BinaryIO, bytes]) -> BaseType:
        """Parse the given data.

        Args:
            obj: Data to parse. Can be a bytes-like object or a file-like object.

        Returns:
            The parsed value of this type.
        """
        if isinstance(obj, (bytes, memoryview, bytearray)):
            return cls.reads(obj)

        return cls._read(obj)

    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> BaseType:
        """Internal function for reading value.

        Must be implemented per type.

        Args:
            stream: The stream to read from.
            context: Optional reading context.
        """
        raise NotImplementedError()

    def _read_array(cls, stream: BinaryIO, count: int, context: dict[str, Any] = None) -> list[BaseType]:
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

    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] = None) -> list[BaseType]:
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
        return cls._write_array(stream, array + [cls()])


class BaseType(metaclass=MetaType):
    """Base class for cstruct type classes."""

    def dumps(self) -> bytes:
        """Dump this value to a byte string.

        Returns:
            The raw bytes of this type.
        """
        out = BytesIO()
        self.__class__._write(out, self)
        return out.getvalue()

    def write(self, stream: BinaryIO) -> int:
        """Write this value to a writable file-like object.

        Args:
            fh: File-like objects that supports writing.

        Returns:
            The amount of bytes written.
        """
        return self.__class__._write(stream, self)


class ArrayMetaType(MetaType):
    """Base metaclass for array-like types."""

    type: MetaType
    num_entries: Optional[Union[int, Expression]]
    null_terminated: bool

    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Array:
        if cls.null_terminated:
            return cls.type._read_0(stream, context)

        if cls.dynamic:
            try:
                num = max(0, cls.num_entries.evaluate(context))
            except Exception:
                if cls.num_entries.expression != "EOF":
                    raise
                num = EOF
        else:
            num = max(0, cls.num_entries)

        return cls.type._read_array(stream, num, context)

    def default(cls) -> BaseType:
        return [cls.type.default() for _ in range(0 if cls.dynamic or cls.null_terminated else cls.num_entries)]


class Array(list, BaseType, metaclass=ArrayMetaType):
    """Implements a fixed or dynamically sized array type.

    Example:
        When using the default C-style parser, the following syntax is supported:

            x[3] -> 3 -> static length.
            x[] -> None -> null-terminated.
            x[expr] -> expr -> dynamic length.
    """

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Array:
        return cls(ArrayMetaType._read(cls, stream, context))

    @classmethod
    def _write(cls, stream: BinaryIO, data: list[Any]) -> int:
        if cls.null_terminated:
            return cls.type._write_0(stream, data)

        if not cls.dynamic and cls.num_entries != (actual_size := len(data)):
            raise ArraySizeError(f"Expected static array size {cls.num_entries}, got {actual_size} instead.")

        return cls.type._write_array(stream, data)
