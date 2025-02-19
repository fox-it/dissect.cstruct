from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_bitfield(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint16  a:4;
        uint16  b:4;
        uint16  c:4;
        uint16  d:4;
        uint32  e;
        uint16  f:2;
        uint16  g:3;
        uint32  h;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert len(cs.test) == 12

    buf = b"\x12\x34\xff\x00\x00\x00\x1f\x00\x01\x00\x00\x00"
    obj = cs.test(buf)

    assert obj.a == 0b10
    assert obj.b == 0b01
    assert obj.c == 0b100
    assert obj.d == 0b011
    assert obj.e == 0xFF
    assert obj.f == 0b11
    assert obj.g == 0b111
    assert obj.h == 1
    assert obj.dumps() == buf


def test_bitfield_consecutive(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint16  a:4;
        uint16  b:4;
        uint16  c:4;
        uint16  d:4;
        uint16  e:16;
        uint16  _pad1;
        uint16  f:2;
        uint16  g:3;
        uint16  h:11;
        uint16  _pad2;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert len(cs.test) == 10

    buf = b"\x12\x34\xff\x00\x00\x00\x1f\x01\x00\x00"
    obj = cs.test(buf)

    assert obj.a == 0b10
    assert obj.b == 0b01
    assert obj.c == 0b100
    assert obj.d == 0b011
    assert obj.e == 0xFF
    assert obj.f == 0b11
    assert obj.g == 0b111
    assert obj.h == 0b1000
    assert obj.dumps() == buf


def test_struct_after_bitfield(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint16  a:4;
        uint16  b:4;
        uint32  c;
        struct {
            uint32 d;
        } nested1;
        uint16  e:4;
        uint16  f:4;
        struct {
            uint32 g;
        } nested2;
        uint32  h;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert len(cs.test) == 20

    buf = b"\x12\x00\xff\x00\x00\x00\x01\x00\x00\x00\x12\x00\x02\x00\x00\x00\xfe\x00\x00\x00"
    obj = cs.test(buf)

    assert obj.a == 0b10
    assert obj.b == 0b01
    assert obj.c == 0xFF
    assert obj.nested1.d == 0x01
    assert obj.e == 0b10
    assert obj.f == 0b01
    assert obj.nested2.g == 0x02
    assert obj.h == 0xFE
    assert obj.dumps() == buf


def test_bitfield_be(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint16  a:4;
        uint16  b:4;
        uint16  c:4;
        uint16  d:4;
        uint32  e;
        uint16  f:2;
        uint16  g:3;
        uint16  h:4;
        uint32  i;
    };
    """
    cs.endian = ">"
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert len(cs.test) == 12

    buf = b"\x12\x34\x00\x00\x00\xff\x1f\x00\x00\x00\x00\x01"
    obj = cs.test(buf)

    assert obj.a == 0b01
    assert obj.b == 0b10
    assert obj.c == 0b011
    assert obj.d == 0b100
    assert obj.e == 0xFF
    assert obj.f == 0
    assert obj.g == 0b11
    assert obj.h == 0b1110
    assert obj.i == 1
    assert obj.dumps() == buf


def test_bitfield_straddle(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint16  a:12;
        uint16  b:12;
        uint16  c:8;
        uint32  d;
        uint16  e:2;
        uint16  f:3;
        uint32  g;
    };
    """

    with pytest.raises(ValueError, match="Straddled bit fields are unsupported"):
        cs.load(cdef, compiled=compiled)


def test_bitfield_write(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint16  a:1;
        uint16  b:1;
        uint32  c;
        uint16  d:2;
        uint16  e:3;
    };
    """
    cs.load(cdef, compiled=compiled)

    obj = cs.test()
    obj.a = 0b1
    obj.b = 0b1
    obj.c = 0xFF
    obj.d = 0b11
    obj.e = 0b111

    assert obj.dumps() == b"\x03\x00\xff\x00\x00\x00\x1f\x00"


def test_bitfield_write_be(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint16  a:1;
        uint16  b:1;
        uint32  c;
        uint16  d:2;
        uint16  e:3;
    };
    """
    cs.endian = ">"
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test()
    obj.a = 0b1
    obj.b = 0b1
    obj.c = 0xFF
    obj.d = 0b11
    obj.e = 0b111

    assert obj.dumps() == b"\xc0\x00\x00\x00\x00\xff\xf8\x00"


def test_bitfield_with_enum_or_flag(cs: cstruct, compiled: bool) -> None:
    cdef = """
    flag Flag8 : uint8 {
        A = 1,
        B = 2
    };

    flag Flag16 : uint16 {
        A = 1,
        B = 2
    };

    struct test {
        uint16  a:1;
        uint16  b:1;
        Flag16  c:2;
        Flag8   d:4;
    };
    """
    cs.endian = ">"
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\xf0\x00\x30"
    obj = cs.test(buf)

    assert obj.a == 0b1
    assert obj.b == 0b1
    assert obj.c == cs.Flag16.A | cs.Flag16.B
    assert obj.d == cs.Flag8.A | cs.Flag8.B

    assert obj.dumps() == buf


def test_bitfield_char(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint16  a : 4;
        uint16  b : 4;
        char    c : 8;
        char    d[4];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x12\x00\xff\x69420"
    obj = cs.test(buf)

    assert obj.a == 0b10
    assert obj.b == 0b1
    assert obj.c == 0b11111111
    assert obj.d == b"i420"

    assert obj.dumps() == buf


def test_bitfield_dynamic(cs: cstruct, compiled: bool) -> None:
    cdef = """
    enum A : uint16 {
        A = 0x0
    };

    struct test {
        uint16  size : 4;
        A       b : 4;
        char    d[size];
    };
    """

    cs.load(cdef, compiled=compiled)
    assert verify_compiled(cs.test, compiled)

    buf = io.BytesIO(b"\x00\x00\xf4\x00help")
    buf.seek(2)
    obj = cs.test(buf)

    assert obj.size == 4
    assert obj.b == 0xF
    assert obj.d == b"help"

    buf.seek(2)
    assert obj.dumps() == buf.read()
