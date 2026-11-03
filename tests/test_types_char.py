from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.exception import ArraySizeError

from .utils import NonSeekableStream

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


@pytest.mark.parametrize("stream_type", [io.BytesIO, NonSeekableStream])
@pytest.mark.parametrize("length", [0, 1, 127, 128, 129, 300])
def test_char_null_terminated(cs: cstruct, stream_type: type, length: int) -> None:
    """Test reading null-terminated char arrays from seekable and non-seekable streams."""
    data = b"".join(bytes([0x41 + i % 26]) for i in range(length))

    fh = stream_type(data + b"\x00rest")
    assert cs.char[None](fh) == data
    assert fh.read() == b"rest"

    with pytest.raises(EOFError, match="Read 0 bytes, but expected 1"):
        cs.char[None](stream_type(data))


def test_char_array_bytearray_not_modified(cs: cstruct, compiled: bool) -> None:
    """Test that writing a ``bytearray`` to a ``char`` array doesn't modify the ``bytearray`` when padding it."""
    cdef = """
    struct test {
        char a[4];
        char b[];
    };
    """
    cs.load(cdef, compiled=compiled)

    a = bytearray(b"a")
    b = bytearray(b"b")
    assert cs.test(a=a, b=b).dumps() == b"a\x00\x00\x00b\x00"
    assert a == b"a"
    assert b == b"b"


def test_char_write_too_long(cs: cstruct) -> None:
    """Test that writing more than a single character to a ``char`` raises an error, instead of writing all of it."""
    assert cs.char.dumps(b"x") == b"x"
    assert cs.char.dumps("x") == b"x"
    assert cs.char.dumps(0x78) == b"x"

    with pytest.raises(ValueError, match="Expected a single character, got 2 instead"):
        cs.char.dumps(b"xy")

    with pytest.raises(ValueError, match="Expected a single character, got 2 instead"):
        cs.char.dumps("xy")


def test_char_write_too_short(cs: cstruct, compiled: bool) -> None:
    """Test that an empty ``char`` is padded, so that a structure always writes all of its fields."""
    cdef = """
    struct test {
        uint8 a;
        char  b;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert cs.char.dumps(b"") == b"\x00"
    assert cs.test(a=1, b=b"").dumps() == b"\x01\x00"
