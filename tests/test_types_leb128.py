from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.exception import WriteError

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_leb128_unsigned_read_EOF(cs: cstruct) -> None:
    with pytest.raises(EOFError, match="EOF reached, while final LEB128 byte was not yet read"):
        cs.uleb128(b"\x8b")


@pytest.mark.parametrize(
    ("type_name", "buf", "value"),
    [
        ("uleb128", b"\x02", 2),
        ("uleb128", b"\x8b\x25", 4747),
        ("uleb128", b"\xc9\x8f\xb0\x06", 13371337),
        ("uleb128", b"\x7e", 126),
        ("uleb128", b"\xf5\x5a", 11637),
        ("uleb128", b"\xde\xd6\xcf\x7c", 261352286),
        ("ileb128", b"\x02", 2),
        ("ileb128", b"\x8b\x25", 4747),
        ("ileb128", b"\xc9\x8f\xb0\x06", 13371337),
        ("ileb128", b"\x7e", -2),
        ("ileb128", b"\xf5\x5a", -4747),
        ("ileb128", b"\xde\xd6\xcf\x7c", -7083170),
        # Bit 6 of the last byte is the sign, so a value that doesn't fit in the other bits takes an extra byte
        ("ileb128", b"\x3f", 63),
        ("ileb128", b"\xc0\x00", 64),
        ("ileb128", b"\x40", -64),
        ("ileb128", b"\xbf\x7f", -65),
    ],
)
def test_leb128_read_write(cs: cstruct, type_name: str, buf: bytes, value: int) -> None:
    """Test reading and writing LEB128 values, and that writing returns the amount of bytes written."""
    type_ = cs.resolve(type_name)

    assert type_(buf) == value
    assert bytes(type_(value)) == buf
    assert type_.write(io.BytesIO(), value) == len(buf)


def test_leb128_struct_unsigned(cs: cstruct) -> None:
    cdef = """
    struct test {
        uleb128 len;
        char    data[len];
    };
    """
    cs.load(cdef)

    buf = b"\xaf\x18"
    buf += b"\x41" * 3119
    obj = cs.test(buf)

    assert obj.len == 3119
    assert obj.data == (b"\x41" * 3119)

    assert bytes(obj) == buf


@pytest.mark.parametrize(
    ("type_name", "buf", "numbers"),
    [
        ("uleb128", b"\xaf\x18\x8b\x25\xc9\x8f\xb0\x06\x00", [3119, 4747, 13371337]),
        ("ileb128", b"\xaf\x18\xf5\x5a\xde\xd6\xcf\x7c\x00", [3119, -4747, -7083170]),
    ],
)
def test_leb128_struct_zero(cs: cstruct, type_name: str, buf: bytes, numbers: list[int]) -> None:
    """Test that a null-terminated array of LEB128 values ends at a zero."""
    cdef = f"""
    struct test {{
        {type_name} numbers[];
    }};
    """
    cs.load(cdef)

    obj = cs.test(buf)
    assert obj.numbers == numbers

    assert bytes(obj) == buf


@pytest.mark.parametrize("type_name", ["uleb128", "ileb128"])
def test_leb128_nested_struct(cs: cstruct, type_name: str) -> None:
    """Test that LEB128 values can be used as the size of arrays in nested structures."""
    cdef = f"""
    struct entry {{
        {type_name} len;
        char    data[len];
        uint32  crc;
    }};
    struct nested {{
        {type_name} name_len;
        char    name[name_len];
        {type_name} n_entries;
        entry   entries[n_entries];
    }};
    """
    cs.load(cdef)

    # Dummy file format specifying 300 entries
    buf = b"\x08\x54\x65\x73\x74\x66\x69\x6c\x65\xac\x02"

    # Each entry has 4 byte data + 4 byte CRC
    buf += b"\x04\x41\x41\x41\x41\x42\x42\x42\x42" * 300

    obj = cs.nested(buf)

    assert obj.name_len == 8
    assert obj.name == b"\x54\x65\x73\x74\x66\x69\x6c\x65"
    assert obj.n_entries == 300

    assert bytes(obj) == buf


def test_leb128_write_negatives(cs: cstruct) -> None:
    with pytest.raises(WriteError, match=r"^Attempt to encode a negative integer using unsigned LEB128 encoding$"):
        bytes(cs.uleb128(-2))


def test_leb128_default(cs: cstruct) -> None:
    assert cs.uleb128.__default__() == 0
    assert cs.ileb128.__default__() == 0

    assert cs.uleb128[1].__default__() == [0]
    assert cs.uleb128[None].__default__() == []
