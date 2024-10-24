from __future__ import annotations

from enum import Flag as StdFlag
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.types.enum import PY_311

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct
    from dissect.cstruct.types.flag import Flag


@pytest.fixture
def TestFlag(cs: cstruct) -> type[Flag]:
    return cs._make_flag("Test", cs.uint8, {"A": 1, "B": 2})


def test_flag(cs: cstruct, TestFlag: type[Flag]) -> None:
    assert issubclass(TestFlag, StdFlag)
    assert TestFlag.cs is cs
    assert TestFlag.type is cs.uint8
    assert TestFlag.size == 1
    assert TestFlag.alignment == 1

    assert TestFlag.A == 1
    assert TestFlag.B == 2
    assert TestFlag(1) == TestFlag.A
    assert TestFlag(2) == TestFlag.B

    assert TestFlag(0) == 0
    assert TestFlag(0).name is None
    assert TestFlag(0).value == 0


def test_flag_read(TestFlag: type[Flag]) -> None:
    assert TestFlag(b"\x02") == TestFlag.B


def test_flag_write(TestFlag: type[Flag]) -> None:
    assert TestFlag.A.dumps() == b"\x01"
    assert TestFlag(b"\x02").dumps() == b"\x02"


def test_flag_array_read(TestFlag: type[Flag]) -> None:
    assert TestFlag[2](b"\x02\x01") == [TestFlag.B, TestFlag.A]
    assert TestFlag[None](b"\x02\x01\x00") == [TestFlag.B, TestFlag.A]


def test_flag_array_write(TestFlag: type[Flag]) -> None:
    assert TestFlag[2]([TestFlag.B, TestFlag.A]).dumps() == b"\x02\x01"
    assert TestFlag[None]([TestFlag.B, TestFlag.A]).dumps() == b"\x02\x01\x00"


def test_flag_operator(TestFlag: type[Flag]) -> None:
    assert TestFlag.A | TestFlag.B == 3
    assert TestFlag(3) == TestFlag.A | TestFlag.B
    assert isinstance(TestFlag.A | TestFlag.B, TestFlag)

    assert TestFlag(b"\x03") == TestFlag.A | TestFlag.B
    assert TestFlag[2](b"\x02\x03") == [TestFlag.B, (TestFlag.A | TestFlag.B)]

    assert (TestFlag.A | TestFlag.B).dumps() == b"\x03"
    assert TestFlag[2]([TestFlag.B, (TestFlag.A | TestFlag.B)]).dumps() == b"\x02\x03"


def test_flag_str_repr(TestFlag: type[Flag]) -> None:
    if PY_311:
        assert repr(TestFlag.A | TestFlag.B) == "<Test.A|B: 3>"
        assert str(TestFlag.A | TestFlag.B) == "Test.A|B"
        assert repr(TestFlag(69)) == "<Test.A|68: 69>"
        assert str(TestFlag(69)) == "Test.A|68"
    else:
        assert repr(TestFlag.A | TestFlag.B) == "<Test.B|A: 3>"
        assert str(TestFlag.A | TestFlag.B) == "Test.B|A"
        assert repr(TestFlag(69)) == "<Test.64|4|A: 69>"
        assert str(TestFlag(69)) == "Test.64|4|A"


def test_flag_str_repr_in_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    flag Test : uint16 {
        A,
        B
    };

    struct test {
        Test    a;
    };
    """
    cs.load(cdef, compiled=compiled)

    obj = cs.test(b"\x03\x00")

    if PY_311:
        assert repr(obj) == "<test a=<Test.A|B: 3>>"
        assert str(obj) == "<test a=<Test.A|B: 3>>"
    else:
        assert repr(obj) == "<test a=<Test.B|A: 3>>"
        assert str(obj) == "<test a=<Test.B|A: 3>>"


def test_flag_struct(cs: cstruct) -> None:
    cdef = """
    flag Test {
        a,
        b,
        c,
        d
    };

    flag Odd {
        a = 2,
        b,
        c,
        d = 32, e, f,
        g
    };
    """
    cs.load(cdef)

    assert cs.Test.a == 1
    assert cs.Test.b == 2
    assert cs.Test.c == 4
    assert cs.Test.d == 8

    assert cs.Odd.a == 2
    assert cs.Odd.b == 4
    assert cs.Odd.c == 8
    assert cs.Odd.d == 32
    assert cs.Odd.e == 64
    assert cs.Odd.f == 128
    assert cs.Odd.g == 256

    assert cs.Test.a == cs.Test.a
    assert cs.Test.a != cs.Test.b
    assert cs.Test.b != cs.Odd.a
    assert bool(cs.Test(0)) is False
    assert bool(cs.Test(1)) is True

    assert cs.Test.a | cs.Test.b == 3
    assert cs.Test(2) == cs.Test.b
    assert cs.Test(3) == cs.Test.a | cs.Test.b
    assert cs.Test.c & 12 == cs.Test.c
    assert cs.Test.b & 12 == 0
    assert cs.Test.b ^ cs.Test.a == cs.Test.a | cs.Test.b

    # TODO: determine if we want to stay true to Python stdlib or a consistent behaviour
    if PY_311:
        assert ~cs.Test.a == 14
        assert repr(~cs.Test.a) == "<Test.b|c|d: 14>"
    else:
        assert ~cs.Test.a == -2
        assert repr(~cs.Test.a) == "<Test.d|c|b: -2>"


def test_flag_struct_read(cs: cstruct, compiled: bool) -> None:
    cdef = """
    flag Test16 : uint16 {
        A = 0x1,
        B = 0x2
    };

    flag Test24 : uint24 {
        A = 0x1,
        B = 0x2
    };

    flag Test32 : uint32 {
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
        Test16  l[2];
        Test16  c16;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x00\x02\x00\x01\x00\x00\x02\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x01\x00\x02\x00\x03\x00"
    obj = cs.test(buf)

    assert isinstance(obj.a16, cs.Test16)
    assert obj.a16.value == cs.Test16.A
    assert isinstance(obj.b16, cs.Test16)
    assert obj.b16.value == cs.Test16.B
    assert isinstance(obj.a24, cs.Test24)
    assert obj.a24.value == cs.Test24.A
    assert isinstance(obj.b24, cs.Test24)
    assert obj.b24.value == cs.Test24.B
    assert isinstance(obj.a32, cs.Test32)
    assert obj.a32.value == cs.Test32.A
    assert isinstance(obj.b32, cs.Test32)
    assert obj.b32.value == cs.Test32.B

    assert len(obj.l) == 2
    assert isinstance(obj.l[0], cs.Test16)
    assert obj.l[0].value == cs.Test16.A
    assert isinstance(obj.l[1], cs.Test16)
    assert obj.l[1].value == cs.Test16.B

    assert obj.c16 == cs.Test16.A | cs.Test16.B
    assert obj.c16 & cs.Test16.A
    if PY_311:
        assert repr(obj.c16) == "<Test16.A|B: 3>"
    else:
        assert repr(obj.c16) == "<Test16.B|A: 3>"

    assert obj.dumps() == buf


def test_flag_anonymous(cs: cstruct, compiled: bool) -> None:
    cdef = """
    flag : uint16 {
          A,
          B,
          C,
    };
    """
    cs.load(cdef, compiled=compiled)

    assert cs.A == 1
    assert cs.B == 2
    assert cs.C == 4

    assert cs.A.name == "A"
    assert cs.A.value == 1
    assert repr(cs.A) == "<A: 1>"
    assert str(cs.A) == "A"

    if PY_311:
        assert repr(cs.A | cs.B) == "<A|B: 3>"
        assert str(cs.A | cs.B) == "A|B"
        assert repr(cs.A.__class__(69)) == "<A|C|64: 69>"
        assert str(cs.A.__class__(69)) == "A|C|64"
    else:
        assert repr(cs.A | cs.B) == "<B|A: 3>"
        assert str(cs.A | cs.B) == "B|A"
        assert repr(cs.A.__class__(69)) == "<64|C|A: 69>"
        assert str(cs.A.__class__(69)) == "64|C|A"


def test_flag_anonymous_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    flag : uint32 {
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


def test_flag_default(cs: cstruct) -> None:
    cdef = """
    flag test {
        A,
        B,
    };
    """
    cs.load(cdef)

    assert cs.test.__default__() == cs.test(0)
    assert cs.test[1].__default__() == [cs.test(0)]
    assert cs.test[None].__default__() == []
