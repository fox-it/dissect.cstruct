import pytest

from dissect import cstruct
from dissect.cstruct.types import BytesInteger

from .utils import verify_compiled


def test_bytesinteger_unsigned():
    cs = cstruct.cstruct()

    assert cs.uint24(b"AAA") == 0x414141
    assert cs.uint24(b"\xff\xff\xff") == 0xFFFFFF
    assert cs.uint24[4](b"AAABBBCCCDDD") == [0x414141, 0x424242, 0x434343, 0x444444]
    assert cs.uint48(b"AAAAAA") == 0x414141414141
    assert cs.uint48(b"\xff\xff\xff\xff\xff\xff") == 0xFFFFFFFFFFFF
    assert cs.uint48[4](b"AAAAAABBBBBBCCCCCCDDDDDD") == [0x414141414141, 0x424242424242, 0x434343434343, 0x444444444444]

    uint40 = BytesInteger(cs, "uint40", 5, signed=False)
    assert uint40(b"AAAAA") == 0x4141414141
    assert uint40(b"\xff\xff\xff\xff\xff") == 0xFFFFFFFFFF
    assert uint40[2](b"AAAAABBBBB") == [0x4141414141, 0x4242424242]
    assert uint40[None](b"AAAAA\x00") == [0x4141414141]


def test_bytesinteger_signed():
    cs = cstruct.cstruct()

    assert cs.int24(b"\xff\x00\x00") == 255
    assert cs.int24(b"\xff\xff\xff") == -1
    assert cs.int24[4](b"\xff\xff\xff\xfe\xff\xff\xfd\xff\xff\xfc\xff\xff") == [-1, -2, -3, -4]

    int40 = BytesInteger(cs, "int40", 5, signed=True)
    assert int40(b"AAAAA") == 0x4141414141
    assert int40(b"\xff\xff\xff\xff\xff") == -1
    assert int40[2](b"\xff\xff\xff\xff\xff\xfe\xff\xff\xff\xff") == [-1, -2]


def test_bytesinteger_unsigned_be():
    cs = cstruct.cstruct()
    cs.endian = ">"

    assert cs.uint24(b"\x00\x00\xff") == 255
    assert cs.uint24(b"\xff\xff\xff") == 0xFFFFFF
    assert cs.uint24[3](b"\x00\x00\xff\x00\x00\xfe\x00\x00\xfd") == [255, 254, 253]

    uint40 = BytesInteger(cs, "uint40", 5, signed=False)
    assert uint40(b"\x00\x00\x00\x00\xff") == 255
    assert uint40(b"\xff\xff\xff\xff\xff") == 0xFFFFFFFFFF
    assert uint40[2](b"\x00\x00\x00\x00A\x00\x00\x00\x00B") == [0x41, 0x42]


def test_bytesinteger_signed_be():
    cs = cstruct.cstruct()
    cs.endian = ">"

    assert cs.int24(b"\x00\x00\xff") == 255
    assert cs.int24(b"\xff\xff\x01") == -255
    assert cs.int24[3](b"\xff\xff\x01\xff\xff\x02\xff\xff\x03") == [-255, -254, -253]

    int40 = BytesInteger(cs, "int40", 5, signed=True)
    assert int40(b"\x00\x00\x00\x00\xff") == 255
    assert int40(b"\xff\xff\xff\xff\xff") == -1
    assert int40(b"\xff\xff\xff\xff\x01") == -255
    assert int40[2](b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\xfe") == [-1, -2]


def test_bytesinteger_struct_signed(compiled):
    cdef = """
    struct test {
        int24   a;
        int24   b[2];
        int24   len;
        int24   dync[len];
        int24   c;
        int24   d[3];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"AAABBBCCC\x02\x00\x00DDDEEE\xff\xff\xff\x01\xff\xff\x02\xff\xff\x03\xff\xff"
    obj = cs.test(buf)

    assert obj.a == 0x414141
    assert obj.b == [0x424242, 0x434343]
    assert obj.len == 0x02
    assert obj.dync == [0x444444, 0x454545]
    assert obj.c == -1
    assert obj.d == [-255, -254, -253]
    assert obj.dumps() == buf


def test_bytesinteger_struct_unsigned(compiled):
    cdef = """
    struct test {
        uint24  a;
        uint24  b[2];
        uint24  len;
        uint24  dync[len];
        uint24  c;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"AAABBBCCC\x02\x00\x00DDDEEE\xff\xff\xff"
    obj = cs.test(buf)

    assert obj.a == 0x414141
    assert obj.b == [0x424242, 0x434343]
    assert obj.len == 0x02
    assert obj.dync == [0x444444, 0x454545]
    assert obj.c == 0xFFFFFF
    assert obj.dumps() == buf


def test_bytesinteger_struct_signed_be(compiled):
    cdef = """
    struct test {
        int24   a;
        int24   b[2];
        int24   len;
        int24   dync[len];
        int24   c;
        int24   d[3];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)
    cs.endian = ">"

    assert verify_compiled(cs.test, compiled)

    buf = b"AAABBBCCC\x00\x00\x02DDDEEE\xff\xff\xff\xff\xff\x01\xff\xff\x02\xff\xff\x03"
    obj = cs.test(buf)

    assert obj.a == 0x414141
    assert obj.b == [0x424242, 0x434343]
    assert obj.len == 0x02
    assert obj.dync == [0x444444, 0x454545]
    assert obj.c == -1
    assert obj.d == [-255, -254, -253]
    assert obj.dumps() == buf


def test_bytesinteger_struct_unsigned_be(compiled):
    cdef = """
    struct test {
        uint24  a;
        uint24  b[2];
        uint24  len;
        uint24  dync[len];
        uint24  c;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)
    cs.endian = ">"

    assert verify_compiled(cs.test, compiled)

    buf = b"AAABBBCCC\x00\x00\x02DDDEEE\xff\xff\xff"
    obj = cs.test(buf)

    assert obj.a == 0x414141
    assert obj.b == [0x424242, 0x434343]
    assert obj.len == 0x02
    assert obj.dync == [0x444444, 0x454545]
    assert obj.c == 0xFFFFFF
    assert obj.dumps() == buf


def test_bytesinteger_range():
    cs = cstruct.cstruct()
    int8 = BytesInteger(cs, "int8", 1, signed=True)
    uint8 = BytesInteger(cs, "uint8", 1, signed=False)
    int16 = BytesInteger(cs, "int16", 2, signed=True)
    int24 = BytesInteger(cs, "int24", 3, signed=True)
    int8.dumps(127)
    int8.dumps(-128)
    uint8.dumps(255)
    uint8.dumps(0)
    int16.dumps(-32768)
    int16.dumps(32767)
    int24.dumps(-8388608)
    int24.dumps(8388607)
    with pytest.raises(OverflowError):
        int8.dumps(-129)
    with pytest.raises(OverflowError):
        int8.dumps(128)
    with pytest.raises(OverflowError):
        uint8.dumps(-1)
    with pytest.raises(OverflowError):
        uint8.dumps(256)
    with pytest.raises(OverflowError):
        int16.dumps(-32769)
    with pytest.raises(OverflowError):
        int16.dumps(32768)
    with pytest.raises(OverflowError):
        int24.dumps(-8388609)
    with pytest.raises(OverflowError):
        int24.dumps(8388608)
