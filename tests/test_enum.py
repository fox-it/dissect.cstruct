import pytest

from dissect import cstruct

from .utils import verify_compiled


def test_enum(compiled):
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
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert verify_compiled(cs.test_term, compiled)
    assert verify_compiled(cs.test_expr, compiled)

    buf = b"\x01\x00\x02\x00\x01\x00\x00\x02\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x01\x00\x02\x00"
    obj = cs.test(buf)

    assert obj.a16.enum == cs.Test16 and obj.a16 == cs.Test16.A
    assert obj.b16.enum == cs.Test16 and obj.b16 == cs.Test16.B
    assert obj.a24.enum == cs.Test24 and obj.a24 == cs.Test24.A
    assert obj.b24.enum == cs.Test24 and obj.b24 == cs.Test24.B
    assert obj.a32.enum == cs.Test32 and obj.a32 == cs.Test32.A
    assert obj.b32.enum == cs.Test32 and obj.b32 == cs.Test32.B

    assert len(obj.l) == 2
    assert obj.l[0].enum == cs.Test16 and obj.l[0] == cs.Test16.A
    assert obj.l[1].enum == cs.Test16 and obj.l[1] == cs.Test16.B

    assert "A" in cs.Test16
    assert "Foo" not in cs.Test16
    assert cs.Test16(1) == cs.Test16["A"]
    assert cs.Test24(2) == cs.Test24.B
    assert cs.Test16.A != cs.Test24.A

    with pytest.raises(KeyError):
        cs.Test16["C"]

    with pytest.raises(AttributeError):
        cs.Test16.C

    assert obj.dumps() == buf

    buf = b"\x01\x00\x02\x00\x00\x00"
    assert cs.test_term(buf).null == [cs.Test16.A, cs.Test16.B]
    assert cs.test_term(null=[cs.Test16.A, cs.Test16.B]).dumps() == buf

    buf = b"\x01\x00\x01\x00\x02\x00"
    assert cs.test_expr(buf).expr == [cs.Test16.A, cs.Test16.B]
    assert cs.test_expr(size=1, expr=[cs.Test16.A, cs.Test16.B]).dumps() == buf

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


def test_enum_comments():
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
    cs = cstruct.cstruct()
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


def test_enum_name(compiled):
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
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.Pixel, compiled)

    Color = cs.Color
    Pixel = cs.Pixel

    pixel = Pixel(b"\xFF\x0A\x01\x00\xAA\xBB\xCC\xDD")
    assert pixel.x == 255
    assert pixel.y == 10
    assert pixel.color.name == "RED"
    assert pixel.color.value == Color.RED
    assert pixel.color.value == 1
    assert pixel.hue == 0xDDCCBBAA

    # unknown enum values default to <enum name>_<value>
    pixel = Pixel(b"\x00\x00\xFF\x00\xAA\xBB\xCC\xDD")
    assert pixel.color.name == "Color_255"
    assert pixel.color.value == 0xFF


def test_enum_write(compiled):
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
    cs = cstruct.cstruct()
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
