from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct import dump
from dissect.cstruct.dump import dumpstruct, hexdump
from tests.util import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_hexdump(capsys: pytest.CaptureFixture) -> None:
    hexdump(b"\x00" * 16, pretty=False)
    captured = capsys.readouterr()
    assert captured.out == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................\n"

    out = hexdump(b"\x00" * 16, output="string")
    assert out == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................"

    out = hexdump(b"\x00" * 16, output="generator")
    assert next(out) == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................"

    with pytest.raises(
        ValueError, match=re.escape("Invalid output argument: 'str' (should be 'print', 'generator' or 'string').")
    ):
        hexdump("b\x00", output="str")


def test_hexdump_pretty(capsys: pytest.CaptureFixture) -> None:
    """Check if we can create a pretty hexdump."""
    c = dump.COLOR_CLEAR
    g = dump.COLOR_GREY
    w = dump.COLOR_WHITE_BOLD
    y = dump.COLOR_YELLOW

    hexdump((b"\x00" * 5) + b"\x01\x02\x03abc" + (b"\x00" * 5), pretty=True)
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


@pytest.mark.parametrize(
    ("data", "autoskip", "expected"),
    [
        # The first interior NUL line is kept, the rest of the run is collapsed to a single '*'
        (b"A" * 16 + b"\x00" * 48 + b"B" * 16, True, ["00000000", "00000010", "*", "00000040"]),
        # NUL lines at the start and the end are never collapsed
        (b"\x00" * 48, True, ["00000000", "00000010", "00000020"]),
        # Every interior NUL run is collapsed separately
        (
            b"A" * 16 + b"\x00" * 32 + b"B" * 16 + b"\x00" * 32 + b"C" * 16,
            True,
            ["00000000", "00000010", "*", "00000030", "00000040", "*", "00000060"],
        ),
        # A single interior NUL line is kept
        (b"A" * 16 + b"\x00" * 16 + b"B" * 16, True, ["00000000", "00000010", "00000020"]),
        # Nothing is collapsed without autoskip
        (b"A" * 16 + b"\x00" * 48 + b"B" * 16, False, ["00000000", "00000010", "00000020", "00000030", "00000040"]),
    ],
)
def test_hexdump_autoskip(data: bytes, autoskip: bool, expected: list[str]) -> None:
    """Test which NUL lines ``autoskip`` collapses to a single '*', by the offset each line starts with."""
    out = hexdump(data, output="string", pretty=False, autoskip=autoskip)
    assert [line[:8] for line in out.splitlines()] == expected


def test_hexdump_pretty_print_conditions(capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test if we respec the ``NO_COLOR`` environment variable and ``pretty=False`` argument."""
    # Test regular print output behavior
    hexdump(b"\x00" * 16)
    captured = capsys.readouterr()
    assert captured.out.startswith("00000000  \x1b[0;90m00")

    # Test explicit disable using NO_COLOR
    with monkeypatch.context() as m:
        m.setenv("NO_COLOR", "1")
        hexdump(b"\x00" * 16)
        captured = capsys.readouterr()
        assert captured.out.startswith("00000000  00")

    # Test explicit disable using pretty=False
    hexdump(b"\x00" * 16, pretty=False)
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

    out = dumpstruct(obj, output="string")
    assert dumpstruct(cs.test, buf, output="string") == out

    assert dumpstruct(cs.test, buf) is None
    assert capsys.readouterr().out == f"{out}\n"

    out = dumpstruct(obj, color=False, output="string")
    assert out == (
        "\n00000000  39 05 00 00                                        9...\n\nstruct test:\n- testval: 0x539"
    )

    with pytest.raises(
        ValueError,
        match=re.escape("Invalid output argument: 'generator' (should be 'print', 'string', 'dict' or 'json')."),
    ):
        dumpstruct(obj, output="generator")


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
    assert dumpstruct(cs.test, buf, output="dict") == {
        "bytes": "0200",
        "type": "test",
        "kind": "struct",
        "fields": [
            {"name": "testval", "type": "Test16", "offset": 0, "size": 2, "display": "<Test16.B: 2>"},
        ],
    }

    out = dumpstruct(cs.test, buf, color=False, output="string")
    assert out == (
        "\n00000000  02 00                                              ..\n\nstruct test:\n- testval: <Test16.B: 2>"
    )


def test_dumpstruct_dict_basic(cs: cstruct, compiled: bool) -> None:
    """Verify that a basic struct is correctly represented in the dict output."""
    cdef = """
    struct test {
        uint32 testval;
        uint16 other;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x39\x05\x00\x00\x01\x00"
    obj = cs.test(buf)

    result = dumpstruct(obj, output="dict")

    assert result == {
        "bytes": "390500000100",
        "type": "test",
        "kind": "struct",
        "fields": [
            {"name": "testval", "type": "uint32", "offset": 0, "size": 4, "display": "0x539"},
            {"name": "other", "type": "uint16", "offset": 4, "size": 2, "display": "0x1"},
        ],
    }

    # Also test with class + data
    result2 = dumpstruct(cs.test, buf, output="dict")
    assert result == result2


def test_dumpstruct_dict_array(cs: cstruct, compiled: bool) -> None:
    """Verify that arrays are correctly represented in the dict output."""
    cdef = """
    struct test {
        uint8 magic[4];
        uint16 value;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x7f\x45\x4c\x46\x02\x00"
    result = dumpstruct(cs.test, buf, output="dict")

    assert result == {
        "bytes": "7f454c460200",
        "type": "test",
        "kind": "struct",
        "fields": [
            {"name": "magic[4]", "type": "uint8", "offset": 0, "size": 4, "display": "[127, 69, 76, 70]"},
            {"name": "value", "type": "uint16", "offset": 4, "size": 2, "display": "0x2"},
        ],
    }


def test_dumpstruct_dict_anonymous_struct_array(cs: cstruct, compiled: bool) -> None:
    """Verify that an array of anonymous structs and its elements have no type name."""
    cdef = """
    struct test {
        struct {
            uint8 x;
        } b[2];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert dumpstruct(cs.test, b"\x01\x02", output="dict")["fields"] == [
        {
            "name": "b[2]",
            "type": None,
            "offset": 0,
            "size": 2,
            "kind": "array",
            "fields": [
                {
                    "name": "[0]",
                    "type": None,
                    "offset": 0,
                    "size": 1,
                    "kind": "struct",
                    "fields": [{"name": "x", "type": "uint8", "offset": 0, "size": 1, "display": "0x1"}],
                },
                {
                    "name": "[1]",
                    "type": None,
                    "offset": 1,
                    "size": 1,
                    "kind": "struct",
                    "fields": [{"name": "x", "type": "uint8", "offset": 1, "size": 1, "display": "0x2"}],
                },
            ],
        },
    ]


def test_dumpstruct_anonymous_union(cs: cstruct, compiled: bool) -> None:
    """Verify anonymous union members are shown as fields of the parent and claim their overlapping bytes only once."""
    cdef = """
    struct test {
        uint16 before;
        union {
            uint32 as_int;
            uint8  as_bytes[4];
        };
        uint16 after;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\xaa\xbb\x01\x02\x03\x04\xcc\xdd"
    result = dumpstruct(cs.test, buf, output="dict")

    assert result == {
        "bytes": "aabb01020304ccdd",
        "type": "test",
        "kind": "struct",
        "fields": [
            {"name": "before", "type": "uint16", "offset": 0, "size": 2, "display": "0xbbaa"},
            {
                "name": None,
                "type": None,
                "offset": 2,
                "size": 4,
                "kind": "union",
                "fields": [
                    {"name": "as_int", "type": "uint32", "offset": 2, "size": 4, "display": "0x4030201"},
                    {"name": "as_bytes[4]", "type": "uint8", "offset": 2, "size": 4, "display": "[1, 2, 3, 4]"},
                ],
            },
            {"name": "after", "type": "uint16", "offset": 6, "size": 2, "display": "0xddcc"},
        ],
    }

    # Union members are promoted flat in the string output
    out = dumpstruct(cs.test, buf, color=False, output="string")
    assert out == (
        "\n"
        "00000000  aa bb 01 02 03 04 cc dd                            ........\n"
        "\n"
        "struct test:\n"
        "- before: 0xbbaa\n"
        "- as_int: 0x4030201\n"
        "- as_bytes[4]: [1, 2, 3, 4]\n"
        "- after: 0xddcc"
    )

    # The overlapping union bytes must be claimed exactly once in the hexdump palette:
    # before (2 bytes), first union member claims the full union region (4 bytes), after (2 bytes)
    out = dumpstruct(cs.test, buf, color=True, output="string")
    hexline = out.split("\n")[1]
    bg_colors = [
        dump.COLOR_BG_RED,
        dump.COLOR_BG_GREEN,
        dump.COLOR_BG_YELLOW,
        dump.COLOR_BG_BLUE,
        dump.COLOR_BG_PURPLE,
        dump.COLOR_BG_CYAN,
        dump.COLOR_BG_WHITE,
    ]
    bg_pattern = re.compile(
        r"(" + "|".join(re.escape(bg) for bg in bg_colors) + r")((?:[0-9a-f]{2}\s*)+)" + re.escape(dump.COLOR_CLEAR)
    )
    bg_regions = [(bg, hexbytes.split()) for bg, hexbytes in bg_pattern.findall(hexline)]

    assert bg_regions == [
        (bg_colors[0], ["aa", "bb"]),  # before
        (bg_colors[1], ["01", "02", "03", "04"]),  # as_int (first union member) claims the full region
        (bg_colors[3], ["cc", "dd"]),  # after
    ]


def test_dumpstruct_dict_bitfields(cs: cstruct, compiled: bool) -> None:
    """Verify that bitfields share the offset and size of their storage unit, and start a new one when it's full or
    after a regular field.
    """
    cdef = """
    struct Multi {
        uint32 a : 1;
        uint32 b : 31;
        uint16 gap;
        uint8 c : 4;
        uint8 d : 4;
        uint8 e : 4;
        uint8 gap2;
        uint8 f : 4;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.Multi, compiled)

    buf = b"\x03\x00\x00\x00\xff\xff\x35\x07\xaa\x09"
    result = dumpstruct(cs.Multi, buf, output="dict")

    assert result == {
        "bytes": "03000000ffff3507aa09",
        "type": "Multi",
        "kind": "struct",
        "fields": [
            {"name": "a", "type": "uint32", "offset": 0, "size": 4, "bits": 1, "display": "0x1"},
            {"name": "b", "type": "uint32", "offset": 0, "size": 4, "bits": 31, "display": "0x1"},
            {"name": "gap", "type": "uint16", "offset": 4, "size": 2, "display": "0xffff"},
            {"name": "c", "type": "uint8", "offset": 6, "size": 1, "bits": 4, "display": "0x5"},
            {"name": "d", "type": "uint8", "offset": 6, "size": 1, "bits": 4, "display": "0x3"},
            {"name": "e", "type": "uint8", "offset": 7, "size": 1, "bits": 4, "display": "0x7"},
            {"name": "gap2", "type": "uint8", "offset": 8, "size": 1, "display": "0xaa"},
            {"name": "f", "type": "uint8", "offset": 9, "size": 1, "bits": 4, "display": "0x9"},
        ],
    }


def test_dumpstruct_invalid_args(cs: cstruct, compiled: bool) -> None:
    """Verify that invalid arguments raise ValueError."""
    cdef = """
    struct test {
        uint32 val;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    message = "Invalid arguments: expected a Structure instance, or a Structure class with data."

    # Class without data
    with pytest.raises(ValueError, match=re.escape(message)):
        dumpstruct(cs.test)

    # Non-Structure type
    with pytest.raises(ValueError, match=re.escape(message)):
        dumpstruct(42)


def test_dumpstruct_comprehensive(cs: cstruct, compiled: bool) -> None:
    """Big boy dumpstruct test."""
    cdef = """
    struct point {
        uint16 x;
        uint16 y;
    };

    struct complex {
        uint32 flags:4;
        uint32 version:4;
        uint32 reserved:24;
        point origin;
        struct {
            uint8 r;
            uint8 g;
            uint8 b;
        };
        union {
            uint32 as_int;
            uint8  as_bytes[4];
        } data;
        uint8 matrix[2][3];
        uint16 checksum;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.complex, compiled)

    # bitfield uint32: flags=5(bits 0-3), version=3(bits 4-7), reserved=1(bits 8-31)
    # little-endian: 5 | (3<<4) | (1<<8) = 0x00000135 -> bytes 35 01 00 00
    buf = (
        b"\x35\x01\x00\x00"  # bitfield: flags=5, version=3, reserved=1
        b"\x0a\x00\x14\x00"  # origin: x=10, y=20
        b"\xff\x80\x40"  # anonymous struct: r=255, g=128, b=64
        b"\xef\xbe\xad\xde"  # union data: as_int=0xdeadbeef
        b"\x01\x02\x03\x04\x05\x06"  # matrix[2][3]: [[1,2,3],[4,5,6]]
        b"\xfe\xca"  # checksum=0xcafe
    )

    result = dumpstruct(cs.complex, buf, output="dict")

    assert result == {
        "bytes": "350100000a001400ff8040efbeadde010203040506feca",
        "type": "complex",
        "kind": "struct",
        "fields": [
            {"name": "flags", "type": "uint32", "offset": 0, "size": 4, "bits": 4, "display": "0x5"},
            {"name": "version", "type": "uint32", "offset": 0, "size": 4, "bits": 4, "display": "0x3"},
            {"name": "reserved", "type": "uint32", "offset": 0, "size": 4, "bits": 24, "display": "0x1"},
            {
                "name": "origin",
                "type": "point",
                "offset": 4,
                "size": 4,
                "kind": "struct",
                "fields": [
                    {"name": "x", "type": "uint16", "offset": 4, "size": 2, "display": "0xa"},
                    {"name": "y", "type": "uint16", "offset": 6, "size": 2, "display": "0x14"},
                ],
            },
            {
                "name": None,
                "type": None,
                "offset": 8,
                "size": 3,
                "kind": "struct",
                "fields": [
                    {"name": "r", "type": "uint8", "offset": 8, "size": 1, "display": "0xff"},
                    {"name": "g", "type": "uint8", "offset": 9, "size": 1, "display": "0x80"},
                    {"name": "b", "type": "uint8", "offset": 10, "size": 1, "display": "0x40"},
                ],
            },
            {
                "name": "data",
                "type": None,
                "offset": 11,
                "size": 4,
                "kind": "union",
                "fields": [
                    {"name": "as_int", "type": "uint32", "offset": 11, "size": 4, "display": "0xdeadbeef"},
                    {
                        "name": "as_bytes[4]",
                        "type": "uint8",
                        "offset": 11,
                        "size": 4,
                        "display": "[239, 190, 173, 222]",
                    },
                ],
            },
            {"name": "matrix[2][3]", "type": "uint8", "offset": 15, "size": 6, "display": "[[1, 2, 3], [4, 5, 6]]"},
            {"name": "checksum", "type": "uint16", "offset": 21, "size": 2, "display": "0xcafe"},
        ],
    }
    assert json.loads(dumpstruct(cs.complex, buf, output="json")) == result

    # Validate string output covers all fields correctly
    out = dumpstruct(cs.complex, buf, color=False, output="string")
    assert out == (
        "\n"
        "00000000  35 01 00 00 0a 00 14 00  ff 80 40 ef be ad de 01   5.........@.....\n"
        "00000010  02 03 04 05 06 fe ca                               .......\n"
        "\n"
        "struct complex:\n"
        "- flags: 0x5\n"
        "- version: 0x3\n"
        "- reserved: 0x1\n"
        "- origin:\n"
        "  - x: 0xa\n"
        "  - y: 0x14\n"
        "- r: 0xff\n"
        "- g: 0x80\n"
        "- b: 0x40\n"
        "- data:\n"
        "  - as_int: 0xdeadbeef\n"
        "  - as_bytes[4]: [239, 190, 173, 222]\n"
        "- matrix[2][3]: [[1, 2, 3], [4, 5, 6]]\n"
        "- checksum: 0xcafe"
    )


def test_dumpstruct_coloring(cs: cstruct, compiled: bool) -> None:
    """Validate that color escape codes and hexdump palette entries are placed correctly.

    Exercises the trickiest coloring edge cases:
    - Bitfields: all members share one palette entry (the storage unit), but each
      gets its own foreground color in the text listing.
    - Named struct: container header gets a foreground color but NO palette entry;
      children each get their own palette entry (sequential bytes).
    - Named union (anonymous type): container gets ONE palette entry for the full
      overlapping region; children get foreground colors but NO palette entries.
    """
    cdef = """
    struct point {
        uint16 x;
        uint16 y;
    };

    struct test {
        uint8  a:4;
        uint8  b:4;
        point  pos;
        union {
            uint32 as_int;
            uint8  as_bytes[4];
        } data;
        uint16 tail;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = (
        b"\x35"  # bitfield: a=5, b=3
        b"\x0a\x00\x14\x00"  # pos: x=10, y=20
        b"\xef\xbe\xad\xde"  # data: as_int=0xdeadbeef
        b"\xfe\xca"  # tail=0xcafe
    )

    out = dumpstruct(cs.test, buf, color=True, output="string")
    lines = out.split("\n")

    # Foreground/background color cycle used by dumpstruct, derived from utils constants
    FG = [
        dump.COLOR_RED_BOLD,
        dump.COLOR_GREEN_BOLD,
        dump.COLOR_YELLOW_BOLD,
        dump.COLOR_BLUE_BOLD,
        dump.COLOR_PURPLE_BOLD,
        dump.COLOR_CYAN_BOLD,
        dump.COLOR_WHITE_BOLD,
    ]
    BG = [
        dump.COLOR_BG_RED,
        dump.COLOR_BG_GREEN,
        dump.COLOR_BG_YELLOW,
        dump.COLOR_BG_BLUE,
        dump.COLOR_BG_PURPLE,
        dump.COLOR_BG_CYAN,
        dump.COLOR_BG_WHITE,
    ]
    RESET = dump.COLOR_CLEAR

    def assert_field_color(line: str, ci: int, name: str) -> None:
        """Assert that ``name`` appears wrapped in the expected foreground color."""
        fg = FG[ci % len(FG)]
        expected = f"{fg}{name}{RESET}"
        assert expected in line, f"Expected {name!r} with fg index {ci} on line: {line!r}"

    # Bitfield members: each gets its own foreground color (ci=0,1)
    assert_field_color(lines[4], 0, "a")
    assert_field_color(lines[5], 1, "b")

    # Struct container header gets foreground but no palette (ci=2)
    assert_field_color(lines[6], 2, "pos")

    # Struct children get their own colors (ci=3,4)
    assert_field_color(lines[7], 3, "x")
    assert_field_color(lines[8], 4, "y")

    # Union container gets foreground and palette (ci=5)
    assert_field_color(lines[9], 5, "data")

    # Union children get foreground but no palette (ci=6,7 -> wraps)
    assert_field_color(lines[10], 6, "as_int")
    assert_field_color(lines[11], 7, "as_bytes[4]")

    # Tail (ci=8 -> wraps to 1)
    assert_field_color(lines[12], 8, "tail")

    # Verify hexdump background palette
    # Extract background+foreground color regions from the hex portion of the hexdump line.
    hexline = lines[1]
    bg_pattern = re.compile(
        r"(" + "|".join(re.escape(bg) for bg in BG) + r")((?:[0-9a-f]{2}\s*)+)" + re.escape(dump.COLOR_CLEAR)
    )
    bg_regions = [(bg, hexbytes.split()) for bg, hexbytes in bg_pattern.findall(hexline)]

    # Expected palette order and byte counts:
    # 1) bitfield storage (1 byte) -> BG[0] (first bitfield's color)
    # 2) pos.x (2 bytes) -> BG[3] (x's color)
    # 3) pos.y (2 bytes) -> BG[4] (y's color)
    # 4) union data (4 bytes) -> BG[5] (data container's color)
    # 5) tail (2 bytes) -> BG[1] (tail's color, ci=8 wraps)
    expected = [
        (BG[0], ["35"], "bitfield"),
        (BG[3], ["0a", "00"], "pos.x"),
        (BG[4], ["14", "00"], "pos.y"),
        (BG[5], ["ef", "be", "ad", "de"], "union data"),
        (BG[1], ["fe", "ca"], "tail"),
    ]

    assert len(bg_regions) == len(expected), (
        f"Expected {len(expected)} palette regions, got {len(bg_regions)}: {bg_regions}"
    )

    for (actual_bg, actual_bytes), (exp_bg, exp_bytes, label) in zip(bg_regions, expected, strict=False):
        assert actual_bg == exp_bg, f"{label}: expected bg={exp_bg!r}, got {actual_bg!r}"
        assert actual_bytes == exp_bytes, f"{label}: expected bytes {exp_bytes}, got {actual_bytes}"

    # Total palette bytes must equal data length
    total_palette_bytes = sum(len(b) for _, b in bg_regions)
    assert total_palette_bytes == len(buf), f"Palette covers {total_palette_bytes} bytes but data is {len(buf)} bytes"


def test_dumpstruct_padding(cs: cstruct, compiled: bool) -> None:
    """Verify that offsets and hexdump colors skip alignment padding, also after a dynamic field."""
    cdef = """
    struct test {
        uint8  a;
        uint32 b;
        uint8  count;
        uint8  data[count];
        uint32 c;
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    buf = (
        b"\x01\xee\xee\xee"  # a, padding
        b"\x02\x03\x04\x05"  # b
        b"\x02\x06\x07\xee"  # count, data, padding
        b"\x08\x09\x0a\x0b"  # c
    )
    result = dumpstruct(cs.test, buf, output="dict")

    assert result["fields"] == [
        {"name": "a", "type": "uint8", "offset": 0, "size": 1, "display": "0x1"},
        {"name": "b", "type": "uint32", "offset": 4, "size": 4, "display": "0x5040302"},
        {"name": "count", "type": "uint8", "offset": 8, "size": 1, "display": "0x2"},
        {"name": "data[count]", "type": "uint8", "offset": 9, "size": 2, "display": "[6, 7]"},
        {"name": "c", "type": "uint32", "offset": 12, "size": 4, "display": "0xb0a0908"},
    ]

    assert _palette_regions(dumpstruct(cs.test, buf, color=True, output="string")) == [
        ["01"],
        ["02", "03", "04", "05"],
        ["02"],
        ["06", "07"],
        ["08", "09", "0a", "0b"],
    ]


def test_dumpstruct_unknown_size(cs: cstruct, compiled: bool) -> None:
    """Verify that offsets are unknown after a dynamic field of a structure that wasn't parsed."""
    cdef = """
    struct test {
        uint8  count;
        uint8  data[count];
        uint16 c;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(count=2, data=[6, 7], c=0x908)

    assert dumpstruct(obj, output="dict")["fields"] == [
        {"name": "count", "type": "uint8", "offset": 0, "size": 1, "display": "0x2"},
        {"name": "data[count]", "type": "uint8", "offset": 1, "size": None, "display": "[6, 7]"},
        {"name": "c", "type": "uint16", "offset": None, "size": 2, "display": "0x908"},
    ]

    assert _palette_regions(dumpstruct(obj, color=True, output="string")) == [["02"]]


def test_dumpstruct_dict_struct_array(cs: cstruct, compiled: bool) -> None:
    """Verify that the elements of an array of structs are described like nested structs."""
    cdef = """
    struct point {
        uint16 x;
        uint16 y;
    };

    struct test {
        uint8 count;
        point items[2];
        uint8 tail;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = (
        b"\x02"  # count=2
        b"\x0a\x00\x14\x00"  # items[0]: x=10, y=20
        b"\x1e\x00\x28\x00"  # items[1]: x=30, y=40
        b"\xff"  # tail=0xff
    )
    result = dumpstruct(cs.test, buf, output="dict")

    assert result == {
        "bytes": "020a0014001e002800ff",
        "type": "test",
        "kind": "struct",
        "fields": [
            {"name": "count", "type": "uint8", "offset": 0, "size": 1, "display": "0x2"},
            {
                "name": "items[2]",
                "type": "point",
                "offset": 1,
                "size": 8,
                "kind": "array",
                "fields": [
                    {
                        "name": "[0]",
                        "type": "point",
                        "offset": 1,
                        "size": 4,
                        "kind": "struct",
                        "fields": [
                            {"name": "x", "type": "uint16", "offset": 1, "size": 2, "display": "0xa"},
                            {"name": "y", "type": "uint16", "offset": 3, "size": 2, "display": "0x14"},
                        ],
                    },
                    {
                        "name": "[1]",
                        "type": "point",
                        "offset": 5,
                        "size": 4,
                        "kind": "struct",
                        "fields": [
                            {"name": "x", "type": "uint16", "offset": 5, "size": 2, "display": "0x1e"},
                            {"name": "y", "type": "uint16", "offset": 7, "size": 2, "display": "0x28"},
                        ],
                    },
                ],
            },
            {"name": "tail", "type": "uint8", "offset": 9, "size": 1, "display": "0xff"},
        ],
    }

    out = dumpstruct(cs.test, buf, color=False, output="string")
    assert out == (
        "\n"
        "00000000  02 0a 00 14 00 1e 00 28  00 ff                     .......(..\n"
        "\n"
        "struct test:\n"
        "- count: 0x2\n"
        "- items[2]:\n"
        "  - [0]:\n"
        "    - x: 0xa\n"
        "    - y: 0x14\n"
        "  - [1]:\n"
        "    - x: 0x1e\n"
        "    - y: 0x28\n"
        "- tail: 0xff"
    )

    # The fields of the elements get their own colors
    assert _palette_regions(dumpstruct(cs.test, buf, color=True, output="string")) == [
        ["02"],
        ["0a", "00"],
        ["14", "00"],
        ["1e", "00"],
        ["28", "00"],
        ["ff"],
    ]


def test_dumpstruct_dynamic_struct_array(cs: cstruct, compiled: bool) -> None:
    """Verify that elements of a dynamic size end where their last field ends, and the fields after them follow."""
    cdef = """
    struct item {
        uint8 length;
        char  data[length];
    };

    struct test {
        uint8 count;
        item  items[count];
        uint8 tail;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    result = dumpstruct(cs.test, b"\x02\x01a\x02bc\xff", output="dict")
    items, tail = result["fields"][1], result["fields"][2]
    assert [(element["offset"], element["size"]) for element in items["fields"]] == [(1, 2), (3, 3)]
    assert tail == {"name": "tail", "type": "uint8", "offset": 6, "size": 1, "display": "0xff"}


def test_dumpstruct_dynamic_struct_array_aligned(cs: cstruct, compiled: bool) -> None:
    """Verify that elements of a dynamic size of aligned structures include their tail padding."""
    cdef = """
    struct item {
        uint16 length;
        char   data[length];
    };

    struct test {
        uint8 count;
        item  items[count];
        uint8 tail;
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    buf = (
        b"\x02\xee"  # count, padding
        b"\x01\x00a\xee"  # items[0], tail padding
        b"\x02\x00bc"  # items[1]
        b"\xff\xee"  # tail, tail padding
    )
    result = dumpstruct(cs.test, buf, output="dict")
    items, tail = result["fields"][1], result["fields"][2]
    assert [(element["offset"], element["size"]) for element in items["fields"]] == [(2, 4), (6, 4)]
    assert tail == {"name": "tail", "type": "uint8", "offset": 10, "size": 1, "display": "0xff"}


def test_dumpstruct_union_array(cs: cstruct, compiled: bool) -> None:
    """Verify that the elements of a multi-dimensional array of unions are nested arrays of unions."""
    cdef = """
    union foo {
        uint8  a;
        uint16 b;
    };

    struct test {
        foo grid[2][1];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    def element(offset: int, a: str, b: str) -> dict:
        return {
            "name": "[0]",
            "type": "foo",
            "offset": offset,
            "size": 2,
            "kind": "union",
            "fields": [
                {"name": "a", "type": "uint8", "offset": offset, "size": 1, "display": a},
                {"name": "b", "type": "uint16", "offset": offset, "size": 2, "display": b},
            ],
        }

    assert dumpstruct(cs.test, b"\x01\x02\x03\x04", output="dict")["fields"] == [
        {
            "name": "grid[2][1]",
            "type": "foo",
            "offset": 0,
            "size": 4,
            "kind": "array",
            "fields": [
                {
                    "name": "[0]",
                    "type": "foo",
                    "offset": 0,
                    "size": 2,
                    "kind": "array",
                    "fields": [element(0, "0x1", "0x201")],
                },
                {
                    "name": "[1]",
                    "type": "foo",
                    "offset": 2,
                    "size": 2,
                    "kind": "array",
                    "fields": [element(2, "0x3", "0x403")],
                },
            ],
        },
    ]


def test_dumpstruct_bitfields_after_dynamic_field(cs: cstruct, compiled: bool) -> None:
    """Verify that bit fields after a dynamic field get the offsets of their storage units."""
    cdef = """
    struct test {
        uint8  count;
        uint8  data[count];
        uint8  a : 4;
        uint8  b : 4;
        uint16 c : 4;
        uint8  tail;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    result = dumpstruct(cs.test, b"\x01\xaa\x21\x03\x00\xff", output="dict")
    assert [(field["name"], field["offset"], field["size"]) for field in result["fields"]] == [
        ("count", 0, 1),
        ("data[count]", 1, 1),
        ("a", 2, 1),
        ("b", 2, 1),
        ("c", 3, 2),
        ("tail", 5, 1),
    ]


def test_dumpstruct_repeated_field_name(cs: cstruct, compiled: bool) -> None:
    """Verify that fields named ``_`` whose value the structure doesn't keep have no value, but their own size."""
    cdef = """
    struct test {
        uint8  _;
        uint8  a;
        uint16 _;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert dumpstruct(cs.test, b"\x01\x02\x03\x04", output="dict")["fields"] == [
        {"name": "_", "type": "uint8", "offset": 0, "size": 1, "display": None},
        {"name": "a", "type": "uint8", "offset": 1, "size": 1, "display": "0x2"},
        {"name": "_", "type": "uint16", "offset": 2, "size": 2, "display": "0x403"},
    ]


def test_dumpstruct_union_root(cs: cstruct, compiled: bool) -> None:
    """Verify that dumping a union directly reports it as a union, not a struct."""
    cdef = """
    union foo {
        uint32 as_int;
        uint8  as_bytes[4];
    };
    """
    cs.load(cdef, compiled=compiled)

    buf = b"\x01\x02\x03\x04"
    out = dumpstruct(cs.foo, buf, color=False, output="string")
    assert out.split("\n")[3] == "union foo:"

    result = dumpstruct(cs.foo, buf, output="dict")
    assert result == {
        "bytes": "01020304",
        "type": "foo",
        "kind": "union",
        "fields": [
            {"name": "as_int", "type": "uint32", "offset": 0, "size": 4, "display": "0x4030201"},
            {"name": "as_bytes[4]", "type": "uint8", "offset": 0, "size": 4, "display": "[1, 2, 3, 4]"},
        ],
    }


def test_dumpstruct_union_nested_struct(cs: cstruct, compiled: bool) -> None:
    """Nested Structure members inside a Union are proxied via UnionProxy; verify unwrap."""
    cdef = """
    struct inner {
        uint32 a;
        uint32 b;
    };
    union outer {
        inner  nested;
        uint8  raw[8];
    };

    union anon_outer {
        struct {
            uint32 a;
            uint32 b;
        };
        uint8  raw[8];
    };
    """
    cs.load(cdef, compiled=compiled)

    buf = b"\x01\x00\x00\x00\x02\x00\x00\x00"

    inner_fields = [
        {"name": "a", "type": "uint32", "offset": 0, "size": 4, "display": "0x1"},
        {"name": "b", "type": "uint32", "offset": 4, "size": 4, "display": "0x2"},
    ]
    raw = {"name": "raw[8]", "type": "uint8", "offset": 0, "size": 8, "display": "[1, 0, 0, 0, 2, 0, 0, 0]"}

    result = dumpstruct(cs.outer, buf, output="dict")
    assert result["fields"] == [
        {"name": "nested", "type": "inner", "offset": 0, "size": 8, "kind": "struct", "fields": inner_fields},
        raw,
    ]

    result = dumpstruct(cs.anon_outer, buf, output="dict")
    assert result["fields"] == [
        {"name": None, "type": None, "offset": 0, "size": 8, "kind": "struct", "fields": inner_fields},
        raw,
    ]


def _palette_regions(colored_output: str) -> list[list[str]]:
    """Extract the hex bytes of each background-colored region from the first hexdump line."""
    backgrounds = [
        dump.COLOR_BG_RED,
        dump.COLOR_BG_GREEN,
        dump.COLOR_BG_YELLOW,
        dump.COLOR_BG_BLUE,
        dump.COLOR_BG_PURPLE,
        dump.COLOR_BG_CYAN,
        dump.COLOR_BG_WHITE,
    ]
    pattern = re.compile(
        r"(?:" + "|".join(re.escape(bg) for bg in backgrounds) + r")((?:[0-9a-f]{2}\s*)+)" + re.escape(dump.COLOR_CLEAR)
    )
    return [hexbytes.split() for hexbytes in pattern.findall(colored_output.split("\n")[1])]
