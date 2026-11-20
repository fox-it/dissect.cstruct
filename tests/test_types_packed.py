from __future__ import annotations

import array
import io
import struct
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.exception import WriteError
from tests.util import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


@pytest.mark.parametrize(
    ("endian", "type_name", "buf", "value"),
    [
        ("<", "uint32", b"AAAA", 0x41414141),
        ("<", "uint32", b"\xff\xff\xff\xff", 0xFFFFFFFF),
        ("<", "int32", b"\xff\x00\x00\x00", 255),
        ("<", "int32", b"\xff\xff\xff\xff", -1),
        ("<", "float16", b"\x00\x3c", 1.0),
        ("<", "float", b"\x00\x00\x80\x3f", 1.0),
        ("<", "double", b"\x00\x00\x00\x00\x00\x00\xf0\x3f", 1.0),
        (">", "uint32", b"AAA\x00", 0x41414100),
        (">", "uint32", b"\xff\xff\xff\x00", 0xFFFFFF00),
        (">", "int32", b"\x00\x00\x00\xff", 255),
        (">", "int32", b"\xff\xff\xff\xff", -1),
        (">", "float16", b"\x3c\x00", 1.0),
        (">", "float", b"\x3f\x80\x00\x00", 1.0),
        (">", "double", b"\x3f\xf0\x00\x00\x00\x00\x00\x00", 1.0),
    ],
)
def test_packed_read_write(cs: cstruct, endian: str, type_name: str, buf: bytes, value: float) -> None:
    """Test reading and writing packed types of different sizes, signedness and endianness."""
    cs.endian = endian
    packed_type = cs.resolve(type_name)

    assert packed_type(buf) == value
    assert bytes(packed_type(value)) == buf


@pytest.mark.parametrize(
    ("endian", "type_name", "count", "buf", "values"),
    [
        ("<", "uint32", 2, b"AAAABBBB", [0x41414141, 0x42424242]),
        ("<", "uint32", None, b"AAAABBBB\x00\x00\x00\x00", [0x41414141, 0x42424242]),
        ("<", "int32", 2, b"\x00\x00\x00\x00\xff\xff\xff\xff", [0, -1]),
        ("<", "int32", None, b"\xff\xff\xff\xff\x00\x00\x00\x00", [-1]),
        ("<", "float", 2, b"\x00\x00\x80\x3f\x00\x00\x00\x40", [1.0, 2.0]),
        ("<", "float", None, b"\x00\x00\x80\x3f\x00\x00\x00\x00", [1.0]),
        (">", "uint32", 2, b"\x00\x00\x00\x01\x00\x00\x00\x02", [1, 2]),
        (">", "uint32", None, b"\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x00", [1, 2]),
        (">", "int32", 2, b"\x00\x00\x00\x01\xff\xff\xff\xfe", [1, -2]),
        (">", "int32", None, b"\xff\xff\xff\xfe\x00\x00\x00\x00", [-2]),
        (">", "float", 2, b"\x3f\x80\x00\x00\x40\x00\x00\x00", [1.0, 2.0]),
        (">", "float", None, b"\x3f\x80\x00\x00\x00\x00\x00\x00", [1.0]),
    ],
)
def test_packed_array_read_write(
    cs: cstruct, endian: str, type_name: str, count: int | None, buf: bytes, values: list[float]
) -> None:
    """Test reading and writing fixed size and null-terminated arrays of packed types."""
    cs.endian = endian
    packed_type = cs.resolve(type_name)

    assert packed_type[count](buf) == values
    assert bytes(packed_type[count](values)) == buf


def test_packed_eof(cs: cstruct) -> None:
    with pytest.raises(EOFError, match="Read 1 bytes, but expected 4"):
        cs.uint32(b"\x00")

    with pytest.raises(EOFError, match="Read 4 bytes, but expected 8"):
        cs.uint32[2](b"\x00\x00\x00\x00")

    with pytest.raises(EOFError, match="Read 0 bytes, but expected 4"):
        cs.uint32[None](b"\x00\x00\x00\x01")

    # More bytes than any stream can hold, e.g. a count from corrupt data
    with pytest.raises(EOFError, match=r"^Read 0 bytes, but expected 18446744073709551616$"):
        cs.uint32[2**62](b"")


def test_packed_range(cs: cstruct) -> None:
    assert bytes(cs.float16(-65519.999999999996)) == b"\xff\xfb"
    assert bytes(cs.float16(65519.999999999996)) == b"\xff\x7b"
    with pytest.raises(WriteError, match=r"^Cannot write float16: "):
        bytes(cs.float16(-65519.999999999997))
    with pytest.raises(WriteError, match=r"^Cannot write float16: "):
        bytes(cs.float16(65519.999999999997))


@pytest.mark.parametrize(
    ("endian", "buf", "a"),
    [
        ("<", b"69\xb1U$G", 0.6513671875),
        (">", b"69G$U\xb1", 0.388916015625),
    ],
)
def test_packed_float_struct(cs: cstruct, compiled: bool, endian: str, buf: bytes, a: float) -> None:
    cdef = """
    struct test {
        float16 a;
        float   b;
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.endian = endian

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(buf)

    assert obj.a == a
    assert obj.b == 42069.69140625
    assert bytes(obj) == buf


def test_packed_default(cs: cstruct) -> None:
    assert cs.int8.__default__() == 0
    assert cs.uint8.__default__() == 0
    assert cs.int16.__default__() == 0
    assert cs.uint16.__default__() == 0
    assert cs.int32.__default__() == 0
    assert cs.uint32.__default__() == 0
    assert cs.int64.__default__() == 0
    assert cs.uint64.__default__() == 0
    assert cs.float16.__default__() == 0.0
    assert cs.float.__default__() == 0.0
    assert cs.double.__default__() == 0.0

    assert cs.int8[2].__default__() == [0, 0]
    assert cs.int8[None].__default__() == []


@pytest.mark.parametrize(
    "factory",
    [bytes, bytearray, memoryview, lambda data: memoryview(bytearray(data))],
    ids=["bytes", "bytearray", "memoryview", "memoryview-bytearray"],
)
def test_packed_buffer_types(cs: cstruct, factory: type) -> None:
    """Test reading packed types from different bytes-like objects."""
    data = b"\x01\x02\x03\x04\x05"

    assert cs.uint32(factory(data)) == 0x04030201
    assert cs.uint32.reads(factory(data)) == 0x04030201
    assert cs.uint32.read(factory(data)) == 0x04030201
    assert cs.uint32(factory(data), endian=">") == 0x01020304
    assert type(cs.uint32(factory(data))) is cs.uint32

    with pytest.raises(EOFError, match="Read 2 bytes, but expected 4"):
        cs.uint32(factory(data[:2]))


def test_packed_stream(cs: cstruct) -> None:
    """Test reading packed types from a stream, which continues after each value that is read."""
    fh = io.BytesIO(b"\x01\x00\x00\x00\x02\x00")
    assert cs.uint32(fh) == 1
    assert cs.uint16(fh) == 2
    assert fh.read() == b""


def test_packed_memoryview_formats(cs: cstruct) -> None:
    """Test reading packed types from memoryviews with a different format or stride."""
    assert cs.uint32(memoryview(array.array("I", [7, 8]))) == 7
    assert cs.uint8(memoryview(array.array("I", [7, 8]))) == 7

    # Non-contiguous memoryviews are handled like the struct module does, which differs per Python implementation
    # E.g. PyPy 3.10 reads the bytes of the view, other versions raise a BufferError
    view = memoryview(bytearray(range(16)))[::2]
    try:
        expected = struct.unpack_from("<I", view)[0]
    except BufferError:
        with pytest.raises(BufferError):
            cs.uint32(view)
    else:
        assert cs.uint32(view) == expected


def test_packed_struct_write_range(cs: cstruct, compiled: bool) -> None:
    """Test that a value that doesn't fit its field raises an error when writing a structure."""
    cdef = """
    struct test {
        uint8   a;
        int16   b;
        uint32  c;
        double  d;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert bytes(cs.test(a=1, b=-2, c=3, d=1.0)) == b"\x01\xfe\xff\x03\x00\x00\x00\x00\x00\x00\x00\x00\x00\xf0\x3f"

    with pytest.raises(WriteError, match=r"^Cannot write test: "):
        bytes(cs.test(a=1, b=2, c=2**32, d=4.0))

    with pytest.raises(WriteError, match=r"^Cannot write test: "):
        bytes(cs.test(a=256, b=2, c=3, d=4.0))


def test_packed_signed(cs: cstruct) -> None:
    """Test that the signed attribute is set correctly for packed types."""
    assert cs.int8.__signed__ is True
    assert cs.uint8.__signed__ is False
    assert cs.int16.__signed__ is True
    assert cs.uint16.__signed__ is False
    assert cs.int32.__signed__ is True
    assert cs.uint32.__signed__ is False
    assert cs.int64.__signed__ is True
    assert cs.uint64.__signed__ is False
    assert cs.float16.__signed__ is True
    assert cs.float.__signed__ is True
    assert cs.double.__signed__ is True
