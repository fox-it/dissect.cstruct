from __future__ import annotations

from io import BytesIO
from typing import Any, BinaryIO, List, TYPE_CHECKING

from dissect.cstruct.expression import Expression

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class BaseType:
    """Base class for cstruct type classes."""

    def __init__(self, cstruct: cstruct):
        self.cstruct = cstruct

    def __getitem__(self, count: int) -> Array:
        return Array(self.cstruct, self, count)

    def __call__(self, *args, **kwargs) -> Any:
        if len(args) > 0:
            return self.read(*args, **kwargs)

        result = self.default()
        if kwargs:
            for k, v in kwargs.items():
                setattr(result, k, v)

        return result

    def reads(self, data: bytes) -> Any:
        """Parse the given data according to the type that implements this class.

        Args:
            data: Byte string to parse.

        Returns:
            The parsed value of this type.
        """

        return self._read(BytesIO(data))

    def dumps(self, data: Any) -> bytes:
        """Dump the given data according to the type that implements this class.

        Args:
            data: Data to dump.

        Returns:
            The resulting bytes.
        """
        out = BytesIO()
        self._write(out, data)
        return out.getvalue()

    def read(self, obj: BinaryIO, *args, **kwargs) -> Any:
        """Parse the given data according to the type that implements this class.

        Args:
            obj: Data to parse. Can be a (byte) string or a file-like object.

        Returns:
            The parsed value of this type.
        """
        if isinstance(obj, (bytes, memoryview, bytearray)):
            return self.reads(obj)

        return self._read(obj)

    def write(self, stream: BinaryIO, data: Any) -> int:
        """Write the given data to a writable file-like object according to the
        type that implements this class.

        Args:
            stream: Writable file-like object to write to.
            data: Data to write.

        Returns:
            The amount of bytes written.
        """
        return self._write(stream, data)

    def _read(self, stream: BinaryIO) -> Any:
        raise NotImplementedError()

    def _read_array(self, stream: BinaryIO, count: int) -> List[Any]:
        return [self._read(stream) for _ in range(count)]

    def _read_0(self, stream: BinaryIO) -> List[Any]:
        raise NotImplementedError()

    def _write(self, stream: BinaryIO, data: Any) -> int:
        raise NotImplementedError()

    def _write_array(self, stream: BinaryIO, data: Any) -> int:
        num = 0
        for i in data:
            num += self._write(stream, i)

        return num

    def _write_0(self, stream: BinaryIO, data: Any) -> int:
        raise NotImplementedError()

    def default(self) -> Any:
        """Return a default value of this type."""
        raise NotImplementedError()

    def default_array(self, count: int) -> List[Any]:
        """Return a default array of this type."""
        return [self.default() for _ in range(count)]


class Array(BaseType):
    """Implements a fixed or dynamically sized array type.

    Example:
        When using the default C-style parser, the following syntax is supported:

            x[3] -> 3 -> static length.
            x[] -> None -> null-terminated.
            x[expr] -> expr -> dynamic length.
    """

    def __init__(self, cstruct: cstruct, type_: BaseType, count: int):
        self.type = type_
        self.count = count
        self.null_terminated = self.count is None
        self.dynamic = isinstance(self.count, Expression)
        self.alignment = type_.alignment
        super().__init__(cstruct)

    def __repr__(self) -> str:
        if self.null_terminated:
            return f"{self.type}[]"

        return f"{self.type}[{self.count}]"

    def __len__(self) -> int:
        if self.dynamic or self.null_terminated:
            raise TypeError("Dynamic size")

        return len(self.type) * self.count

    def _read(self, stream: BinaryIO, context: dict = None) -> List[Any]:
        if self.null_terminated:
            return self.type._read_0(stream)

        if self.dynamic:
            count = self.count.evaluate(context)
        else:
            count = self.count

        return self.type._read_array(stream, max(0, count))

    def _write(self, stream: BinaryIO, data: List[Any]) -> int:
        if self.null_terminated:
            return self.type._write_0(stream, data)

        return self.type._write_array(stream, data)

    def default(self) -> List[Any]:
        count = 0 if self.dynamic or self.null_terminated else self.count
        return self.type.default_array(count)


class RawType(BaseType):
    """Base class for raw types that have a name and size."""

    def __init__(self, cstruct: cstruct, name: str = None, size: int = 0, alignment: int = None):
        self.name = name
        self.size = size
        self.alignment = alignment or size
        super().__init__(cstruct)

    def __len__(self) -> int:
        return self.size

    def __repr__(self) -> str:
        if self.name:
            return self.name

        return BaseType.__repr__(self)

    def _read(self, stream: BinaryIO) -> Any:
        raise NotImplementedError()

    def _read_0(self, stream: BinaryIO) -> List[Any]:
        raise NotImplementedError()

    def _write(self, stream: BinaryIO, data: Any) -> int:
        raise NotImplementedError()

    def _write_0(self, stream: BinaryIO, data: List[Any]) -> int:
        raise NotImplementedError()

    def default(self) -> Any:
        raise NotImplementedError()
