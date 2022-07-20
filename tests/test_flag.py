from dissect import cstruct

from .utils import verify_compiled


def test_flag():
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
    cs = cstruct.cstruct()
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
    assert bool(cs.Test(0)) is False
    assert bool(cs.Test(1)) is True

    assert cs.Test.a | cs.Test.b == 3
    assert str(cs.Test.c | cs.Test.d) == "Test.d|c"
    assert repr(cs.Test.a | cs.Test.b) == "<Test.b|a: 3>"
    assert cs.Test(2) == cs.Test.b
    assert cs.Test(3) == cs.Test.a | cs.Test.b
    assert cs.Test.c & 12 == cs.Test.c
    assert cs.Test.b & 12 == 0
    assert cs.Test.b ^ cs.Test.a == cs.Test.a | cs.Test.b

    assert ~cs.Test.a == -2
    assert str(~cs.Test.a) == "Test.d|c|b"


def test_flag_read(compiled):
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
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x00\x02\x00\x01\x00\x00\x02\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x01\x00\x02\x00\x03\x00"
    obj = cs.test(buf)

    assert obj.a16.enum == cs.Test16 and obj.a16.value == cs.Test16.A
    assert obj.b16.enum == cs.Test16 and obj.b16.value == cs.Test16.B
    assert obj.a24.enum == cs.Test24 and obj.a24.value == cs.Test24.A
    assert obj.b24.enum == cs.Test24 and obj.b24.value == cs.Test24.B
    assert obj.a32.enum == cs.Test32 and obj.a32.value == cs.Test32.A
    assert obj.b32.enum == cs.Test32 and obj.b32.value == cs.Test32.B

    assert len(obj.l) == 2
    assert obj.l[0].enum == cs.Test16 and obj.l[0].value == cs.Test16.A
    assert obj.l[1].enum == cs.Test16 and obj.l[1].value == cs.Test16.B

    assert obj.c16 == cs.Test16.A | cs.Test16.B
    assert obj.c16 & cs.Test16.A
    assert str(obj.c16) == "Test16.B|A"

    assert obj.dumps() == buf
