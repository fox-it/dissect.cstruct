from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct import utils

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_hexdump(capsys: pytest.CaptureFixture) -> None:
    utils.hexdump(b"\x00" * 16)
    captured = capsys.readouterr()
    assert captured.out == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................\n"

    out = utils.hexdump(b"\x00" * 16, output="string")
    assert out == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................"

    out = utils.hexdump(b"\x00" * 16, output="generator")
    assert next(out) == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................"

    with pytest.raises(
        ValueError, match=re.escape("Invalid output argument: 'str' (should be 'print', 'generator' or 'string').")
    ):
        utils.hexdump("b\x00", output="str")


def test_dumpstruct(cs: cstruct, capsys: pytest.CaptureFixture, compiled: bool) -> None:
    cdef = """
    struct test {
        uint32 testval;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x39\x05\x00\x00"
    obj = cs.test(buf)

    utils.dumpstruct(cs.test, buf)
    captured_1 = capsys.readouterr()

    utils.dumpstruct(obj)
    captured_2 = capsys.readouterr()

    assert captured_1.out == captured_2.out

    out_1 = utils.dumpstruct(cs.test, buf, output="string")
    out_2 = utils.dumpstruct(obj, output="string")

    assert out_1 == out_2

    with pytest.raises(
        ValueError, match=re.escape("Invalid output argument: 'generator' (should be 'print' or 'string').")
    ):
        utils.dumpstruct(obj, output="generator")


def test_dumpstruct_anonymous(cs: cstruct, capsys: pytest.CaptureFixture, compiled: bool) -> None:
    cdef = """
    struct test {
        struct {
            uint32 testval;
        };
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x39\x05\x00\x00"
    obj = cs.test(buf)

    utils.dumpstruct(cs.test, buf)
    captured_1 = capsys.readouterr()

    utils.dumpstruct(obj)
    captured_2 = capsys.readouterr()

    assert captured_1.out == captured_2.out

    out_1 = utils.dumpstruct(cs.test, buf, output="string")
    out_2 = utils.dumpstruct(obj, output="string")

    assert out_1 == out_2

    with pytest.raises(
        ValueError, match=re.escape("Invalid output argument: 'generator' (should be 'print' or 'string').")
    ):
        utils.dumpstruct(obj, output="generator")


def test_dumpstruct_enum(cs: cstruct, compiled: bool) -> None:
    cdef = """
    enum Test16 : uint16 {
        A = 0x1,
        B = 0x2
    };

    struct test {
        Test16 testval;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x02\x00"
    obj = cs.test(buf)

    out1 = utils.dumpstruct(cs.test, buf, output="string")
    out2 = utils.dumpstruct(obj, output="string")

    assert "<Test16.B: 2>" in out1
    assert "<Test16.B: 2>" in out2


def test_pack_unpack() -> None:
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


def test_swap() -> None:
    assert utils.swap16(0x0001) == 0x0100
    assert utils.swap32(0x00000001) == 0x01000000
    assert utils.swap64(0x0000000000000001) == 0x0100000000000000
