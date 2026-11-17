from __future__ import annotations

import pytest

from dissect.cstruct import cstruct, util


def test_pack_unpack() -> None:
    endian = "little"
    sign = False
    assert util.p8(1, endian) == b"\x01"
    assert util.p16(1, endian) == b"\x01\x00"
    assert util.p32(1, endian) == b"\x01\x00\x00\x00"
    assert util.p64(1, endian) == b"\x01\x00\x00\x00\x00\x00\x00\x00"
    assert util.pf16(1.0, endian) == b"\x00\x3c"
    assert util.pf32(1.0, endian) == b"\x00\x00\x80\x3f"
    assert util.pf64(1.0, endian) == b"\x00\x00\x00\x00\x00\x00\xf0\x3f"
    assert util.u8(b"\x01", endian, sign) == 1
    assert util.u16(b"\x01\x00", endian, sign) == 1
    assert util.u32(b"\x01\x00\x00\x00", endian, sign) == 1
    assert util.u64(b"\x01\x00\x00\x00\x00\x00\x00\x00", endian, sign) == 1
    assert util.f16(b"\x00\x3c", endian) == 1.0
    assert util.f32(b"\x00\x00\x80\x3f", endian) == 1.0
    assert util.f64(b"\x00\x00\x00\x00\x00\x00\xf0\x3f", endian) == 1.0

    endian = "big"
    sign = False
    assert util.p8(1, endian) == b"\x01"
    assert util.p16(1, endian) == b"\x00\x01"
    assert util.p32(1, endian) == b"\x00\x00\x00\x01"
    assert util.p64(1, endian) == b"\x00\x00\x00\x00\x00\x00\x00\x01"
    assert util.pf16(1.0, endian) == b"\x3c\x00"
    assert util.pf32(1.0, endian) == b"\x3f\x80\x00\x00"
    assert util.pf64(1.0, endian) == b"\x3f\xf0\x00\x00\x00\x00\x00\x00"
    assert util.u8(b"\x01", endian, sign) == 1
    assert util.u16(b"\x00\x01", endian, sign) == 1
    assert util.u32(b"\x00\x00\x00\x01", endian, sign) == 1
    assert util.u64(b"\x00\x00\x00\x00\x00\x00\x00\x01", endian, sign) == 1
    assert util.f16(b"\x3c\x00", endian) == 1.0
    assert util.f32(b"\x3f\x80\x00\x00", endian) == 1.0
    assert util.f64(b"\x3f\xf0\x00\x00\x00\x00\x00\x00", endian) == 1.0

    endian = "network"
    sign = False
    assert util.p8(1, endian) == b"\x01"
    assert util.p16(1, endian) == b"\x00\x01"
    assert util.p32(1, endian) == b"\x00\x00\x00\x01"
    assert util.p64(1, endian) == b"\x00\x00\x00\x00\x00\x00\x00\x01"
    assert util.pf16(1.0, endian) == b"\x3c\x00"
    assert util.pf32(1.0, endian) == b"\x3f\x80\x00\x00"
    assert util.pf64(1.0, endian) == b"\x3f\xf0\x00\x00\x00\x00\x00\x00"
    assert util.u8(b"\x01", endian, sign) == 1
    assert util.u16(b"\x00\x01", endian, sign) == 1
    assert util.u32(b"\x00\x00\x00\x01", endian, sign) == 1
    assert util.u64(b"\x00\x00\x00\x00\x00\x00\x00\x01", endian, sign) == 1
    assert util.f16(b"\x3c\x00", endian) == 1.0
    assert util.f32(b"\x3f\x80\x00\x00", endian) == 1.0
    assert util.f64(b"\x3f\xf0\x00\x00\x00\x00\x00\x00", endian) == 1.0

    endian = "little"
    sign = True
    assert util.p8(-120, endian) == b"\x88"
    assert util.p16(-120, endian) == b"\x88\xff"
    assert util.p32(-120, endian) == b"\x88\xff\xff\xff"
    assert util.p64(-120, endian) == b"\x88\xff\xff\xff\xff\xff\xff\xff"
    assert util.pf16(-120.0, endian) == b"\x80\xd7"
    assert util.pf32(-120.0, endian) == b"\x00\x00\xf0\xc2"
    assert util.pf64(-120.0, endian) == b"\x00\x00\x00\x00\x00\x00\x5e\xc0"
    assert util.u8(b"\x88", endian, sign) == -120
    assert util.u16(b"\x88\xff", endian, sign) == -120
    assert util.u32(b"\x88\xff\xff\xff", endian, sign) == -120
    assert util.u64(b"\x88\xff\xff\xff\xff\xff\xff\xff", endian, sign) == -120
    assert util.f16(b"\x80\xd7", endian) == -120.0
    assert util.f32(b"\x00\x00\xf0\xc2", endian) == -120.0
    assert util.f64(b"\x00\x00\x00\x00\x00\x00\x5e\xc0", endian) == -120.0

    endian = "big"
    sign = True
    assert util.p8(-120, endian) == b"\x88"
    assert util.p16(-120, endian) == b"\xff\x88"
    assert util.p32(-120, endian) == b"\xff\xff\xff\x88"
    assert util.p64(-120, endian) == b"\xff\xff\xff\xff\xff\xff\xff\x88"
    assert util.pf16(-120.0, endian) == b"\xd7\x80"
    assert util.pf32(-120.0, endian) == b"\xc2\xf0\x00\x00"
    assert util.pf64(-120.0, endian) == b"\xc0\x5e\x00\x00\x00\x00\x00\x00"
    assert util.u8(b"\x88", endian, sign) == -120
    assert util.u16(b"\xff\x88", endian, sign) == -120
    assert util.u32(b"\xff\xff\xff\x88", endian, sign) == -120
    assert util.u64(b"\xff\xff\xff\xff\xff\xff\xff\x88", endian, sign) == -120
    assert util.f16(b"\xd7\x80", endian) == -120.0
    assert util.f32(b"\xc2\xf0\x00\x00", endian) == -120.0
    assert util.f64(b"\xc0\x5e\x00\x00\x00\x00\x00\x00", endian) == -120.0

    assert util.pack(1, 24) == b"\x01\x00\x00"
    assert util.unpack(b"\x01\x00\x00", 24) == 1

    assert util.pack(213928798) == b"^K\xc0\x0c"
    assert util.unpack(b"^K\xc0\x0c") == 213928798


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
