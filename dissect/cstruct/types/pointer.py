from __future__ import annotations

import operator
from typing import Any, BinaryIO, Callable, Dict, Union, TYPE_CHECKING

from dissect.cstruct.exceptions import NullPointerDereference
from dissect.cstruct.types import BaseType, CharType, RawType

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class Pointer(RawType):
    """Implements a pointer to some other type."""

    def __init__(self, cstruct: cstruct, target: BaseType):
        self.cstruct = cstruct
        self.type = target
        super().__init__(cstruct, "pointer", self.cstruct.pointer.size, self.cstruct.pointer.alignment)

    def __repr__(self) -> str:
        return f"<Pointer {self.type}>"

    def _read(self, stream: BinaryIO, context: dict[str, Any] = None) -> PointerInstance:
        addr = self.cstruct.pointer(stream)
        return PointerInstance(self.type, stream, addr, context)

    def _write(self, stream: BinaryIO, data: Union[int, PointerInstance]):
        if isinstance(data, PointerInstance):
            data = data._addr

        if not isinstance(data, int):
            raise TypeError("Invalid pointer data")

        return self.cstruct.pointer._write(stream, data)


class PointerInstance:
    """Like the Instance class, but for structures referenced by a pointer."""

    def __init__(self, type_: BaseType, stream: BinaryIO, addr: int, ctx: Dict[str, Any]):
        self._stream = stream
        self._type = type_
        self._addr = addr
        self._ctx = ctx
        self._value = None

    def __repr__(self) -> str:
        return f"<Pointer {self._type} @ 0x{self._addr:x}>"

    def __str__(self) -> str:
        return str(self.dereference())

    def __getattr__(self, attr: str) -> Any:
        return getattr(self.dereference(), attr)

    def __int__(self) -> int:
        return self._addr

    def __nonzero__(self) -> bool:
        return self._addr != 0

    def __addr_math(self, other: Union[int, PointerInstance], op: Callable[[int, int], int]) -> PointerInstance:
        if isinstance(other, PointerInstance):
            other = other._addr

        return PointerInstance(self._type, self._stream, op(self._addr, other), self._ctx)

    def __add__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__add__)

    def __sub__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__sub__)

    def __mul__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__mul__)

    def __floordiv__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__floordiv__)

    def __mod__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__mod__)

    def __pow__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__pow__)

    def __lshift__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__lshift__)

    def __rshift__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__rshift__)

    def __and__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__and__)

    def __xor__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__xor__)

    def __or__(self, other: Union[int, PointerInstance]) -> PointerInstance:
        return self.__addr_math(other, operator.__or__)

    def __eq__(self, other: Union[int, PointerInstance]) -> bool:
        if isinstance(other, PointerInstance):
            other = other._addr

        return self._addr == other

    def dereference(self) -> Any:
        if self._addr == 0:
            raise NullPointerDereference()

        if self._value is None:
            # Read current position of file read/write pointer
            position = self._stream.tell()
            # Reposition the file read/write pointer
            self._stream.seek(self._addr)

            if isinstance(self._type, CharType):
                # this makes the assumption that a char pointer is a null-terminated string
                value = self._type._read_0(self._stream, self._ctx)
            else:
                value = self._type._read(self._stream, self._ctx)

            self._stream.seek(position)
            self._value = value

        return self._value
