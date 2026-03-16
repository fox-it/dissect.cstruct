from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING, Any, BinaryIO, Generic, TypeVar

from dissect.cstruct.exceptions import NullPointerDereference
from dissect.cstruct.types.base import BaseType, normalize_endianness
from dissect.cstruct.types.char import Char
from dissect.cstruct.types.void import Void

if TYPE_CHECKING:
    from collections.abc import Callable

    from typing_extensions import Self

    from dissect.cstruct.cstruct import AllowedEndianness, Endianness

T = TypeVar("T", bound=BaseType)


class Pointer(int, BaseType, Generic[T]):
    """Pointer to some other type."""

    type: type[T]
    _stream: BinaryIO | None
    _context: dict[str, Any] | None
    _endian: Endianness
    _kwargs: dict[str, Any]

    def __new__(
        cls, value: int, stream: BinaryIO | None, *, context: dict[str, Any] | None = None, endian: Endianness, **kwargs
    ) -> Self:
        obj = super().__new__(cls, value)
        obj._stream = stream
        obj._context = context
        obj._endian = endian
        obj._kwargs = kwargs
        obj.dereference = cache(obj.dereference)
        return obj

    def __repr__(self) -> str:
        return f"<{self.type.__name__}* @ {self:#x}>"

    def __str__(self) -> str:
        return str(self.dereference())

    def __getattr__(self, attr: str) -> Any:
        return getattr(self.dereference(), attr)

    @staticmethod
    def __op(op: Callable[[int, int], int]) -> Self:
        def method(self: Self, other: int) -> Self:
            return type.__call__(
                self.__class__,
                op(self, other),
                self._stream,
                context=self._context,
                endian=self._endian,
                **self._kwargs,
            )

        return method

    __add__ = __op(int.__add__)
    __sub__ = __op(int.__sub__)
    __mul__ = __op(int.__mul__)
    __floordiv__ = __op(int.__floordiv__)
    __mod__ = __op(int.__mod__)
    __pow__ = __op(int.__pow__)
    __lshift__ = __op(int.__lshift__)
    __rshift__ = __op(int.__rshift__)
    __and__ = __op(int.__and__)
    __xor__ = __op(int.__xor__)
    __or__ = __op(int.__or__)

    @classmethod
    def __default__(cls) -> Self:
        return cls.__new__(
            cls,
            cls.cs.pointer.__default__(),
            None,
            context=None,
            endian=cls.cs.endian,
        )

    @classmethod
    def _read(cls, stream: BinaryIO, *, context: dict[str, Any] | None = None, endian: Endianness, **kwargs) -> Self:
        return cls.__new__(
            cls,
            cls.cs.pointer._read(stream, context=context, endian=endian, **kwargs),
            stream,
            context=context,
            endian=endian,
            **kwargs,
        )

    @classmethod
    def _write(cls, stream: BinaryIO, data: int, *, endian: Endianness, **kwargs) -> int:
        return cls.cs.pointer._write(stream, data, endian=endian, **kwargs)

    def dereference(self, *, endian: AllowedEndianness | None = None) -> T:
        """Dereference the pointer and read the value it points to.

        Args:
            endian: Optional endianness to use when reading the value.
                    If not provided, the endianness used when reading the pointer itself will be used.
        """
        if self == 0 or self._stream is None:
            raise NullPointerDereference

        endian = normalize_endianness(endian) if endian is not None else self._endian
        if issubclass(self.type, Void):
            return None

        position = self._stream.tell()
        self._stream.seek(self)

        if issubclass(self.type, Char):
            # This makes the assumption that a char pointer is a null-terminated string
            value = self.type._read_0(self._stream, context=self._context, endian=endian, **self._kwargs)
        else:
            value = self.type._read(self._stream, context=self._context, endian=endian, **self._kwargs)

        # Restore the stream position after reading the value
        self._stream.seek(position)
        return value
