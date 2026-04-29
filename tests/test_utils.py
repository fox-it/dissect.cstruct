from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct import utils

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_hexdump(capsys: pytest.CaptureFixture) -> None:
    utils.hexdump(b"\x00" * 16, pretty=False)
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


def test_hexdump_pretty(capsys: pytest.CaptureFixture) -> None:
    """Check if we can create a pretty hexdump."""
    c = utils.COLOR_CLEAR
    g = utils.COLOR_GREY
    w = utils.COLOR_WHITE_BOLD
    y = utils.COLOR_YELLOW

    utils.hexdump((b"\x00" * 5) + b"\x01\x02\x03abc" + (b"\x00" * 5), pretty=True)
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


def test_hexdump_pretty_print_conditions(capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test if we respec the ``NO_COLOR`` environment variable and ``pretty=False`` argument."""
    # Test regular print output behavior
    utils.hexdump(b"\x00" * 16)
    captured = capsys.readouterr()
    assert captured.out.startswith("00000000  \x1b[0;90m00")

    # Test explicit disable using NO_COLOR
    with monkeypatch.context() as m:
        m.setenv("NO_COLOR", "1")
        utils.hexdump(b"\x00" * 16)
        captured = capsys.readouterr()
        assert captured.out.startswith("00000000  00")

    # Test explicit disable using pretty=False
    utils.hexdump(b"\x00" * 16, pretty=False)
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

    utils.dumpstruct(cs.test, buf)
    captured_1 = capsys.readouterr()

    utils.dumpstruct(obj)
    captured_2 = capsys.readouterr()

    assert captured_1.out == captured_2.out

    out_1 = utils.dumpstruct(cs.test, buf, output="string")
    out_2 = utils.dumpstruct(obj, output="string")

    assert out_1 == out_2

    out = utils.dumpstruct(obj, color=False, output="string")
    assert out == (
        "\n00000000  39 05 00 00                                        9...\n\nstruct test:\n- testval: 0x539"
    )

    with pytest.raises(
        ValueError,
        match=re.escape("Invalid output argument: 'generator' (should be 'print', 'string', 'dict' or 'json')."),
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

    out = utils.dumpstruct(obj, color=False, output="string")
    assert out == (
        "\n00000000  39 05 00 00                                        9...\n\nstruct test:\n- testval: 0x539"
    )

    with pytest.raises(
        ValueError,
        match=re.escape("Invalid output argument: 'generator' (should be 'print', 'string', 'dict' or 'json')."),
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

    out = utils.dumpstruct(obj, color=False, output="string")
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

    result = utils.dumpstruct(obj, output="dict")

    assert result == {
        "bytes": "390500000100",
        "root": "test",
        "types": {
            "test": [
                {"name": "testval", "type": "uint32"},
                {"name": "other", "type": "uint16"},
            ],
        },
        "sizes": {
            "testval": 4,
            "other": 2,
        },
        "values": {
            "testval": "0x539",
            "other": "0x1",
        },
    }

    # Also test with class + data
    result2 = utils.dumpstruct(cs.test, buf, output="dict")
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
    result = utils.dumpstruct(cs.test, buf, output="dict")

    assert result == {
        "bytes": "7f454c460200",
        "root": "test",
        "types": {
            "test": [
                {"name": "magic[4]", "type": "uint8"},
                {"name": "value", "type": "uint16"},
            ],
        },
        "sizes": {
            "magic[4]": 4,
            "value": 2,
        },
        "values": {
            "magic[4]": "[127, 69, 76, 70]",
            "value": "0x2",
        },
    }


def test_dumpstruct_dict_nested_struct(cs: cstruct, compiled: bool) -> None:
    """Verify that nested structs are correctly represented in the dict output."""
    cdef = """
    struct inner {
        uint16 x;
        uint16 y;
    };

    struct outer {
        uint32 id;
        inner pos;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.outer, compiled)

    buf = b"\x01\x00\x00\x00\x0a\x00\x14\x00"
    result = utils.dumpstruct(cs.outer, buf, output="dict")

    assert result == {
        "bytes": "010000000a001400",
        "root": "outer",
        "types": {
            "outer": [
                {"name": "id", "type": "uint32"},
                {"name": "pos", "type": "inner"},
            ],
            "inner": [
                {"name": "x", "type": "uint16"},
                {"name": "y", "type": "uint16"},
            ],
        },
        "sizes": {
            "id": 4,
            "pos": 4,
            "pos.x": 2,
            "pos.y": 2,
        },
        "values": {
            "id": "0x1",
            "pos.x": "0xa",
            "pos.y": "0x14",
        },
    }


def test_dumpstruct_dict_anonymous_struct(cs: cstruct, compiled: bool) -> None:
    """Verify that anonymous structs are correctly represented in the dict output."""
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
    result = utils.dumpstruct(cs.test, buf, output="dict")

    assert result == {
        "bytes": "39050000",
        "root": "test",
        "types": {
            "test": [
                {
                    "name": "__anonymous_0__",
                    "type": "struct",
                    "anonymous": True,
                    "fields": [
                        {"name": "testval", "type": "uint32"},
                    ],
                },
            ],
        },
        "sizes": {
            "testval": 4,
        },
        "values": {
            "testval": "0x539",
        },
    }


def test_dumpstruct_dict_union(cs: cstruct, compiled: bool) -> None:
    """Verify that unions are correctly represented in the dict output."""
    cdef = """
    struct test {
        union {
            uint32 as_int;
            uint8  as_bytes[4];
        } u;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x02\x03\x04"
    result = utils.dumpstruct(cs.test, buf, output="dict")

    assert result == {
        "bytes": "01020304",
        "root": "test",
        "types": {
            "test": [
                {
                    "name": "u",
                    "type": "union",
                    "fields": [
                        {"name": "as_int", "type": "uint32"},
                        {"name": "as_bytes[4]", "type": "uint8"},
                    ],
                },
            ],
        },
        "sizes": {
            "u": 4,
            "u.as_int": 4,
            "u.as_bytes[4]": 4,
        },
        "values": {
            "u.as_int": "0x4030201",
            "u.as_bytes[4]": "[1, 2, 3, 4]",
        },
    }


def test_dumpstruct_dict_enum(cs: cstruct, compiled: bool) -> None:
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
    result = utils.dumpstruct(cs.test, buf, output="dict")

    assert result == {
        "bytes": "0200",
        "root": "test",
        "types": {
            "test": [
                {"name": "testval", "type": "Test16"},
            ],
        },
        "sizes": {
            "testval": 2,
        },
        "values": {
            "testval": "<Test16.B: 2>",
        },
    }


def test_dumpstruct_dict_serializable(cs: cstruct, compiled: bool) -> None:
    """Verify that the dict is fully JSON-serializable."""
    cdef = """
    struct inner {
        uint8 val[2];
    };

    struct outer {
        uint32 id;
        inner sub;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.outer, compiled)

    buf = b"\xff\x00\x00\x00\x0a\x0b"
    result = utils.dumpstruct(cs.outer, buf, output="dict")

    assert result == {
        "bytes": "ff0000000a0b",
        "root": "outer",
        "types": {
            "outer": [
                {"name": "id", "type": "uint32"},
                {"name": "sub", "type": "inner"},
            ],
            "inner": [
                {"name": "val[2]", "type": "uint8"},
            ],
        },
        "sizes": {
            "id": 4,
            "sub": 2,
            "sub.val[2]": 2,
        },
        "values": {
            "id": "0xff",
            "sub.val[2]": "[10, 11]",
        },
    }

    # Must not raise
    serialized = json.dumps(result)
    deserialized = json.loads(serialized)
    assert deserialized == result


def test_dumpstruct_dict_bitfields(cs: cstruct, compiled: bool) -> None:
    """Verify that bitfields are handled correctly."""
    cdef = """
    struct Multi {
        uint32 a : 1;
        uint32 b : 31;
        uint16 gap;
        uint8 c : 4;
        uint8 d : 4;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.Multi, compiled)

    buf = b"\x03\x00\x00\x00\xff\xff\x35"
    result = utils.dumpstruct(cs.Multi, buf, output="dict")

    assert result == {
        "bytes": "03000000ffff35",
        "root": "Multi",
        "types": {
            "Multi": [
                {
                    "type": "uint32",
                    "bitfields": [
                        {"name": "a", "bits": 1},
                        {"name": "b", "bits": 31},
                    ],
                },
                {"name": "gap", "type": "uint16"},
                {
                    "type": "uint8",
                    "bitfields": [
                        {"name": "c", "bits": 4},
                        {"name": "d", "bits": 4},
                    ],
                },
            ],
        },
        "sizes": {
            "a": 4,
            "gap": 2,
            "c": 1,
        },
        "values": {
            "a": "0x1",
            "b": "0x1",
            "gap": "0xffff",
            "c": "0x5",
            "d": "0x3",
        },
    }


def test_dumpstruct_dict_multidimensional_array(cs: cstruct, compiled: bool) -> None:
    """Verify that multi-dimensional arrays are correctly represented."""
    cdef = """
    struct test {
        uint8 cube[2][3][2];
        uint16 after;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\xff\x00"
    result = utils.dumpstruct(cs.test, buf, output="dict")

    assert result == {
        "bytes": "0102030405060708090a0b0cff00",
        "root": "test",
        "types": {
            "test": [
                {"name": "cube[2][3][2]", "type": "uint8"},
                {"name": "after", "type": "uint16"},
            ],
        },
        "sizes": {
            "cube[2][3][2]": 12,
            "after": 2,
        },
        "values": {
            "cube[2][3][2]": "[[[1, 2], [3, 4], [5, 6]], [[7, 8], [9, 10], [11, 12]]]",
            "after": "0xff",
        },
    }


def test_dumpstruct_json_output(cs: cstruct, compiled: bool) -> None:
    """Verify the output='json' path returns valid JSON matching the dict output."""
    cdef = """
    struct test {
        uint32 id;
        uint16 value;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x00\x00\x00\x02\x00"
    dict_result = utils.dumpstruct(cs.test, buf, output="dict")
    json_result = utils.dumpstruct(cs.test, buf, output="json")

    assert isinstance(json_result, str)
    assert json.loads(json_result) == dict_result


def test_dumpstruct_print_returns_none(cs: cstruct, capsys: pytest.CaptureFixture, compiled: bool) -> None:
    """Verify that output='print' returns None and actually prints."""
    cdef = """
    struct test {
        uint32 val;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x00\x00\x00"
    result = utils.dumpstruct(cs.test, buf, output="print")
    captured = capsys.readouterr()

    assert result is None
    assert "struct test:" in captured.out
    assert "val" in captured.out


def test_dumpstruct_invalid_args(cs: cstruct, compiled: bool) -> None:
    """Verify that invalid arguments raise ValueError."""
    cdef = """
    struct test {
        uint32 val;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    # Class without data
    with pytest.raises(ValueError, match="Invalid arguments"):
        utils.dumpstruct(cs.test)

    # Non-Structure type
    with pytest.raises((ValueError, TypeError)):
        utils.dumpstruct(42)


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

    result = utils.dumpstruct(cs.complex, buf, output="dict")

    assert result == {
        "bytes": "350100000a001400ff8040efbeadde010203040506feca",
        "root": "complex",
        "types": {
            "complex": [
                {
                    "type": "uint32",
                    "bitfields": [
                        {"name": "flags", "bits": 4},
                        {"name": "version", "bits": 4},
                        {"name": "reserved", "bits": 24},
                    ],
                },
                {"name": "origin", "type": "point"},
                {
                    "name": "__anonymous_0__",
                    "type": "struct",
                    "anonymous": True,
                    "fields": [
                        {"name": "r", "type": "uint8"},
                        {"name": "g", "type": "uint8"},
                        {"name": "b", "type": "uint8"},
                    ],
                },
                {
                    "name": "data",
                    "type": "union",
                    "fields": [
                        {"name": "as_int", "type": "uint32"},
                        {"name": "as_bytes[4]", "type": "uint8"},
                    ],
                },
                {"name": "matrix[2][3]", "type": "uint8"},
                {"name": "checksum", "type": "uint16"},
            ],
            "point": [
                {"name": "x", "type": "uint16"},
                {"name": "y", "type": "uint16"},
            ],
        },
        "sizes": {
            "flags": 4,
            "origin": 4,
            "origin.x": 2,
            "origin.y": 2,
            "r": 1,
            "g": 1,
            "b": 1,
            "data": 4,
            "data.as_int": 4,
            "data.as_bytes[4]": 4,
            "matrix[2][3]": 6,
            "checksum": 2,
        },
        "values": {
            "flags": "0x5",
            "version": "0x3",
            "reserved": "0x1",
            "origin.x": "0xa",
            "origin.y": "0x14",
            "r": "0xff",
            "g": "0x80",
            "b": "0x40",
            "data.as_int": "0xdeadbeef",
            "data.as_bytes[4]": "[239, 190, 173, 222]",
            "matrix[2][3]": "[[1, 2, 3], [4, 5, 6]]",
            "checksum": "0xcafe",
        },
    }

    # Validate string output covers all fields correctly
    out = utils.dumpstruct(cs.complex, buf, color=False, output="string")
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

    out = utils.dumpstruct(cs.test, buf, color=True, output="string")
    lines = out.split("\n")

    # Foreground/background color cycle used by dumpstruct, derived from utils constants
    FG = [
        utils.COLOR_RED_BOLD,
        utils.COLOR_GREEN_BOLD,
        utils.COLOR_YELLOW_BOLD,
        utils.COLOR_BLUE_BOLD,
        utils.COLOR_PURPLE_BOLD,
        utils.COLOR_CYAN_BOLD,
        utils.COLOR_WHITE_BOLD,
    ]
    BG = [
        utils.COLOR_BG_RED,
        utils.COLOR_BG_GREEN,
        utils.COLOR_BG_YELLOW,
        utils.COLOR_BG_BLUE,
        utils.COLOR_BG_PURPLE,
        utils.COLOR_BG_CYAN,
        utils.COLOR_BG_WHITE,
    ]
    RESET = utils.COLOR_CLEAR

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
        r"(" + "|".join(re.escape(bg) for bg in BG) + r")((?:[0-9a-f]{2}\s*)+)" + re.escape(utils.COLOR_CLEAR_BOLD)
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

    for (actual_bg, actual_bytes), (exp_bg, exp_bytes, label) in zip(bg_regions, expected):
        assert actual_bg == exp_bg, f"{label}: expected bg={exp_bg!r}, got {actual_bg!r}"
        assert actual_bytes == exp_bytes, f"{label}: expected bytes {exp_bytes}, got {actual_bytes}"

    # Total palette bytes must equal data length
    total_palette_bytes = sum(len(b) for _, b in bg_regions)
    assert total_palette_bytes == len(buf), f"Palette covers {total_palette_bytes} bytes but data is {len(buf)} bytes"


def test_dumpstruct_dict_struct_array(cs: cstruct, compiled: bool) -> None:
    """Verify how arrays of structs are represented."""
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
    result = utils.dumpstruct(cs.test, buf, output="dict")

    assert result == {
        "bytes": "020a0014001e002800ff",
        "root": "test",
        "types": {
            "test": [
                {"name": "count", "type": "uint8"},
                {"name": "items[2]", "type": "point"},
                {"name": "tail", "type": "uint8"},
            ],
            "point": [
                {"name": "x", "type": "uint16"},
                {"name": "y", "type": "uint16"},
            ],
        },
        "sizes": {
            "count": 1,
            "items[2]": 8,
            "tail": 1,
        },
        "values": {
            "count": "0x2",
            "items[2]": "[<point x=0xa y=0x14>, <point x=0x1e y=0x28>]",
            "tail": "0xff",
        },
    }


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
