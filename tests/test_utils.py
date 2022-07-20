from dissect.cstruct import utils


def test_pack_unpack():
    endian = "little"
    sign = False
    assert utils.p8(1, endian) == b"\x01"
    assert utils.p16(1, endian) == b"\x01\x00"
    assert utils.p32(1, endian) == b"\x01\x00\x00\x00"
    assert utils.p64(1, endian) == b"\x01\x00\x00\x00\x00\x00\x00\x00"
    assert utils.u8(b"\x01", endian, sign) == 1
    assert utils.u16(b"\x01\x00", endian, sign) == 1
    assert utils.u32(b"\x01\x00\x00\x00", endian, sign) == 1
    assert utils.u64(b"\x01\x00\x00\x00\x00\x00\x00\x00", endian, sign) == 1

    endian = "big"
    sign = False
    assert utils.p8(1, endian) == b"\x01"
    assert utils.p16(1, endian) == b"\x00\x01"
    assert utils.p32(1, endian) == b"\x00\x00\x00\x01"
    assert utils.p64(1, endian) == b"\x00\x00\x00\x00\x00\x00\x00\x01"
    assert utils.u8(b"\x01", endian, sign) == 1
    assert utils.u16(b"\x00\x01", endian, sign) == 1
    assert utils.u32(b"\x00\x00\x00\x01", endian, sign) == 1
    assert utils.u64(b"\x00\x00\x00\x00\x00\x00\x00\x01", endian, sign) == 1

    endian = "network"
    sign = False
    assert utils.p8(1, endian) == b"\x01"
    assert utils.p16(1, endian) == b"\x00\x01"
    assert utils.p32(1, endian) == b"\x00\x00\x00\x01"
    assert utils.p64(1, endian) == b"\x00\x00\x00\x00\x00\x00\x00\x01"
    assert utils.u8(b"\x01", endian, sign) == 1
    assert utils.u16(b"\x00\x01", endian, sign) == 1
    assert utils.u32(b"\x00\x00\x00\x01", endian, sign) == 1
    assert utils.u64(b"\x00\x00\x00\x00\x00\x00\x00\x01", endian, sign) == 1

    endian = "little"
    sign = True
    assert utils.p8(-120, endian) == b"\x88"
    assert utils.p16(-120, endian) == b"\x88\xff"
    assert utils.p32(-120, endian) == b"\x88\xff\xff\xff"
    assert utils.p64(-120, endian) == b"\x88\xff\xff\xff\xff\xff\xff\xff"
    assert utils.u8(b"\x88", endian, sign) == -120
    assert utils.u16(b"\x88\xff", endian, sign) == -120
    assert utils.u32(b"\x88\xff\xff\xff", endian, sign) == -120
    assert utils.u64(b"\x88\xff\xff\xff\xff\xff\xff\xff", endian, sign) == -120

    endian = "big"
    sign = True
    assert utils.p8(-120, endian) == b"\x88"
    assert utils.p16(-120, endian) == b"\xff\x88"
    assert utils.p32(-120, endian) == b"\xff\xff\xff\x88"
    assert utils.p64(-120, endian) == b"\xff\xff\xff\xff\xff\xff\xff\x88"
    assert utils.u8(b"\x88", endian, sign) == -120
    assert utils.u16(b"\xff\x88", endian, sign) == -120
    assert utils.u32(b"\xff\xff\xff\x88", endian, sign) == -120
    assert utils.u64(b"\xff\xff\xff\xff\xff\xff\xff\x88", endian, sign) == -120

    assert utils.pack(1, 24) == b"\x01\x00\x00"
    assert utils.unpack(b"\x01\x00\x00", 24) == 1

    assert utils.pack(213928798) == b"^K\xc0\x0c"
    assert utils.unpack(b"^K\xc0\x0c") == 213928798


def test_swap():
    assert utils.swap16(0x0001) == 0x0100
    assert utils.swap32(0x00000001) == 0x01000000
    assert utils.swap64(0x0000000000000001) == 0x0100000000000000
