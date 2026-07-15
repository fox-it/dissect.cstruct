from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct import util

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_hexdump(capsys: pytest.CaptureFixture) -> None:
    util.hexdump(b"\x00" * 16, pretty=False)
    captured = capsys.readouterr()
    assert captured.out == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................\n"

    out = util.hexdump(b"\x00" * 16, output="string")
    assert out == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................"

    out = util.hexdump(b"\x00" * 16, output="generator")
    assert next(out) == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................"

    with pytest.raises(
        ValueError, match=re.escape("Invalid output argument: 'str' (should be 'print', 'generator' or 'string').")
    ):
        util.hexdump("b\x00", output="str")


def test_hexdump_pretty(capsys: pytest.CaptureFixture) -> None:
    """Check if we can create a pretty hexdump."""
    c = util.COLOR_CLEAR
    g = util.COLOR_GREY
    w = util.COLOR_WHITE_BOLD
    y = util.COLOR_YELLOW

    util.hexdump((b"\x00" * 5) + b"\x01\x02\x03abc" + (b"\x00" * 5), pretty=True)
    captured = capsys.readouterr()
    assert (
        captured.out
        == "00000000  "
        + (f"{g}00{c} " * 5)
        + f"{y}01{c} {y}02{c} {y}03{c}  {w}61{c} {w}62{c} {w}63{c} "
        + (f"{g}00{c} " * 5)
        + "  "
        + (f"{g}.{c}" * 5)
        + f"{y}.{c}{y}.{c}{y}.{c}{w}a{c}{w}b{c}{w}c{c}"
        + (f"{g}.{c}" * 5)
        + "\n"
    )


def test_hexdump_autoskip_collapses_middle_null_run() -> None:
    """Keep first interior NUL line, then collapse the rest of that run to '*'."""
    # Layout: [A data line] [3 NUL lines] [B data line]
    # Expected: [A line] [first NUL line] [*] [B line] = 4 lines
    data = (b"A" * 16) + (b"\x00" * 48) + (b"B" * 16)

    out = util.hexdump(data, output="string", pretty=False, autoskip=True)
    assert out is not None

    lines = out.splitlines()
    assert len(lines) == 4
    assert lines[0].startswith("00000000")  # A line
    assert lines[1].startswith("00000010")  # First NUL line is kept
    assert lines[2] == "*"  # Remaining NUL lines collapsed
    assert lines[3].startswith("00000040")  # B line


def test_hexdump_autoskip_keeps_edge_null_lines() -> None:
    """Do not collapse first/last hexdump lines even when they are all NUL bytes."""
    # Layout: [3 NUL lines]
    # Expected: all lines are kept (only one interior line, so nothing is repeated there)
    data = b"\x00" * 48

    out = util.hexdump(data, output="string", pretty=False, autoskip=True)
    assert out is not None

    lines = out.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("00000000")  # First line kept (edge)
    assert lines[1].startswith("00000010")  # Single interior NUL line is kept
    assert lines[2].startswith("00000020")  # Last line kept (edge)


def test_hexdump_autoskip_separate_null_runs() -> None:
    """Emit one '*' per interior NUL run, after keeping each run's first interior NUL line."""
    # Layout: [A data] [2 NUL lines] [B data] [2 NUL lines] [C data]
    # Expected: [A line] [NUL line] [*] [B line] [NUL line] [*] [C line] = 7 lines
    data = (b"A" * 16) + (b"\x00" * 32) + (b"B" * 16) + (b"\x00" * 32) + (b"C" * 16)

    out = util.hexdump(data, output="string", pretty=False, autoskip=True)
    assert out is not None

    lines = out.splitlines()
    assert len(lines) == 7
    assert lines[0].startswith("00000000")  # A line
    assert lines[1].startswith("00000010")  # First NUL line of first run kept
    assert lines[2] == "*"  # Remaining NUL lines of first run collapsed
    assert lines[3].startswith("00000030")  # B line
    assert lines[4].startswith("00000040")  # First NUL line of second run kept
    assert lines[5] == "*"  # Remaining NUL lines of second run collapsed
    assert lines[6].startswith("00000060")  # C line


def test_hexdump_autoskip_single_interior_null_line_is_not_collapsed() -> None:
    """Keep a single interior all-NUL line visible when autoskip is enabled."""
    # Layout: [A data line] [1 NUL line] [B data line]
    # Expected: [A line] [NUL line] [B line] = 3 lines (no repeated interior NUL line)
    data = (b"A" * 16) + (b"\x00" * 16) + (b"B" * 16)

    out = util.hexdump(data, output="string", pretty=False, autoskip=True)
    assert out is not None

    lines = out.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("00000000")  # A line
    assert lines[1].startswith("00000010")  # Single NUL line is kept
    assert lines[2].startswith("00000020")  # B line


def test_hexdump_autoskip_false_does_not_collapse() -> None:
    """Keep all lines expanded and never emit '*' when autoskip is disabled."""
    # Layout: [A data line] [3 NUL lines] [B data line]
    # Expected: [A line] [NUL line] [NUL line] [NUL line] [B line] = 5 lines (no * when disabled)
    data = (b"A" * 16) + (b"\x00" * 48) + (b"B" * 16)

    out = util.hexdump(data, output="string", pretty=False, autoskip=False)
    assert out is not None

    lines = out.splitlines()
    assert len(lines) == 5
    assert all(line != "*" for line in lines)  # No * when autoskip disabled
    assert lines[0].startswith("00000000")  # A line
    assert lines[1].startswith("00000010")  # First NUL line (expanded)
    assert lines[2].startswith("00000020")  # Second NUL line (expanded)
    assert lines[3].startswith("00000030")  # Third NUL line (expanded)
    assert lines[4].startswith("00000040")  # B line


def test_hexdump_pretty_print_conditions(capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test if we respec the ``NO_COLOR`` environment variable and ``pretty=False`` argument."""
    # Test regular print output behavior
    util.hexdump(b"\x00" * 16)
    captured = capsys.readouterr()
    assert captured.out.startswith("00000000  \x1b[0;90m00")

    # Test explicit disable using NO_COLOR
    with monkeypatch.context() as m:
        m.setenv("NO_COLOR", "1")
        util.hexdump(b"\x00" * 16)
        captured = capsys.readouterr()
        assert captured.out.startswith("00000000  00")

    # Test explicit disable using pretty=False
    util.hexdump(b"\x00" * 16, pretty=False)
    captured = capsys.readouterr()
    assert captured.out.startswith("00000000  00")


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

    util.dumpstruct(cs.test, buf)
    captured_1 = capsys.readouterr()

    util.dumpstruct(obj)
    captured_2 = capsys.readouterr()

    assert captured_1.out == captured_2.out

    out_1 = util.dumpstruct(cs.test, buf, output="string")
    out_2 = util.dumpstruct(obj, output="string")

    assert out_1 == out_2

    with pytest.raises(
        ValueError, match=re.escape("Invalid output argument: 'generator' (should be 'print' or 'string').")
    ):
        util.dumpstruct(obj, output="generator")


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

    util.dumpstruct(cs.test, buf)
    captured_1 = capsys.readouterr()

    util.dumpstruct(obj)
    captured_2 = capsys.readouterr()

    assert captured_1.out == captured_2.out

    out_1 = util.dumpstruct(cs.test, buf, output="string")
    out_2 = util.dumpstruct(obj, output="string")

    assert out_1 == out_2

    with pytest.raises(
        ValueError, match=re.escape("Invalid output argument: 'generator' (should be 'print' or 'string').")
    ):
        util.dumpstruct(obj, output="generator")


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

    out1 = util.dumpstruct(cs.test, buf, output="string")
    out2 = util.dumpstruct(obj, output="string")

    assert "<Test16.B: 2>" in out1
    assert "<Test16.B: 2>" in out2


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
