from __future__ import annotations

from typing import TYPE_CHECKING, Any, BinaryIO

import pytest

from dissect.cstruct.types import BaseType

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


class EtwPointer(BaseType):
    type: type[BaseType]
    size: int | None

    @classmethod
    def __default__(cls) -> int:
        return cls.cs.uint64.__default__()

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> BaseType:
        return cls.type._read(stream, context)

    @classmethod
    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> list[BaseType]:
        return cls.type._read_0(stream, context)

    @classmethod
    def _write(cls, stream: BinaryIO, data: Any) -> int:
        return cls.type._write(stream, data)

    @classmethod
    def as_32bit(cls) -> None:
        cls.type = cls.cs.uint32
        cls.size = 4

    @classmethod
    def as_64bit(cls) -> None:
        cls.type = cls.cs.uint64
        cls.size = 8


def test_adding_custom_type(cs: cstruct) -> None:
    cs.add_custom_type("EtwPointer", EtwPointer)

    cs.EtwPointer.as_64bit()
    assert cs.EtwPointer.type is cs.uint64
    assert len(cs.EtwPointer) == 8
    assert cs.EtwPointer(b"\xde\xad\xbe\xef" * 2).dumps() == b"\xde\xad\xbe\xef" * 2

    cs.EtwPointer.as_32bit()
    assert cs.EtwPointer.type is cs.uint32
    assert len(cs.EtwPointer) == 4
    assert cs.EtwPointer(b"\xde\xad\xbe\xef" * 2).dumps() == b"\xde\xad\xbe\xef"


def test_using_type_in_struct(cs: cstruct) -> None:
    cs.add_custom_type("EtwPointer", EtwPointer)

    struct_definition = """
    struct test {
        EtwPointer data;
        uint64     data2;
    };
    """

    cs.load(struct_definition)

    cs.EtwPointer.as_64bit()
    with pytest.raises(EOFError):
        # Input too small
        cs.test(b"\xde\xad\xbe\xef" * 3)

    cs.EtwPointer.as_32bit()

    obj = cs.test(b"\xde\xad\xbe\xef" * 3)
    assert obj.data == 0xEFBEADDE
    assert obj.data2 == 0xEFBEADDEEFBEADDE
    assert obj.data.dumps() == b"\xde\xad\xbe\xef"


def test_custom_default(cs: cstruct) -> None:
    cs.add_custom_type("EtwPointer", EtwPointer)

    cs.EtwPointer.as_64bit()
    assert cs.EtwPointer.__default__() == 0

    cs.EtwPointer.as_32bit()
    assert cs.EtwPointer.__default__() == 0

    assert cs.EtwPointer[1].__default__() == [0]
    assert cs.EtwPointer[None].__default__() == []
