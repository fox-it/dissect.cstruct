import pytest

from dissect import cstruct

from .utils import verify_compiled


def test_bitfield(compiled):
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
    cs = cstruct.cstruct()
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


def test_bitfield_consecutive(compiled):
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
    cs = cstruct.cstruct()
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


def test_struct_after_bitfield(compiled):
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
    cs = cstruct.cstruct()
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


def test_bitfield_be(compiled):
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
    cs = cstruct.cstruct(endian=">")
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


def test_bitfield_straddle(compiled):
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
    cs = cstruct.cstruct()

    with pytest.raises(ValueError) as exc:
        cs.load(cdef, compiled=compiled)

    assert str(exc.value) == "Straddled bit fields are unsupported"


def test_bitfield_write(compiled):
    cdef = """
    struct test {
        uint16  a:1;
        uint16  b:1;
        uint32  c;
        uint16  d:2;
        uint16  e:3;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    obj = cs.test()
    obj.a = 0b1
    obj.b = 0b1
    obj.c = 0xFF
    obj.d = 0b11
    obj.e = 0b111

    assert obj.dumps() == b"\x03\x00\xff\x00\x00\x00\x1f\x00"


def test_bitfield_write_be(compiled):
    cdef = """
    struct test {
        uint16  a:1;
        uint16  b:1;
        uint32  c;
        uint16  d:2;
        uint16  e:3;
    };
    """
    cs = cstruct.cstruct(endian=">")
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test()
    obj.a = 0b1
    obj.b = 0b1
    obj.c = 0xFF
    obj.d = 0b11
    obj.e = 0b111

    assert obj.dumps() == b"\xc0\x00\x00\x00\x00\xff\xf8\x00"


def test_bitfield_with_enum_or_flag(compiled):
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
    cs = cstruct.cstruct(endian=">")
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\xf0\x00\x30"
    obj = cs.test(buf)

    assert obj.a == 0b1
    assert obj.b == 0b1
    assert obj.c == cs.Flag16.A | cs.Flag16.B
    assert obj.d == cs.Flag8.A | cs.Flag8.B

    assert obj.dumps() == buf
