from __future__ import annotations

from dissect.cstruct import util


def test_pack_unpack() -> None:
    endian = "little"
    sign = False
    assert util.p8(1, endian) == b"\x01"
    assert util.p16(1, endian) == b"\x01\x00"
    assert util.p32(1, endian) == b"\x01\x00\x00\x00"
    assert util.p64(1, endian) == b"\x01\x00\x00\x00\x00\x00\x00\x00"
    assert util.u8(b"\x01", endian, sign) == 1
    assert util.u16(b"\x01\x00", endian, sign) == 1
    assert util.u32(b"\x01\x00\x00\x00", endian, sign) == 1
    assert util.u64(b"\x01\x00\x00\x00\x00\x00\x00\x00", endian, sign) == 1

    endian = "big"
    sign = False
    assert util.p8(1, endian) == b"\x01"
    assert util.p16(1, endian) == b"\x00\x01"
    assert util.p32(1, endian) == b"\x00\x00\x00\x01"
    assert util.p64(1, endian) == b"\x00\x00\x00\x00\x00\x00\x00\x01"
    assert util.u8(b"\x01", endian, sign) == 1
    assert util.u16(b"\x00\x01", endian, sign) == 1
    assert util.u32(b"\x00\x00\x00\x01", endian, sign) == 1
    assert util.u64(b"\x00\x00\x00\x00\x00\x00\x00\x01", endian, sign) == 1

    endian = "network"
    sign = False
    assert util.p8(1, endian) == b"\x01"
    assert util.p16(1, endian) == b"\x00\x01"
    assert util.p32(1, endian) == b"\x00\x00\x00\x01"
    assert util.p64(1, endian) == b"\x00\x00\x00\x00\x00\x00\x00\x01"
    assert util.u8(b"\x01", endian, sign) == 1
    assert util.u16(b"\x00\x01", endian, sign) == 1
    assert util.u32(b"\x00\x00\x00\x01", endian, sign) == 1
    assert util.u64(b"\x00\x00\x00\x00\x00\x00\x00\x01", endian, sign) == 1

    endian = "little"
    sign = True
    assert util.p8(-120, endian) == b"\x88"
    assert util.p16(-120, endian) == b"\x88\xff"
    assert util.p32(-120, endian) == b"\x88\xff\xff\xff"
    assert util.p64(-120, endian) == b"\x88\xff\xff\xff\xff\xff\xff\xff"
    assert util.u8(b"\x88", endian, sign) == -120
    assert util.u16(b"\x88\xff", endian, sign) == -120
    assert util.u32(b"\x88\xff\xff\xff", endian, sign) == -120
    assert util.u64(b"\x88\xff\xff\xff\xff\xff\xff\xff", endian, sign) == -120

    endian = "big"
    sign = True
    assert util.p8(-120, endian) == b"\x88"
    assert util.p16(-120, endian) == b"\xff\x88"
    assert util.p32(-120, endian) == b"\xff\xff\xff\x88"
    assert util.p64(-120, endian) == b"\xff\xff\xff\xff\xff\xff\xff\x88"
    assert util.u8(b"\x88", endian, sign) == -120
    assert util.u16(b"\xff\x88", endian, sign) == -120
    assert util.u32(b"\xff\xff\xff\x88", endian, sign) == -120
    assert util.u64(b"\xff\xff\xff\xff\xff\xff\xff\x88", endian, sign) == -120

    assert util.pack(1, 24) == b"\x01\x00\x00"
    assert util.unpack(b"\x01\x00\x00", 24) == 1

    assert util.pack(213928798) == b"^K\xc0\x0c"
    assert util.unpack(b"^K\xc0\x0c") == 213928798


def test_swap() -> None:
    assert util.swap16(0x0001) == 0x0100
    assert util.swap32(0x00000001) == 0x01000000
    assert util.swap64(0x0000000000000001) == 0x0100000000000000
