from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_int_unsigned_read(cs: cstruct) -> None:
    assert cs.uint24(b"AAA") == 0x414141
    assert cs.uint24(b"\xff\xff\xff") == 0xFFFFFF

    assert cs.uint48(b"AAAAAA") == 0x414141414141
    assert cs.uint48(b"\xff\xff\xff\xff\xff\xff") == 0xFFFFFFFFFFFF

    assert cs.uint128(b"A" * 16) == 0x41414141414141414141414141414141
    assert cs.uint128(b"\xff" * 16) == 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF

    uint40 = cs._make_int_type("uint40", 5, False)
    assert uint40(b"AAAAA") == 0x4141414141
    assert uint40(b"\xff\xff\xff\xff\xff") == 0xFFFFFFFFFF


def test_int_unsigned_write(cs: cstruct) -> None:
    assert cs.uint24(0x414141).dumps() == b"AAA"
    assert cs.uint24(0xFFFFFF).dumps() == b"\xff\xff\xff"

    assert cs.uint48(0x414141414141).dumps() == b"AAAAAA"
    assert cs.uint48(0xFFFFFFFFFFFF).dumps() == b"\xff\xff\xff\xff\xff\xff"

    assert cs.uint128(0x41414141414141414141414141414141).dumps() == b"A" * 16
    assert cs.uint128(0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF).dumps() == b"\xff" * 16

    assert cs.uint128(b"A" * 16).dumps() == b"A" * 16

    uint40 = cs._make_int_type("uint40", 5, False)
    assert uint40(0x4141414141).dumps() == b"AAAAA"
    assert uint40(0xFFFFFFFFFF).dumps() == b"\xff\xff\xff\xff\xff"


def test_int_unsigned_array_read(cs: cstruct) -> None:
    assert cs.uint24[4](b"AAABBBCCCDDD") == [0x414141, 0x424242, 0x434343, 0x444444]

    assert cs.uint48[4](b"AAAAAABBBBBBCCCCCCDDDDDD") == [0x414141414141, 0x424242424242, 0x434343434343, 0x444444444444]

    assert cs.uint128[2](b"A" * 16 + b"B" * 16) == [
        0x41414141414141414141414141414141,
        0x42424242424242424242424242424242,
    ]
    assert cs.uint128[None](b"AAAAAAAAAAAAAAAA" + (b"\x00" * 16)) == [0x41414141414141414141414141414141]

    uint40 = cs._make_int_type("uint40", 5, False)
    assert uint40[2](b"AAAAABBBBB") == [0x4141414141, 0x4242424242]
    assert uint40[None](b"AAAAA" + (b"\x00" * 5)) == [0x4141414141]


def test_int_unsigned_array_write(cs: cstruct) -> None:
    assert cs.uint24[4]([0x414141, 0x424242, 0x434343, 0x444444]).dumps() == b"AAABBBCCCDDD"

    assert (
        cs.uint48[4]([0x414141414141, 0x424242424242, 0x434343434343, 0x444444444444]).dumps()
        == b"AAAAAABBBBBBCCCCCCDDDDDD"
    )

    assert (
        cs.uint128[2](
            [
                0x41414141414141414141414141414141,
                0x42424242424242424242424242424242,
            ]
        ).dumps()
        == b"A" * 16 + b"B" * 16
    )
    assert cs.uint128[None]([0x41414141414141414141414141414141]).dumps() == b"AAAAAAAAAAAAAAAA" + (b"\x00" * 16)

    uint40 = cs._make_int_type("uint40", 5, False)
    assert uint40[2]([0x4141414141, 0x4242424242]).dumps() == b"AAAAABBBBB"
    assert uint40[None]([0x4141414141]).dumps() == b"AAAAA" + (b"\x00" * 5)


def test_int_signed_read(cs: cstruct) -> None:
    assert cs.int24(b"\xff\x00\x00") == 255
    assert cs.int24(b"\xff\xff\xff") == -1

    int40 = cs._make_int_type("int40", 5, True)
    assert int40(b"AAAAA") == 0x4141414141
    assert int40(b"\xff\xff\xff\xff\xff") == -1


def test_int_signed_write(cs: cstruct) -> None:
    assert cs.int24(255).dumps() == b"\xff\x00\x00"
    assert cs.int24(-1).dumps() == b"\xff\xff\xff"

    assert cs.int128(0x41414141414141414141414141414141).dumps() == b"A" * 16
    assert cs.int128(-1).dumps() == b"\xff" * 16

    assert cs.int128(b"A" * 16).dumps() == b"A" * 16

    int40 = cs._make_int_type("int40", 5, True)
    assert int40(0x4141414141).dumps() == b"AAAAA"
    assert int40(-1).dumps() == b"\xff\xff\xff\xff\xff"


def test_int_signed_array_read(cs: cstruct) -> None:
    assert cs.int24[4](b"\xff\xff\xff\xfe\xff\xff\xfd\xff\xff\xfc\xff\xff") == [-1, -2, -3, -4]

    assert cs.int128[2](b"\xff" * 16 + b"\xfe" + b"\xff" * 15) == [-1, -2]

    int40 = cs._make_int_type("int40", 5, True)
    assert int40[2](b"\xff\xff\xff\xff\xff\xfe\xff\xff\xff\xff") == [-1, -2]


def test_int_signed_array_write(cs: cstruct) -> None:
    assert cs.int24[4]([-1, -2, -3, -4]).dumps() == b"\xff\xff\xff\xfe\xff\xff\xfd\xff\xff\xfc\xff\xff"
    assert cs.int24[None]([-1]).dumps() == b"\xff\xff\xff\x00\x00\x00"

    assert cs.int128[2]([-1, -2]).dumps() == b"\xff" * 16 + b"\xfe" + b"\xff" * 15

    int40 = cs._make_int_type("int40", 5, True)
    assert int40[2]([-1, -2]).dumps() == b"\xff\xff\xff\xff\xff\xfe\xff\xff\xff\xff"


def test_int_unsigned_be_read(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.uint24(b"\x00\x00\xff") == 255
    assert cs.uint24(b"\xff\xff\xff") == 0xFFFFFF

    assert cs.uint128(b"\x00" * 15 + b"\xff") == 255
    assert cs.uint128(b"\xff" * 16) == 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF

    uint40 = cs._make_int_type("uint40", 5, False)
    assert uint40(b"\x00\x00\x00\x00\xff") == 255
    assert uint40(b"\xff\xff\xff\xff\xff") == 0xFFFFFFFFFF


def test_int_unsigned_be_write(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.uint24(255).dumps() == b"\x00\x00\xff"
    assert cs.uint24(0xFFFFFF).dumps() == b"\xff\xff\xff"

    assert cs.uint128(255).dumps() == b"\x00" * 15 + b"\xff"
    assert cs.uint128(0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF).dumps() == b"\xff" * 16

    uint40 = cs._make_int_type("uint40", 5, False)
    assert uint40(255).dumps() == b"\x00\x00\x00\x00\xff"
    assert uint40(0xFFFFFFFFFF).dumps() == b"\xff\xff\xff\xff\xff"


def test_int_unsigned_be_array_read(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.uint24[3](b"\x00\x00\xff\x00\x00\xfe\x00\x00\xfd") == [255, 254, 253]

    assert cs.uint24[None](b"\x00\x00\xff\x00\x00\x00") == [255]

    assert cs.uint128[2](b"\x00" * 15 + b"A" + b"\x00" * 15 + b"B") == [0x41, 0x42]

    uint40 = cs._make_int_type("uint40", 5, False)
    assert uint40[2](b"\x00\x00\x00\x00A\x00\x00\x00\x00B") == [0x41, 0x42]


def test_int_unsigned_be_array_write(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.uint24[3]([255, 254, 253]).dumps() == b"\x00\x00\xff\x00\x00\xfe\x00\x00\xfd"
    assert cs.uint24[None]([255]).dumps() == b"\x00\x00\xff\x00\x00\x00"

    assert cs.uint128[2]([0x41, 0x42]).dumps() == b"\x00" * 15 + b"A" + b"\x00" * 15 + b"B"

    uint40 = cs._make_int_type("uint40", 5, False)
    assert uint40[2]([0x41, 0x42]).dumps() == b"\x00\x00\x00\x00A\x00\x00\x00\x00B"


def test_int_signed_be_read(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.int24(b"\x00\x00\xff") == 255
    assert cs.int24(b"\xff\xff\x01") == -255

    int40 = cs._make_int_type("int40", 5, True)
    assert int40(b"\x00\x00\x00\x00\xff") == 255
    assert int40(b"\xff\xff\xff\xff\xff") == -1
    assert int40(b"\xff\xff\xff\xff\x01") == -255


def test_int_signed_be_write(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.int24(255).dumps() == b"\x00\x00\xff"
    assert cs.int24(-255).dumps() == b"\xff\xff\x01"

    assert cs.int128(255).dumps() == b"\x00" * 15 + b"\xff"
    assert cs.int128(-1).dumps() == b"\xff" * 16
    assert cs.int128(-255).dumps() == b"\xff" * 15 + b"\x01"

    int40 = cs._make_int_type("int40", 5, True)
    assert int40(255).dumps() == b"\x00\x00\x00\x00\xff"
    assert int40(-1).dumps() == b"\xff\xff\xff\xff\xff"
    assert int40(-255).dumps() == b"\xff\xff\xff\xff\x01"


def test_int_signed_be_array_read(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.int24[3](b"\xff\xff\x01\xff\xff\x02\xff\xff\x03") == [-255, -254, -253]

    assert cs.int128[2](b"\xff" * 16 + b"\xff" * 15 + b"\xfe") == [-1, -2]

    int40 = cs._make_int_type("int40", 5, True)
    assert int40[2](b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\xfe") == [-1, -2]


def test_int_signed_be_array_write(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.int24[3]([-255, -254, -253]).dumps() == b"\xff\xff\x01\xff\xff\x02\xff\xff\x03"

    assert cs.int128[2]([-1, -2]).dumps() == b"\xff" * 16 + b"\xff" * 15 + b"\xfe"

    int40 = cs._make_int_type("int40", 5, True)
    assert int40[2]([-1, -2]).dumps() == b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\xfe"


def test_int_eof(cs: cstruct) -> None:
    with pytest.raises(EOFError):
        cs.int24(b"\x00")

    with pytest.raises(EOFError):
        cs.int24[2](b"\x00\x00\x00")

    with pytest.raises(EOFError):
        cs.int24[None](b"\x01\x00\x00")


def test_int_range(cs: cstruct) -> None:
    int8 = cs._make_int_type("int8", 1, True)
    uint8 = cs._make_int_type("uint9", 1, False)
    int16 = cs._make_int_type("int16", 2, True)
    int24 = cs._make_int_type("int24", 3, True)
    int128 = cs._make_int_type("int128", 16, True)

    int8(127).dumps()
    int8(-128).dumps()
    uint8(255).dumps()
    uint8(0).dumps()
    int16(-32768).dumps()
    int16(32767).dumps()
    int24(-8388608).dumps()
    int24(8388607).dumps()
    int128(-(2**127) + 1).dumps()
    int128(2**127 - 1).dumps()
    with pytest.raises(OverflowError):
        int8(-129).dumps()
    with pytest.raises(OverflowError):
        int8(128).dumps()
    with pytest.raises(OverflowError):
        uint8(-1).dumps()
    with pytest.raises(OverflowError):
        uint8(256).dumps()
    with pytest.raises(OverflowError):
        int16(-32769).dumps()
    with pytest.raises(OverflowError):
        int16(32768).dumps()
    with pytest.raises(OverflowError):
        int24(-8388609).dumps()
    with pytest.raises(OverflowError):
        int24(8388608).dumps()
    with pytest.raises(OverflowError):
        int128(-(2**127) - 1).dumps()
    with pytest.raises(OverflowError):
        int128(2**127).dumps()


def test_int_struct_signed(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        int24   a;
        int24   b[2];
        int24   len;
        int24   dync[len];
        int24   c;
        int24   d[3];
        int128  e;
        int128  f[2];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"AAABBBCCC\x02\x00\x00DDDEEE\xff\xff\xff\x01\xff\xff\x02\xff\xff\x03\xff\xff"
    buf += b"A" * 16
    buf += b"\xff" * 16 + b"\x01" + b"\xff" * 15
    obj = cs.test(buf)

    assert obj.a == 0x414141
    assert obj.b == [0x424242, 0x434343]
    assert obj.len == 0x02
    assert obj.dync == [0x444444, 0x454545]
    assert obj.c == -1
    assert obj.d == [-255, -254, -253]
    assert obj.e == 0x41414141414141414141414141414141
    assert obj.f == [-1, -255]
    assert obj.dumps() == buf


def test_int_struct_unsigned(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint24  a;
        uint24  b[2];
        uint24  len;
        uint24  dync[len];
        uint24  c;
        uint128 d;
        uint128 e[2];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"AAABBBCCC\x02\x00\x00DDDEEE\xff\xff\xff"
    buf += b"A" * 16
    buf += b"A" + b"\x00" * 15 + b"B" + b"\x00" * 15
    obj = cs.test(buf)

    assert obj.a == 0x414141
    assert obj.b == [0x424242, 0x434343]
    assert obj.len == 0x02
    assert obj.dync == [0x444444, 0x454545]
    assert obj.c == 0xFFFFFF
    assert obj.d == 0x41414141414141414141414141414141
    assert obj.e == [0x41, 0x42]
    assert obj.dumps() == buf


def test_int_struct_signed_be(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        int24   a;
        int24   b[2];
        int24   len;
        int24   dync[len];
        int24   c;
        int24   d[3];
        int128  e;
        int128  f[2];
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.endian = ">"

    assert verify_compiled(cs.test, compiled)

    buf = b"AAABBBCCC\x00\x00\x02DDDEEE\xff\xff\xff\xff\xff\x01\xff\xff\x02\xff\xff\x03"
    buf += b"A" * 16
    buf += b"\x00" * 15 + b"A" + b"\x00" * 15 + b"B"
    obj = cs.test(buf)

    assert obj.a == 0x414141
    assert obj.b == [0x424242, 0x434343]
    assert obj.len == 0x02
    assert obj.dync == [0x444444, 0x454545]
    assert obj.c == -1
    assert obj.d == [-255, -254, -253]
    assert obj.e == 0x41414141414141414141414141414141
    assert obj.f == [0x41, 0x42]
    assert obj.dumps() == buf


def test_int_struct_unsigned_be(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint24  a;
        uint24  b[2];
        uint24  len;
        uint24  dync[len];
        uint24  c;
        uint128 d;
        uint128 e[2];
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.endian = ">"

    assert verify_compiled(cs.test, compiled)

    buf = b"AAABBBCCC\x00\x00\x02DDDEEE\xff\xff\xff"
    buf += b"\xff" * 16
    buf += b"\x00" * 14 + b"AA" + b"\x00" * 14 + b"BB"
    obj = cs.test(buf)

    assert obj.a == 0x414141
    assert obj.b == [0x424242, 0x434343]
    assert obj.len == 0x02
    assert obj.dync == [0x444444, 0x454545]
    assert obj.c == 0xFFFFFF
    assert obj.d == 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
    assert obj.e == [0x4141, 0x4242]
    assert obj.dumps() == buf


def test_int_default(cs: cstruct) -> None:
    assert cs.int24.__default__() == 0
    assert cs.uint24.__default__() == 0
    assert cs.int128.__default__() == 0
    assert cs.uint128.__default__() == 0

    assert cs.int24[1].__default__() == [0]
    assert cs.int24[None].__default__() == []
