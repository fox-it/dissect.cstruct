from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.exception import WriteError
from tests.util import NonSeekableStream, verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


@pytest.mark.parametrize(
    ("endian", "buf"),
    [
        ("<", b"A\x00A\x00A\x00A\x00\x00\x00"),
        (">", b"\x00A\x00A\x00A\x00A\x00\x00"),
    ],
)
def test_wchar_read(cs: cstruct, endian: str, buf: bytes) -> None:
    cs.endian = endian

    assert cs.wchar("A") == "A"
    assert cs.wchar(buf) == "A"
    assert cs.wchar(io.BytesIO(buf)) == "A"


@pytest.mark.parametrize(
    ("endian", "buf"),
    [
        ("<", b"A\x00"),
        (">", b"\x00A"),
    ],
)
def test_wchar_write(cs: cstruct, endian: str, buf: bytes) -> None:
    cs.endian = endian

    assert bytes(cs.wchar("A")) == buf
    assert bytes(cs.wchar(buf)) == buf


@pytest.mark.parametrize(
    ("endian", "buf"),
    [
        ("<", b"A\x00A\x00A\x00A\x00\x00\x00"),
        (">", b"\x00A\x00A\x00A\x00A\x00\x00"),
    ],
)
def test_wchar_array(cs: cstruct, endian: str, buf: bytes) -> None:
    cs.endian = endian

    assert cs.wchar[4]("AAAA") == "AAAA"
    assert cs.wchar[4](buf) == "AAAA"
    assert cs.wchar[4](io.BytesIO(buf)) == "AAAA"
    assert cs.wchar[None](buf) == "AAAA"
    assert cs.wchar[None](io.BytesIO(buf)) == "AAAA"


@pytest.mark.parametrize(
    ("endian", "buf"),
    [
        ("<", b"A\x00A\x00A\x00A\x00\x00\x00"),
        (">", b"\x00A\x00A\x00A\x00A\x00\x00"),
    ],
)
def test_wchar_array_write(cs: cstruct, endian: str, buf: bytes) -> None:
    cs.endian = endian

    assert bytes(cs.wchar[4](buf)) == buf[:-2]
    assert bytes(cs.wchar[4]("AAAA")) == buf[:-2]
    assert bytes(cs.wchar[None](buf)) == buf[:-2]
    assert bytes(cs.wchar[None]("AAAA")) == buf[:-2]
    assert cs.wchar[None].dumps(cs.wchar[None](buf)) == buf


def test_wchar_array_write_padding(cs: cstruct) -> None:
    buf = io.BytesIO()
    cs.wchar[8]._write(buf, "hi", endian=cs.endian)
    assert buf.getvalue() == b"h\x00i\x00" + b"\x00" * 12

    cdef = """
    struct test_struct {
        int x;
        wchar y[8];
        wchar z[16];
    };
    """
    cs.load(cdef)
    obj = cs.test_struct()
    obj.x = 4
    obj.y = "hi"
    obj.z = "bye"
    assert len(bytes(obj)) == len(cs.test_struct)
    assert bytes(obj) == b"\x04\x00\x00\x00h\x00i\x00" + (b"\x00" * 12) + b"b\x00y\x00e\x00" + (b"\x00" * 26)


def test_wchar_array_write_size_error(cs: cstruct) -> None:
    buf = io.BytesIO()
    with pytest.raises(WriteError, match=re.escape("Expected static array size 4, got 7 instead.")):
        cs.wchar[4]._write(buf, "toolong", endian=cs.endian)


def test_wchar_eof(cs: cstruct) -> None:
    with pytest.raises(EOFError, match="Read 1 bytes, but expected 2"):
        cs.wchar(b"A")

    with pytest.raises(EOFError, match="Read 0 bytes, but expected 8"):
        cs.wchar[4](b"")

    with pytest.raises(EOFError, match="Read 0 bytes, but expected 2"):
        cs.wchar[None](b"A\x00A\x00A\x00A\x00")

    # More bytes than any stream can hold, e.g. a count from corrupt data
    with pytest.raises(EOFError, match=r"^Read 0 bytes, but expected 9223372036854775808$"):
        cs.wchar[2**62](b"")

    assert cs.wchar[0](b"") == ""


def test_wchar_value(cs: cstruct) -> None:
    """Test that a ``wchar`` and ``wchar`` array behave as expected when given sensible values."""
    assert cs.wchar() == "\x00"
    assert cs.wchar("") == "\x00"
    assert cs.wchar[4]("ab") == "ab\x00\x00"
    assert cs.wchar[4]("äö") == "äö\x00\x00"
    assert cs.wchar[4]() == "\x00\x00\x00\x00"
    assert cs.wchar[None]("ab") == "ab"
    assert cs.wchar[None]() == ""

    # Values of other cstruct types, which are subclasses of str
    assert cs.wchar[2](cs.wchar[2]("ab")) == "ab"
    assert cs.wchar[4](cs.wchar("a")) == "a\x00\x00\x00"

    # A surrogate pair is a single character that takes up two entries
    assert cs.wchar[4]("a\U0001f600") == "a\U0001f600\x00"
    assert cs.wchar[2]("\U0001f600") == "\U0001f600"

    with pytest.raises(ValueError, match=r"^Expected a single character, got 2 instead\.$"):
        cs.wchar("xy")

    with pytest.raises(ValueError, match=r"^Expected a single character, got 2 instead\.$"):
        cs.wchar("\U0001f600")

    with pytest.raises(ValueError, match=r"^Expected static array size 4, got 5 instead\.$"):
        cs.wchar[4]("abcde")

    with pytest.raises(ValueError, match=r"^Expected static array size 2, got 3 instead\.$"):
        cs.wchar[2]("a\U0001f600")

    # Other values aren't converted with str(), which would give e.g. the digits of an int
    with pytest.raises(TypeError, match=r"^Cannot create wchar from int$"):
        cs.wchar(65)

    with pytest.raises(TypeError, match=r"^Cannot create wchar\[4\] from int$"):
        cs.wchar[4](65)

    with pytest.raises(TypeError, match=r"^Cannot create wchar\[\] from list$"):
        cs.wchar[None]([65, 66])


def test_wchar_default(cs: cstruct) -> None:
    assert cs.wchar.__default__() == "\x00"
    assert cs.wchar[4].__default__() == "\x00\x00\x00\x00"
    assert cs.wchar[None].__default__() == ""


@pytest.mark.parametrize("stream_type", [io.BytesIO, NonSeekableStream])
@pytest.mark.parametrize("length", [0, 1, 127, 128, 129, 300])
def test_wchar_null_terminated(cs: cstruct, stream_type: type, length: int) -> None:
    """Test reading null-terminated wchar arrays from seekable and non-seekable streams."""
    text = "".join(chr(0x41 + i % 26) for i in range(length))
    data = text.encode("utf-16-le")

    fh = stream_type(data + b"\x00\x00rest")
    assert cs.wchar[None](fh) == text
    assert fh.read() == b"rest"

    with pytest.raises(EOFError, match="Read 0 bytes, but expected 2"):
        cs.wchar[None](stream_type(data))

    with pytest.raises(EOFError, match="Read 1 bytes, but expected 2"):
        cs.wchar[None](stream_type(data + b"\x41"))


def test_wchar_null_terminated_alignment(cs: cstruct) -> None:
    """Test that only an aligned double null byte ends a null-terminated wchar array."""
    # The double null byte at an odd offset is not a terminator
    fh = io.BytesIO(b"A\x00\x00\x01\x00\x00rest")
    assert cs.wchar[None](fh) == "AĀ"
    assert fh.read() == b"rest"

    # Terminator right at a chunk boundary
    data = "x".encode("utf-16-le") * 127
    fh = io.BytesIO(data + b"\x00\x00rest")
    assert cs.wchar[None](fh) == "x" * 127
    assert fh.read() == b"rest"


def test_wchar_array_surrogate_pair(cs: cstruct, compiled: bool) -> None:
    """Test that a surrogate pair takes up two entries of a ``wchar`` array, so that it pads to the right size."""
    cdef = """
    struct test {
        wchar a[4];
        uint8 b;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert cs.wchar[4].dumps("\U0001f600") == b"\x3d\xd8\x00\xde\x00\x00\x00\x00"
    assert cs.wchar[2].dumps("\U0001f600") == b"\x3d\xd8\x00\xde"

    with pytest.raises(WriteError, match="Expected static array size 1, got 2 instead"):
        cs.wchar[1].dumps("\U0001f600")

    buf = b"\x3d\xd8\x00\xdex\x00\x00\x00\x01"
    obj = cs.test(buf)
    assert obj.a == "\U0001f600x\x00"
    assert bytes(obj) == buf

    obj.a = "abcde"
    with pytest.raises(WriteError, match="Expected static array size 4, got 5 instead"):
        bytes(obj)

    obj.a = "\U0001f600\U0001f600\U0001f600"
    with pytest.raises(WriteError, match="Expected static array size 4, got 6 instead"):
        bytes(obj)


def test_wchar_write_too_long(cs: cstruct, compiled: bool) -> None:
    """Test that writing more than a single character to a ``wchar`` raises an error, instead of writing all of it."""
    cdef = """
    struct test {
        uint8 a;
        wchar b;
        uint8 c;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert cs.wchar.dumps("x") == b"x\x00"

    with pytest.raises(WriteError, match=r"^Expected a single character, got 2 instead\.$"):
        cs.wchar.dumps("xy")

    # A surrogate pair doesn't fit a single wchar
    with pytest.raises(WriteError, match=r"^Expected a single character, got 2 instead\.$"):
        cs.wchar.dumps("\U0001f600")

    obj = cs.test(a=1, c=2)
    obj.b = "xy"
    with pytest.raises(WriteError, match=r"^Expected a single character, got 2 instead\.$"):
        bytes(obj)

    obj.b = "\U0001f600"
    with pytest.raises(WriteError, match=r"^Expected a single character, got 2 instead\.$"):
        bytes(obj)


def test_wchar_write_too_short(cs: cstruct, compiled: bool) -> None:
    """Test that an empty ``wchar`` is padded, so that a structure always writes all of its fields."""
    cdef = """
    struct test {
        uint8 a;
        wchar b;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert cs.wchar.dumps("") == b"\x00\x00"
    assert bytes(cs.test(a=1, b="")) == b"\x01\x00\x00"


@pytest.mark.parametrize(
    ("endian", "buf", "expected"),
    [
        ("<", b"a\x00\x00\xd8", "a\ud800"),
        ("<", b"\x00\xd8a\x00", "\ud800a"),
        ("<", b"a\x00\x00\xdc", "a\udc00"),
        ("<", b"\x00\xdca\x00", "\udc00a"),
        ("<", b"\x00\xdc\x00\xd8", "\udc00\ud800"),
        ("<", b"\x00\xd8\x00\xd8", "\ud800\ud800"),
        (">", b"\x00a\xd8\x00", "a\ud800"),
        (">", b"\xdc\x00\xd8\x00", "\udc00\ud800"),
    ],
)
def test_wchar_lone_surrogate(cs: cstruct, compiled: bool, endian: str, buf: bytes, expected: str) -> None:
    """Test that a lone surrogate is read and written back as stored, for every kind of ``wchar`` array."""
    cdef = """
    struct dynamic_array {
        uint8 length;
        wchar text[length];
    };

    struct static_array {
        wchar text[2];
        uint8 after;
    };

    struct null_terminated {
        wchar text[];
        uint8 after;
    };

    struct until_eof {
        wchar text[EOF];
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.endian = endian

    assert verify_compiled(cs.dynamic_array, compiled)
    assert verify_compiled(cs.static_array, compiled)
    assert verify_compiled(cs.null_terminated, compiled)
    assert verify_compiled(cs.until_eof, compiled)

    data = b"\x02" + buf
    obj = cs.dynamic_array(data)
    assert obj.text == expected
    assert bytes(obj) == data

    data = buf + b"\x01"
    obj = cs.static_array(data)
    assert obj.text == expected
    assert obj.after == 1
    assert bytes(obj) == data

    data = buf + b"\x00\x00\x01"
    obj = cs.null_terminated(data)
    assert obj.text == expected
    assert obj.after == 1
    assert bytes(obj) == data

    for stream_type in (io.BytesIO, NonSeekableStream):
        assert cs.wchar[None](stream_type(data)) == expected

    obj = cs.until_eof(buf)
    assert obj.text == expected
    assert bytes(obj) == buf


def test_wchar_lone_surrogate_single(cs: cstruct, compiled: bool) -> None:
    """Test that a single ``wchar`` can hold a lone surrogate."""
    cdef = """
    struct test {
        wchar a;
        wchar b;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert cs.wchar(b"\x00\xd8") == "\ud800"
    assert cs.wchar.dumps("\ud800") == b"\x00\xd8"

    buf = b"\x3d\xd8\x00\xde"
    obj = cs.test(buf)
    assert obj.a == "\ud83d"
    assert obj.b == "\ude00"
    assert bytes(obj) == buf

    # Two lone surrogates take up the same space as the surrogate pair they make up
    with pytest.raises(WriteError, match=r"^Expected a single character, got 2 instead\.$"):
        cs.wchar.dumps("\ud83d\ude00")


def test_wchar_truncated(cs: cstruct, compiled: bool) -> None:
    """Test that half of a ``wchar`` still raises an error, unlike a lone surrogate."""
    cdef = """
    struct test {
        wchar text[EOF];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert cs.test(b"\x00\xd8").text == "\ud800"

    with pytest.raises(EOFError, match=r"^Read 1 bytes, but expected 2$"):
        cs.test(b"\x00\xd8\x00")
