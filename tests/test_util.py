from __future__ import annotations

import re
from functools import partial
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct import cstruct, util

if TYPE_CHECKING:
    from collections.abc import Callable

    from dissect.cstruct.cstruct import cstruct


@pytest.mark.parametrize(
    ("pack", "unpack", "endian", "value", "buf"),
    [
        (util.p8, util.u8, "little", 1, b"\x01"),
        (util.p16, util.u16, "little", 1, b"\x01\x00"),
        (util.p32, util.u32, "little", 1, b"\x01\x00\x00\x00"),
        (util.p64, util.u64, "little", 1, b"\x01\x00\x00\x00\x00\x00\x00\x00"),
        (util.p8, util.u8, "big", 1, b"\x01"),
        (util.p16, util.u16, "big", 1, b"\x00\x01"),
        (util.p32, util.u32, "big", 1, b"\x00\x00\x00\x01"),
        (util.p64, util.u64, "big", 1, b"\x00\x00\x00\x00\x00\x00\x00\x01"),
        (util.p8, util.u8, "network", 1, b"\x01"),
        (util.p16, util.u16, "network", 1, b"\x00\x01"),
        (util.p32, util.u32, "network", 1, b"\x00\x00\x00\x01"),
        (util.p64, util.u64, "network", 1, b"\x00\x00\x00\x00\x00\x00\x00\x01"),
        (util.p8, util.u8, "little", -120, b"\x88"),
        (util.p16, util.u16, "little", -120, b"\x88\xff"),
        (util.p32, util.u32, "little", -120, b"\x88\xff\xff\xff"),
        (util.p64, util.u64, "little", -120, b"\x88\xff\xff\xff\xff\xff\xff\xff"),
        (util.p8, util.u8, "big", -120, b"\x88"),
        (util.p16, util.u16, "big", -120, b"\xff\x88"),
        (util.p32, util.u32, "big", -120, b"\xff\xff\xff\x88"),
        (util.p64, util.u64, "big", -120, b"\xff\xff\xff\xff\xff\xff\xff\x88"),
        (partial(util.pack, size=24), partial(util.unpack, size=24), "little", 1, b"\x01\x00\x00"),
        # Without a size, the size of the value is used
        (util.pack, util.unpack, "little", 213928798, b"^K\xc0\x0c"),
    ],
)
def test_pack_unpack(pack: Callable, unpack: Callable, endian: str, value: int, buf: bytes) -> None:
    """Test packing and unpacking integers of different sizes, endianness and signedness."""
    assert pack(value, endian=endian) == buf
    assert unpack(buf, endian=endian, sign=value < 0) == value


@pytest.mark.parametrize(
    ("pack", "unpack", "endian", "value", "buf"),
    [
        (util.pf16, util.f16, "little", 1.0, b"\x00\x3c"),
        (util.pf32, util.f32, "little", 1.0, b"\x00\x00\x80\x3f"),
        (util.pf64, util.f64, "little", 1.0, b"\x00\x00\x00\x00\x00\x00\xf0\x3f"),
        (util.pf16, util.f16, "big", 1.0, b"\x3c\x00"),
        (util.pf32, util.f32, "big", 1.0, b"\x3f\x80\x00\x00"),
        (util.pf64, util.f64, "big", 1.0, b"\x3f\xf0\x00\x00\x00\x00\x00\x00"),
        (util.pf16, util.f16, "network", 1.0, b"\x3c\x00"),
        (util.pf32, util.f32, "network", 1.0, b"\x3f\x80\x00\x00"),
        (util.pf64, util.f64, "network", 1.0, b"\x3f\xf0\x00\x00\x00\x00\x00\x00"),
        (util.pf16, util.f16, "little", -120.0, b"\x80\xd7"),
        (util.pf32, util.f32, "little", -120.0, b"\x00\x00\xf0\xc2"),
        (util.pf64, util.f64, "little", -120.0, b"\x00\x00\x00\x00\x00\x00\x5e\xc0"),
        (util.pf16, util.f16, "big", -120.0, b"\xd7\x80"),
        (util.pf32, util.f32, "big", -120.0, b"\xc2\xf0\x00\x00"),
        (util.pf64, util.f64, "big", -120.0, b"\xc0\x5e\x00\x00\x00\x00\x00\x00"),
    ],
)
def test_pack_unpack_float(pack: Callable, unpack: Callable, endian: str, value: float, buf: bytes) -> None:
    """Test packing and unpacking floats of different sizes and endianness."""
    assert pack(value, endian=endian) == buf
    assert unpack(buf, endian=endian) == value


@pytest.mark.parametrize(
    ("func", "message"),
    [
        (
            lambda: util.normalize_endianness("x"),
            "Invalid endianness: 'x', expected one of <, >, !, @, =, network, little, big",
        ),
        (lambda: util.pack(1, 8, "x"), "Invalid endianness: 'x' (should be little, big, network, <, >, !, @ or =)"),
        (
            lambda: util.unpack(b"\x01", 8, "x"),
            "Invalid endianness: 'x' (should be little, big, network, <, >, !, @ or =)",
        ),
        (lambda: util.unpack(b"\x01", 16), "Invalid byte value, expected 2 bytes, got 1 bytes"),
    ],
)
def test_pack_unpack_invalid(func: Callable, message: str) -> None:
    """Test that an invalid endianness or a value of the wrong size raises an error."""
    with pytest.raises(ValueError, match=re.escape(message)):
        func()


def test_swap() -> None:
    assert util.swap16(0x0001) == 0x0100
    assert util.swap32(0x00000001) == 0x01000000
    assert util.swap64(0x0000000000000001) == 0x0100000000000000


# The offsets of gcc, with and without __attribute__((packed))
@pytest.mark.parametrize(
    ("align", "offsets"),
    [
        (
            True,
            {
                "u1": {"a": 0, "b": 0, "c": 0},
                "s2": {"x": 0, "a": 2, "b": 2, "y": 4},
                "u3": {"a": 0, "b": 4, "c": 0},
                "s4": {"x": 0, "a": 4, "b": 8, "y": 12},
                "s5": {"x": 0, "a": 4, "b": 6, "c": 4},
            },
        ),
        (
            False,
            {
                "u1": {"a": 0, "b": 0, "c": 0},
                "s2": {"x": 0, "a": 1, "b": 1, "y": 3},
                "u3": {"a": 0, "b": 1, "c": 0},
                "s4": {"x": 0, "a": 1, "b": 2, "y": 6},
                "s5": {"x": 0, "a": 1, "b": 2, "c": 1},
            },
        ),
    ],
)
def test_offsetof(align: bool, offsets: dict[str, dict[str, int]]) -> None:
    """Test that offsetof gives the offsets of C, also of union fields and fields of anonymous nested types."""
    cdef = """
    union u1 { uint8 a; uint16 b; uint32 c[2]; };
    struct s2 { uint8 x; union { uint8 a; uint16 b; }; uint8 y; };
    union u3 { struct { uint8 a; uint32 b; }; uint16 c; };
    struct s4 { uint8 x; struct { uint8 a; uint32 b; }; uint8 y; };
    struct s5 { uint8 x; union { struct { uint8 a; uint16 b; }; uint32 c; }; };
    struct dynamic { uint8 n; char d[n]; uint8 e; };
    """
    cs = cstruct().load(cdef, align=align)

    for name, fields in offsets.items():
        assert {field: util.offsetof(cs.resolve(name), field) for field in fields} == fields

    cs = cstruct().load(cdef)

    with pytest.raises(TypeError, match=r"^Type 'uint8' is not a structure$"):
        util.offsetof(cs.uint8, "a")

    with pytest.raises(ValueError, match=r"^Structure 's2' does not have a field named 'z'$"):
        util.offsetof(cs.s2, "z")

    with pytest.raises(ValueError, match=r"^Field 'e' of structure 'dynamic' does not have a known offset$"):
        util.offsetof(cs.dynamic, "e")


def test_offsetof_invalid(cs: cstruct) -> None:
    """Test that the offset of a field that doesn't exist or comes after a dynamic field raises an error."""
    cdef = """
    struct test {
        uint8   size;
        char    data[size];
        uint8   after;
    };
    """
    cs.load(cdef)

    with pytest.raises(ValueError, match=re.escape("Structure 'test' does not have a field named 'missing'")):
        util.offsetof(cs.test, "missing")

    with pytest.raises(ValueError, match=re.escape("Field 'after' of structure 'test' does not have a known offset")):
        util.offsetof(cs.test, "after")
