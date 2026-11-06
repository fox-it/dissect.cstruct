from __future__ import annotations

from dissect.cstruct import util


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
