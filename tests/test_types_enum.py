from __future__ import annotations

from enum import Enum as StdEnum
from typing import TYPE_CHECKING

import pytest

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct
    from dissect.cstruct.types.enum import Enum


@pytest.fixture
def TestEnum(cs: cstruct) -> type[Enum]:
    return cs._make_enum("Test", cs.uint8, {"A": 1, "B": 2, "C": 3})


def test_enum(cs: cstruct, TestEnum: type[Enum]) -> None:
    assert issubclass(TestEnum, StdEnum)
    assert TestEnum.cs is cs
    assert TestEnum.type is cs.uint8
    assert TestEnum.size == 1
    assert TestEnum.alignment == 1

    assert TestEnum.A == 1
    assert TestEnum.B == 2
    assert TestEnum.C == 3
    assert TestEnum(1) == TestEnum.A
    assert TestEnum(2) == TestEnum.B
    assert TestEnum(3) == TestEnum.C
    assert TestEnum["A"] == TestEnum.A
    assert TestEnum["B"] == TestEnum.B
    assert TestEnum["C"] == TestEnum.C

    assert TestEnum(0) == 0
    assert TestEnum(0).name is None
    assert TestEnum(0).value == 0

    assert 0 not in TestEnum
    assert 1 in TestEnum
    assert 2 in TestEnum
    assert 3 in TestEnum
    assert 4 not in TestEnum

    assert TestEnum.A in TestEnum

    # Mixing enums is not allowed
    OtherEnum = cs._make_enum("Other", cs.uint8, {"A": 1, "B": 2, "C": 3})
    assert OtherEnum.A not in TestEnum


def test_enum_read(TestEnum: type[Enum]) -> None:
    assert TestEnum(b"\x02") == TestEnum.B


def test_enum_write(TestEnum: type[Enum]) -> None:
    assert TestEnum.B.dumps() == b"\x02"
    assert TestEnum(b"\x02").dumps() == b"\x02"


def test_enum_array_read(TestEnum: type[Enum]) -> None:
    assert TestEnum[2](b"\x02\x03") == [TestEnum.B, TestEnum.C]
    assert TestEnum[None](b"\x02\x03\x00") == [TestEnum.B, TestEnum.C]


def test_enum_array_write(TestEnum: type[Enum]) -> None:
    assert TestEnum[2]([TestEnum.B, TestEnum.C]).dumps() == b"\x02\x03"
    assert TestEnum[None]([TestEnum.B, TestEnum.C]).dumps() == b"\x02\x03\x00"


def test_enum_alias(cs: cstruct) -> None:
    AliasEnum = cs._make_enum("Test", cs.uint8, {"A": 1, "B": 2, "C": 2})

    assert AliasEnum.A == 1
    assert AliasEnum.B == 2
    assert AliasEnum.C == 2

    assert AliasEnum.A.name == "A"
    assert AliasEnum.B.name == "B"
    assert AliasEnum.C.name == "C"

    assert AliasEnum.B == AliasEnum.C

    assert AliasEnum.B.dumps() == AliasEnum.C.dumps()


def test_enum_bad_type(cs: cstruct) -> None:
    with pytest.raises(TypeError):
        cs._make_enum("Test", cs.char, {"A": 1, "B": 2, "C": 3})


def test_enum_eof(TestEnum: type[Enum]) -> None:
    with pytest.raises(EOFError):
        TestEnum(b"")

    with pytest.raises(EOFError):
        TestEnum[2](b"\x01")

    with pytest.raises(EOFError):
        TestEnum[None](b"\x01")


def test_enum_same_value_different_type(cs: cstruct, compiled: bool) -> None:
    cdef = """
    enum Test16 : uint16 {
        A = 0x1,
        B = 0x2
    };

    enum Test24 : uint24 {
        A = 0x1,
        B = 0x2
    };

    enum Test32 : uint32 {
        A = 0x1,
        B = 0x2
    };
    """
    cs.load(cdef, compiled=compiled)

    obj = {
        cs.Test16.A: "Test16.A",
        cs.Test16.B: "Test16.B",
        cs.Test24.A: "Test24.A",
        cs.Test24.B: "Test24.B",
    }

    assert obj[cs.Test16.A] == "Test16.A"
    assert obj[cs.Test16(2)] == "Test16.B"
    assert obj[cs.Test24(1)] == "Test24.A"
    assert obj[cs.Test24.B] == "Test24.B"

    with pytest.raises(KeyError):
        obj[cs.Test32.A]


def test_enum_str_repr(TestEnum: type[Enum]) -> None:
    assert repr(TestEnum.A) == "<Test.A: 1>"
    assert str(TestEnum.A) == "Test.A"
    assert repr(TestEnum(69)) == "<Test: 69>"
    assert str(TestEnum(69)) == "Test.69"


def test_enum_str_repr_in_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    enum Test16 : uint16 {
        A = 0x1,
        B = 0x2
    };

    struct test {
        Test16  a;
    };
    """
    cs.load(cdef, compiled=compiled)

    obj = cs.test(b"\x02\x00")
    assert repr(obj) == "<test a=<Test16.B: 2>>"
    assert str(obj) == "<test a=<Test16.B: 2>>"


def test_enum_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    enum Test16 : uint16 {
        A = 0x1,
        B = 0x2
    };

    enum Test24 : uint24 {
        A = 0x1,    // comment, best one
        B = 0x2
    };

    enum Test32 : uint32 {
        A = 0x1,
        B = 0x2     // comment
    };

    struct test {
        Test16  a16;
        Test16  b16;
        Test24  a24;
        Test24  b24;
        Test32  a32;
        Test32  b32;        // this is a comment, awesome
        Test16  l[2];
    };

    struct test_term {
        Test16  null[];
    };

    struct test_expr {
        uint16  size;
        Test16  expr[size * 2];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert verify_compiled(cs.test_term, compiled)
    assert verify_compiled(cs.test_expr, compiled)

    buf = b"\x01\x00\x02\x00\x01\x00\x00\x02\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x01\x00\x02\x00"
    obj = cs.test(buf)

    assert isinstance(obj.a16, cs.Test16)
    assert obj.a16 == cs.Test16.A
    assert isinstance(obj.b16, cs.Test16)
    assert obj.b16 == cs.Test16.B
    assert isinstance(obj.a24, cs.Test24)
    assert obj.a24 == cs.Test24.A
    assert isinstance(obj.b24, cs.Test24)
    assert obj.b24 == cs.Test24.B
    assert isinstance(obj.a32, cs.Test32)
    assert obj.a32 == cs.Test32.A
    assert isinstance(obj.b32, cs.Test32)
    assert obj.b32 == cs.Test32.B

    assert len(obj.l) == 2
    assert isinstance(obj.l[0], cs.Test16)
    assert obj.l[0] == cs.Test16.A
    assert isinstance(obj.l[1], cs.Test16)
    assert obj.l[1] == cs.Test16.B

    assert cs.Test16(1) == cs.Test16["A"]
    assert cs.Test24(2) == cs.Test24.B
    assert cs.Test16.A != cs.Test24.A

    with pytest.raises(KeyError):
        cs.Test16["C"]

    with pytest.raises(AttributeError):
        cs.Test16.C  # noqa: B018

    assert obj.dumps() == buf

    buf = b"\x01\x00\x02\x00\x00\x00"
    assert cs.test_term(buf).null == [cs.Test16.A, cs.Test16.B]
    assert cs.test_term(null=[cs.Test16.A, cs.Test16.B]).dumps() == buf

    buf = b"\x01\x00\x01\x00\x02\x00"
    assert cs.test_expr(buf).expr == [cs.Test16.A, cs.Test16.B]
    assert cs.test_expr(size=1, expr=[cs.Test16.A, cs.Test16.B]).dumps() == buf


def test_enum_comments(cs: cstruct) -> None:
    cdef = """
    enum Inline { hello=7, world, foo, bar }; // inline enum

    enum Test {
        a = 2,  // comment, 2
        b,      // comment, 3
        c       // comment, 4
    };

    enum Odd {
        a = 0,          // hello, world
        b,              // next
        c,              // next
        d = 5, e, f     // inline, from 5
        g               // next
    };
    """
    cs.load(cdef)

    assert cs.Inline.hello == 7
    assert cs.Inline.world == 8
    assert cs.Inline.foo == 9
    assert cs.Inline.bar == 10

    assert cs.Test.a == 2
    assert cs.Test.b == 3
    assert cs.Test.c == 4

    assert cs.Odd.a == 0
    assert cs.Odd.b == 1
    assert cs.Odd.c == 2

    assert cs.Odd.d == 5
    assert cs.Odd.e == 6
    assert cs.Odd.f == 7
    assert cs.Odd.g == 8

    assert cs.Test.a == cs.Test.a
    assert cs.Test.a != cs.Test.b


def test_enum_name(cs: cstruct, compiled: bool) -> None:
    cdef = """
    enum Color: uint16 {
          RED = 1,
          GREEN = 2,
          BLUE = 3,
    };

    struct Pixel {
        uint8 x;
        uint8 y;
        Color color;
        uint32 hue;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.Pixel, compiled)

    Color = cs.Color
    Pixel = cs.Pixel

    pixel = Pixel(b"\xff\x0a\x01\x00\xaa\xbb\xcc\xdd")
    assert pixel.x == 255
    assert pixel.y == 10
    assert pixel.color.name == "RED"
    assert pixel.color.value == Color.RED
    assert pixel.color.value == 1
    assert pixel.hue == 0xDDCCBBAA

    pixel = Pixel(b"\x00\x00\xff\x00\xaa\xbb\xcc\xdd")
    assert pixel.color.name is None
    assert pixel.color.value == 0xFF
    assert repr(pixel.color) == "<Color: 255>"


def test_enum_struct_write(cs: cstruct, compiled: bool) -> None:
    cdef = """
    enum Test16 : uint16 {
        A = 0x1,
        B = 0x2
    };

    enum Test24 : uint24 {
        A = 0x1,
        B = 0x2
    };

    enum Test32 : uint32 {
        A = 0x1,
        B = 0x2
    };

    struct test {
        Test16  a16;
        Test16  b16;
        Test24  a24;
        Test24  b24;
        Test32  a32;
        Test32  b32;
        Test16  list[2];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test()
    obj.a16 = cs.Test16.A
    obj.b16 = cs.Test16.B
    obj.a24 = cs.Test24.A
    obj.b24 = cs.Test24.B
    obj.a32 = cs.Test32.A
    obj.b32 = cs.Test32.B
    obj.list = [cs.Test16.A, cs.Test16.B]

    assert obj.dumps() == b"\x01\x00\x02\x00\x01\x00\x00\x02\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x01\x00\x02\x00"


def test_enum_anonymous(cs: cstruct, compiled: bool) -> None:
    cdef = """
    enum : uint16 {
          RED = 1,
          GREEN = 2,
          BLUE = 3,
    };
    """
    cs.load(cdef, compiled=compiled)

    assert cs.RED == 1
    assert cs.GREEN == 2
    assert cs.BLUE == 3

    assert cs.RED.name == "RED"
    assert cs.RED.value == 1
    assert repr(cs.RED) == "<RED: 1>"
    assert str(cs.RED) == "RED"


def test_enum_anonymous_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    enum : uint32 {
          nElements = 4
    };

    struct test {
        uint32  arr[nElements];
    };
    """
    cs.load(cdef, compiled=compiled)

    test = cs.test

    t = test(b"\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x0a\x00\x00\x00")
    assert t.arr == [255, 0, 0, 10]


def test_enum_reference_own_member(cs: cstruct, compiled: bool) -> None:
    cdef = """
    enum test {
        A,
        B = A + 3,
        C
    };
    """
    cs.load(cdef, compiled=compiled)

    assert cs.test.A == 0
    assert cs.test.B == 3
    assert cs.test.C == 4


def test_enum_default(cs: cstruct) -> None:
    cdef = """
    enum test {
        A,
        B,
    };
    """
    cs.load(cdef)

    assert cs.test.__default__() == cs.test.A == cs.test(0)
    assert cs.test[1].__default__() == [cs.test.A]
    assert cs.test[None].__default__() == []


def test_enum_default_default(cs: cstruct) -> None:
    cdef = """
    enum test {
        default = 0,
    };

    struct test2 {
        test a;
    };
    """
    cs.load(cdef)

    assert cs.test.__default__() == cs.test.default == cs.test(0)
