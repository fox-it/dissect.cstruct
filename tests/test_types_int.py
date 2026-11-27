from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.exception import WriteError
from tests.util import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


@pytest.fixture
def cs_int40(cs: cstruct) -> cstruct:
    cs.add_type("uint40", cs._make_int_type("uint40", 5, False))
    cs.add_type("int40", cs._make_int_type("int40", 5, True))
    return cs


@pytest.mark.parametrize(
    ("endian", "type_name", "buf", "value"),
    [
        ("<", "uint24", b"AAA", 0x414141),
        ("<", "uint24", b"\xff\xff\xff", 0xFFFFFF),
        ("<", "uint48", b"AAAAAA", 0x414141414141),
        ("<", "uint48", b"\xff\xff\xff\xff\xff\xff", 0xFFFFFFFFFFFF),
        ("<", "uint128", b"A" * 16, 0x41414141414141414141414141414141),
        ("<", "uint128", b"\xff" * 16, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF),
        ("<", "uint40", b"AAAAA", 0x4141414141),
        ("<", "uint40", b"\xff\xff\xff\xff\xff", 0xFFFFFFFFFF),
        ("<", "int24", b"\xff\x00\x00", 255),
        ("<", "int24", b"\xff\xff\xff", -1),
        ("<", "int128", b"A" * 16, 0x41414141414141414141414141414141),
        ("<", "int128", b"\xff" * 16, -1),
        ("<", "int40", b"AAAAA", 0x4141414141),
        ("<", "int40", b"\xff\xff\xff\xff\xff", -1),
        (">", "uint24", b"\x00\x00\xff", 255),
        (">", "uint24", b"\xff\xff\xff", 0xFFFFFF),
        (">", "uint128", b"\x00" * 15 + b"\xff", 255),
        (">", "uint128", b"\xff" * 16, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF),
        (">", "uint40", b"\x00\x00\x00\x00\xff", 255),
        (">", "uint40", b"\xff\xff\xff\xff\xff", 0xFFFFFFFFFF),
        (">", "int24", b"\x00\x00\xff", 255),
        (">", "int24", b"\xff\xff\x01", -255),
        (">", "int128", b"\x00" * 15 + b"\xff", 255),
        (">", "int128", b"\xff" * 16, -1),
        (">", "int128", b"\xff" * 15 + b"\x01", -255),
        (">", "int40", b"\x00\x00\x00\x00\xff", 255),
        (">", "int40", b"\xff\xff\xff\xff\xff", -1),
        (">", "int40", b"\xff\xff\xff\xff\x01", -255),
    ],
)
def test_int_read_write(cs_int40: cstruct, endian: str, type_name: str, buf: bytes, value: int) -> None:
    """Test reading and writing ``Int`` types of different sizes, signedness and endianness."""
    cs_int40.endian = endian
    int_type = cs_int40.resolve(type_name)

    assert int_type(buf) == value
    assert bytes(int_type(value)) == buf


@pytest.mark.parametrize(
    ("endian", "type_name", "count", "buf", "values"),
    [
        ("<", "uint24", 4, b"AAABBBCCCDDD", [0x414141, 0x424242, 0x434343, 0x444444]),
        (
            "<",
            "uint48",
            4,
            b"AAAAAABBBBBBCCCCCCDDDDDD",
            [0x414141414141, 0x424242424242, 0x434343434343, 0x444444444444],
        ),
        (
            "<",
            "uint128",
            2,
            b"A" * 16 + b"B" * 16,
            [0x41414141414141414141414141414141, 0x42424242424242424242424242424242],
        ),
        ("<", "uint128", None, b"A" * 16 + b"\x00" * 16, [0x41414141414141414141414141414141]),
        ("<", "uint40", 2, b"AAAAABBBBB", [0x4141414141, 0x4242424242]),
        ("<", "uint40", None, b"AAAAA" + b"\x00" * 5, [0x4141414141]),
        ("<", "int24", 4, b"\xff\xff\xff\xfe\xff\xff\xfd\xff\xff\xfc\xff\xff", [-1, -2, -3, -4]),
        ("<", "int24", None, b"\xff\xff\xff\x00\x00\x00", [-1]),
        ("<", "int128", 2, b"\xff" * 16 + b"\xfe" + b"\xff" * 15, [-1, -2]),
        ("<", "int40", 2, b"\xff\xff\xff\xff\xff\xfe\xff\xff\xff\xff", [-1, -2]),
        (">", "uint24", 3, b"\x00\x00\xff\x00\x00\xfe\x00\x00\xfd", [255, 254, 253]),
        (">", "uint24", None, b"\x00\x00\xff\x00\x00\x00", [255]),
        (">", "uint128", 2, b"\x00" * 15 + b"A" + b"\x00" * 15 + b"B", [0x41, 0x42]),
        (">", "uint40", 2, b"\x00\x00\x00\x00A\x00\x00\x00\x00B", [0x41, 0x42]),
        (">", "int24", 3, b"\xff\xff\x01\xff\xff\x02\xff\xff\x03", [-255, -254, -253]),
        (">", "int128", 2, b"\xff" * 16 + b"\xff" * 15 + b"\xfe", [-1, -2]),
        (">", "int40", 2, b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\xfe", [-1, -2]),
    ],
)
def test_int_array_read_write(
    cs_int40: cstruct, endian: str, type_name: str, count: int | None, buf: bytes, values: list[int]
) -> None:
    """Test reading and writing fixed size and null-terminated arrays of ``Int`` types."""
    cs_int40.endian = endian
    int_type = cs_int40.resolve(type_name)

    result = int_type[count](buf)
    assert result == values
    assert [type(value) for value in result] == [int_type] * len(values)
    assert int_type[count].dumps(values) == buf


def test_int_eof(cs: cstruct) -> None:
    with pytest.raises(EOFError, match="Read 1 bytes, but expected 3"):
        cs.int24(b"\x00")

    with pytest.raises(EOFError, match="Read 0 bytes, but expected 3"):
        cs.int24[2](b"\x00\x00\x00")

    with pytest.raises(EOFError, match="Read 1 bytes, but expected 3"):
        cs.int24[2](b"\x00\x00\x00\x00")

    with pytest.raises(EOFError, match="Read 0 bytes, but expected 3"):
        cs.int24[None](b"\x01\x00\x00")

    # More bytes than any stream can hold, e.g. a count from corrupt data
    with pytest.raises(EOFError, match=r"^Read 0 bytes, but expected 13835058055282163712$"):
        cs.int24[2**62](b"")


@pytest.mark.parametrize(
    ("size", "signed", "value", "buf"),
    [
        (1, True, -128, b"\x80"),
        (1, True, 127, b"\x7f"),
        (1, False, 0, b"\x00"),
        (1, False, 255, b"\xff"),
        (2, True, -32768, b"\x00\x80"),
        (2, True, 32767, b"\xff\x7f"),
        (3, True, -8388608, b"\x00\x00\x80"),
        (3, True, 8388607, b"\xff\xff\x7f"),
        (16, True, -(2**127), b"\x00" * 15 + b"\x80"),
        (16, True, 2**127 - 1, b"\xff" * 15 + b"\x7f"),
    ],
)
def test_int_range(cs: cstruct, size: int, signed: bool, value: int, buf: bytes) -> None:
    """Test that the lowest and highest value of an ``Int`` type are written."""
    int_type = cs._make_int_type("test", size, signed)
    assert bytes(int_type(value)) == buf


@pytest.mark.parametrize(
    ("size", "signed", "value"),
    [
        (1, True, -129),
        (1, True, 128),
        (1, False, -1),
        (1, False, 256),
        (2, True, -32769),
        (2, True, 32768),
        (3, True, -8388609),
        (3, True, 8388608),
        (16, True, -(2**127) - 1),
        (16, True, 2**127),
    ],
)
def test_int_range_overflow(cs: cstruct, size: int, signed: bool, value: int) -> None:
    """Test that a value outside the range of an ``Int`` type raises an error when writing it."""
    int_type = cs._make_int_type("test", size, signed)
    with pytest.raises(WriteError, match=r"^Cannot write test: "):
        bytes(int_type(value))


@pytest.mark.parametrize(
    ("endian", "buf", "values"),
    [
        (
            "<",
            b"AAABBBCCC\x02\x00\x00DDDEEE\xff\xff\xff\x01\xff\xff\x02\xff\xff\x03\xff\xff"
            + b"A" * 16
            + b"\xff" * 16
            + b"\x01"
            + b"\xff" * 15,
            {
                "a": 0x414141,
                "b": [0x424242, 0x434343],
                "len": 0x02,
                "dync": [0x444444, 0x454545],
                "c": -1,
                "d": [-255, -254, -253],
                "e": 0x41414141414141414141414141414141,
                "f": [-1, -255],
            },
        ),
        (
            ">",
            b"AAABBBCCC\x00\x00\x02DDDEEE\xff\xff\xff\xff\xff\x01\xff\xff\x02\xff\xff\x03"
            + b"A" * 16
            + b"\x00" * 15
            + b"A"
            + b"\x00" * 15
            + b"B",
            {
                "a": 0x414141,
                "b": [0x424242, 0x434343],
                "len": 0x02,
                "dync": [0x444444, 0x454545],
                "c": -1,
                "d": [-255, -254, -253],
                "e": 0x41414141414141414141414141414141,
                "f": [0x41, 0x42],
            },
        ),
    ],
)
def test_int_struct_signed(cs: cstruct, compiled: bool, endian: str, buf: bytes, values: dict) -> None:
    """Test reading and writing signed ``Int`` types in a structure, also in fixed size and dynamic arrays."""
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
    cs.endian = endian

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(buf)
    assert dict(obj.__values__) == values
    assert bytes(obj) == buf


@pytest.mark.parametrize(
    ("endian", "buf", "values"),
    [
        (
            "<",
            b"AAABBBCCC\x02\x00\x00DDDEEE\xff\xff\xff" + b"A" * 16 + b"A" + b"\x00" * 15 + b"B" + b"\x00" * 15,
            {
                "a": 0x414141,
                "b": [0x424242, 0x434343],
                "len": 0x02,
                "dync": [0x444444, 0x454545],
                "c": 0xFFFFFF,
                "d": 0x41414141414141414141414141414141,
                "e": [0x41, 0x42],
            },
        ),
        (
            ">",
            b"AAABBBCCC\x00\x00\x02DDDEEE\xff\xff\xff" + b"\xff" * 16 + b"\x00" * 14 + b"AA" + b"\x00" * 14 + b"BB",
            {
                "a": 0x414141,
                "b": [0x424242, 0x434343],
                "len": 0x02,
                "dync": [0x444444, 0x454545],
                "c": 0xFFFFFF,
                "d": 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF,
                "e": [0x4141, 0x4242],
            },
        ),
    ],
)
def test_int_struct_unsigned(cs: cstruct, compiled: bool, endian: str, buf: bytes, values: dict) -> None:
    """Test reading and writing unsigned ``Int`` types in a structure, also in fixed size and dynamic arrays."""
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
    cs.endian = endian

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(buf)
    assert dict(obj.__values__) == values
    assert bytes(obj) == buf


def test_int_default(cs: cstruct) -> None:
    assert cs.int24.__default__() == 0
    assert cs.uint24.__default__() == 0
    assert cs.int128.__default__() == 0
    assert cs.uint128.__default__() == 0

    assert cs.int24[1].__default__() == [0]
    assert cs.int24[None].__default__() == []


def test_int_struct_write_range(cs: cstruct, compiled: bool) -> None:
    """Test that a value that doesn't fit its ``Int`` type raises an error when writing a structure, also in arrays."""
    cdef = """
    struct test {
        uint24  a;
        int24   b;
        uint24  c[2];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert bytes(cs.test(a=1, b=-2, c=[3, 4])) == b"\x01\x00\x00\xfe\xff\xff\x03\x00\x00\x04\x00\x00"

    with pytest.raises(WriteError, match=r"^Cannot write test: "):
        bytes(cs.test(a=1, b=2**23, c=[3, 4]))

    # A negative value only fits a signed type
    with pytest.raises(WriteError, match=r"^Cannot write test: "):
        bytes(cs.test(a=-1, b=2, c=[3, 4]))

    with pytest.raises(WriteError, match=r"^Cannot write test: "):
        bytes(cs.test(a=1, b=2, c=[3, 2**24]))
