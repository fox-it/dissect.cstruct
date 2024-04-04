from __future__ import annotations

from typing import Any, BinaryIO

from dissect.cstruct.exceptions import NullPointerDereference
from dissect.cstruct.types.base import BaseType, MetaType
from dissect.cstruct.types.char import Char
from dissect.cstruct.types.void import Void


class Pointer(int, BaseType):
    """Pointer to some other type."""

    type: MetaType
    _stream: BinaryIO
    _context: dict[str, Any]
    _value: BaseType

    def __new__(cls, value: int, stream: BinaryIO, context: dict[str, Any] = None) -> Pointer:
        obj = super().__new__(cls, value)
        obj._stream = stream
        obj._context = context
        obj._value = None
        return obj

    def __repr__(self) -> str:
        return f"<{self.type.__name__}* @ {self:#x}>"

    def __str__(self) -> str:
        return str(self.dereference())

    def __getattr__(self, attr: str) -> Any:
        return getattr(self.dereference(), attr)

    def __add__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__add__(self, other), self._stream, self._context)

    def __sub__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__sub__(self, other), self._stream, self._context)

    def __mul__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__mul__(self, other), self._stream, self._context)

    def __floordiv__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__floordiv__(self, other), self._stream, self._context)

    def __mod__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__mod__(self, other), self._stream, self._context)

    def __pow__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__pow__(self, other), self._stream, self._context)

    def __lshift__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__lshift__(self, other), self._stream, self._context)

    def __rshift__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__rshift__(self, other), self._stream, self._context)

    def __and__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__and__(self, other), self._stream, self._context)

    def __xor__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__xor__(self, other), self._stream, self._context)

    def __or__(self, other: int) -> Pointer:
        return type.__call__(self.__class__, int.__or__(self, other), self._stream, self._context)

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Pointer:
        return cls.__new__(cls, cls.cs.pointer._read(stream, context), stream, context)

    @classmethod
    def _write(cls, stream: BinaryIO, data: int) -> int:
        return cls.cs.pointer._write(stream, data)

    def dereference(self) -> Any:
        if self == 0:
            raise NullPointerDereference()

        if self._value is None and not issubclass(self.type, Void):
            # Read current position of file read/write pointer
            position = self._stream.tell()
            # Reposition the file read/write pointer
            self._stream.seek(self)

            if issubclass(self.type, Char):
                # this makes the assumption that a char pointer is a null-terminated string
                value = self.type._read_0(self._stream, self._context)
            else:
                value = self.type._read(self._stream, self._context)

            self._stream.seek(position)
            self._value = value

        return self._value
