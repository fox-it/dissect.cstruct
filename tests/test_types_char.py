from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.exception import ArraySizeError

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_char_read(cs: cstruct) -> None:
    assert cs.char(b"A") == b"A"
    assert cs.char(b"AAAA\x00") == b"A"
    assert cs.char(io.BytesIO(b"AAAA\x00")) == b"A"


def test_char_write(cs: cstruct) -> None:
    assert cs.char(b"A").dumps() == b"A"


def test_char_array(cs: cstruct) -> None:
    buf = b"AAAA\x00"

    assert cs.char[4](buf) == b"AAAA"
    assert cs.char[4](io.BytesIO(buf)) == b"AAAA"

    assert cs.char[None](buf) == b"AAAA"
    assert cs.char[None](io.BytesIO(buf)) == b"AAAA"


def test_char_array_write(cs: cstruct) -> None:
    buf = b"AAAA\x00"

    assert cs.char[4](buf).dumps() == b"AAAA"
    assert cs.char[None](buf).dumps() == b"AAAA\x00"


def test_char_array_write_padding(cs: cstruct) -> None:
    buf = io.BytesIO()
    cs.char[8]._write(buf, "hi", endian=cs.endian)
    assert buf.getvalue() == b"hi\x00\x00\x00\x00\x00\x00"

    cdef = """
    struct test_struct {
        int x;
        char y[8];
        char z[16];
    };
    """
    cs.load(cdef)

    obj = cs.test_struct()
    obj.x = 4
    obj.y = "hi"
    obj.z = "bye"

    assert len(obj.dumps()) == len(cs.test_struct)
    assert (
        obj.dumps()
        == b"\x04\x00\x00\x00hi\x00\x00\x00\x00\x00\x00bye\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    )


def test_char_array_write_size_error(cs: cstruct) -> None:
    buf = io.BytesIO()
    with pytest.raises(ArraySizeError):
        cs.char[4]._write(buf, b"toolong", endian=cs.endian)


def test_char_eof(cs: cstruct) -> None:
    with pytest.raises(EOFError):
        cs.char(b"")

    with pytest.raises(EOFError):
        cs.char[4](b"")

    with pytest.raises(EOFError):
        cs.char[None](b"AAAA")

    assert cs.char[0](b"") == b""


def test_char_default(cs: cstruct) -> None:
    assert cs.char.__default__() == b"\x00"
    assert cs.char[4].__default__() == b"\x00\x00\x00\x00"
    assert cs.char[None].__default__() == b""
