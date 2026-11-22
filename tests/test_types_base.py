from __future__ import annotations

import io
import re
import sys
from typing import TYPE_CHECKING, BinaryIO

import pytest

from dissect.cstruct.exception import ReadError, ResolveError, WriteError
from dissect.cstruct.expression import Expression
from dissect.cstruct.types.base import BaseArray, BaseType
from tests.util import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import Endianness, cstruct


def test_array_size_mismatch(cs: cstruct) -> None:
    with pytest.raises(WriteError):
        cs.uint8[2].dumps([1, 2, 3])

    assert bytes(cs.uint8[2]([1, 2])) == b"\x01\x02"


def test_array_value(cs: cstruct) -> None:
    """Test that an array can be created from sensible values."""
    cdef = """
    struct point {
        uint8 x;
    };
    """
    cs.load(cdef)

    assert cs.uint8[4]([1, 2]) == [1, 2, 0, 0]
    assert cs.uint8[4]((1, 2)) == [1, 2, 0, 0]
    assert cs.uint8[4](x for x in (1, 2)) == [1, 2, 0, 0]
    assert cs.uint8[4]() == [0, 0, 0, 0]
    assert cs.uint8[None]([1, 2]) == [1, 2]
    assert cs.uint8[None]() == []
    assert cs.uleb128[4]([1, 2]) == [1, 2, 0, 0]

    # Values of other cstruct types, which are subclasses of list
    assert cs.uint8[2](cs.uint8[2]([1, 2])) == [1, 2]
    assert cs.uint8[4](cs.uint8[2]([1, 2])) == [1, 2, 0, 0]

    # Every entry of the padding is a new structure
    points = cs.point[3]([cs.point(x=1)])
    assert [point.x for point in points] == [1, 0, 0]
    assert points[1] is not points[2]

    with pytest.raises(ValueError, match=r"^Expected static array size 4, got 5 instead\.$"):
        cs.uint8[4]([1, 2, 3, 4, 5])

    # Not converted with list()
    with pytest.raises(TypeError, match=r"^Cannot create uint8\[4\] from int$"):
        cs.uint8[4](3)

    with pytest.raises(TypeError, match=r"^Cannot create uint8\[\] from str$"):
        cs.uint8[None]("ab")


def test_array_write_padding(cs: cstruct) -> None:
    buf = io.BytesIO()
    cs.uint8[4]._write(buf, [1, 2], endian=cs.endian)
    assert buf.getvalue() == b"\x01\x02\x00\x00"

    cdef = """
    struct point {
        uint8 x;
        uint8 y;
    };
    """
    cs.load(cdef)

    buf = io.BytesIO()
    cs.point[4]._write(buf, [cs.point(x=1, y=2)], endian=cs.endian)
    assert buf.getvalue() == b"\x01\x02" + b"\x00\x00" * 3


def test_array_write_padding_dynamic_entries(cs: cstruct, compiled: bool) -> None:
    """Test that an array of entries with a dynamic size is padded to its number of entries."""
    cdef = """
    struct entry {
        uint8   length;
        char    data[length];
    };

    struct test {
        uleb128 a[3];
        entry   b[2];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert cs.uleb128[3].dumps([1]) == b"\x01\x00\x00"

    with pytest.raises(WriteError, match=r"^Expected static array size 3, got 4 instead\.$"):
        cs.uleb128[3].dumps([1, 2, 3, 4])

    buf = bytes(cs.test(a=[1], b=[cs.entry(length=1, data=b"x")]))
    assert buf == b"\x01\x00\x00\x01x\x00"

    obj = cs.test(buf)
    assert obj.a == [1, 0, 0]
    assert [entry.data for entry in obj.b] == [b"x", b""]

    with pytest.raises(WriteError, match=r"^Expected static array size 2, got 3 instead\.$"):
        bytes(cs.test(a=[1], b=[cs.entry(), cs.entry(), cs.entry()]))


def test_array_bytes_null_terminated(cs: cstruct) -> None:
    """Test that ``bytes(obj)`` leaves out the null terminator of an array."""
    cdef = """
    struct point {
        uint8 x;
        uint8 y;
    };
    """
    cs.load(cdef)

    values = cs.uint16[None]([1, 2])
    assert bytes(values) == b"\x01\x00\x02\x00"
    assert cs.uint16[None].dumps(values) == b"\x01\x00\x02\x00\x00\x00"

    points = cs.point[None]([cs.point(x=1, y=2)])
    assert bytes(points) == b"\x01\x02"
    assert cs.point[None].dumps(points) == b"\x01\x02\x00\x00"


def test_array_large_count(cs: cstruct, compiled: bool) -> None:
    """Test that an array with a count beyond the end of the data raises an EOFError."""
    cdef = """
    struct entry {
        uint32  a;
        uint32  b;
    };

    struct test {
        uint32  count;
        entry   entries[count];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    with pytest.raises(EOFError):
        cs.test(b"\x00\x00\x00\x40" + bytes(16))


def test_eof(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test_char {
        char data[EOF];
    };

    struct test_wchar {
        wchar data[EOF];
    };

    struct test_packed {
        uint16 data[EOF];
    };

    struct test_int {
        uint24 data[EOF];
    };

    enum Test : uint16 {
        A = 1
    };

    struct test_enum {
        Test data[EOF];
    };

    struct test_eof_field {
        uint8 EOF;
        char data[EOF];
        uint8 remainder;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test_char, compiled)
    assert verify_compiled(cs.test_wchar, compiled)
    assert verify_compiled(cs.test_packed, compiled)
    assert verify_compiled(cs.test_int, compiled)
    assert verify_compiled(cs.test_enum, compiled)
    assert verify_compiled(cs.test_eof_field, compiled)

    test_char = cs.test_char(b"abc")
    assert test_char.data == b"abc"
    assert bytes(test_char) == b"abc"

    test_wchar = cs.test_wchar("abc".encode("utf-16-le"))
    assert test_wchar.data == "abc"
    assert bytes(test_wchar) == "abc".encode("utf-16-le")

    test_packed = cs.test_packed(b"\x01\x00\x02\x00")
    assert test_packed.data == [1, 2]
    assert bytes(test_packed) == b"\x01\x00\x02\x00"

    test_int = cs.test_int(b"\x01\x00\x00\x02\x00\x00")
    assert test_int.data == [1, 2]
    assert bytes(test_int) == b"\x01\x00\x00\x02\x00\x00"

    # A partial last element is a short read
    with pytest.raises(EOFError, match=r"^Read 1 bytes, but expected 2$"):
        cs.test_packed(b"\x01\x00\x02")

    with pytest.raises(EOFError, match=r"^Read 1 bytes, but expected 3$"):
        cs.test_int(b"\x01\x00\x00\x02")

    test_enum = cs.test_enum(b"\x01\x00")
    assert test_enum.data == [cs.Test.A]
    assert bytes(test_enum) == b"\x01\x00"

    test_eof_field = cs.test_eof_field(b"\x01a\x02")
    assert test_eof_field.data == b"a"
    assert test_eof_field.remainder == 2
    assert bytes(test_eof_field) == b"\x01a\x02"


@pytest.mark.parametrize(
    ("size", "buf", "expression"),
    [
        ("n / d", b"\x01\x00", "n / d"),
        ("n % d", b"\x01\x00", "n % d"),
        ("1 << (d - n)", b"\x02\x01", "1 << ( d - n )"),
    ],
)
def test_array_size_invalid(cs: cstruct, compiled: bool, size: str, buf: bytes, expression: str) -> None:
    """Test that an array size that can't be calculated from the data raises a ``ReadError``."""
    cdef = f"""
    struct test {{
        uint8   n;
        uint8   d;
        uint8   data[{size}];
    }};
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    # The rest of the message is the error of Python, which differs per version
    with pytest.raises(ReadError, match=f"^{re.escape(f'Invalid array size {expression!r}: ')}"):
        cs.test(buf)


def test_array_size_unknown_type(cs: cstruct, compiled: bool) -> None:
    """Test that an array size with an unknown type raises a ``ResolveError`` when reading, not a ``ReadError``."""
    cdef = """
    struct test {
        uint8   n;
        uint8   data[n * sizeof(unknown)];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    with pytest.raises(ResolveError, match=r"^Unknown type unknown$"):
        cs.test(b"\x01")


def test_custom_array_type(cs: cstruct, compiled: bool) -> None:
    class CustomType(BaseType):
        def __init__(self, value: bytes = b""):
            self.value = value.upper()

        @classmethod
        def _read(cls, stream: BinaryIO, *, context: dict | None = None, endian: Endianness) -> CustomType:
            length = stream.read(1)[0]
            value = stream.read(length)
            return type.__call__(cls, value)

        class __ArrayType__(BaseArray):
            @classmethod
            def __default__(cls) -> CustomType:
                return cls.__type__()

            @classmethod
            def _read(
                cls, stream: BinaryIO, *, context: dict | None = None, endian: Endianness, **kwargs
            ) -> CustomType:
                value = cls.__type__._read(stream, context=context, endian=endian)
                if str(cls.__num_entries__) == "lower":
                    value.value = value.value.lower()

                return value

    cs.add_custom_type("custom", CustomType)

    result = cs.custom(b"\x04asdf")
    assert isinstance(result, CustomType)
    assert result.value == b"ASDF"

    result = cs.custom["lower"](b"\x04asdf")
    assert isinstance(result, CustomType)
    assert result.value == b"asdf"

    cdef = """
    struct test {
        custom  a;
        custom  b[lower];
    };
    """
    cs.load(cdef, compiled=compiled)

    # We don't want the compiler to blow up with a custom type
    assert not cs.test.__compiled__

    result = cs.test(b"\x04asdf\x04asdf")
    assert isinstance(result.a, CustomType)
    assert isinstance(result.b, CustomType)
    assert result.a.value == b"ASDF"
    assert result.b.value == b"asdf"


def test_truthy_type(cs: cstruct) -> None:
    static_type = cs.uint32
    dynamic_type = cs.uint32[None]

    assert static_type
    # Should not raise a TypeError: Dynamic size
    assert dynamic_type


def test_array_string_count(cs: cstruct) -> None:
    """Test that a string array count is an expression, like an array count in a definition."""
    cs.add_const("SIZE", 4)
    assert cs.uint8["SIZE * 2"] is cs.uint8[8]

    array_type = cs.uint8["size"]
    assert array_type.__dynamic__
    assert array_type.__num_entries__.expression == "size"


def test_array_type_cache(cs: cstruct) -> None:
    """Test that array types are cached, and created again when the element type changes."""
    assert cs.uint32[4] is cs.uint32[4]
    assert cs.uint32[4] is not cs.uint32[5]
    assert cs.uint32[None] is cs.uint32[None]
    assert cs.uint32[None].__null_terminated__

    # Array types with an expression are only created when parsing a definition, so they aren't cached
    expr = Expression("a")
    assert cs.uint8[expr] is not cs.uint8[expr]

    # A modified structure results in a new array type with the correct size
    cdef = """
    struct test {
        uint8   a;
    };
    """
    cs.load(cdef)
    array_type = cs.test[2]
    assert array_type.__size__ == 2
    cs.test.add_field("b", cs.uint8)
    assert cs.test[2] is not array_type
    assert cs.test[2].__size__ == 4

    # Also when only the alignment changes, which determines the offsets in aligned structures
    array_type = cs.test[2]
    cs.test.add_field("c", cs.uint32[0])
    assert cs.test.__size__ == 2
    assert cs.test[2] is not array_type
    assert cs.test[2].__alignment__ == 4


class WrappingStream(io.BytesIO):
    """A stream that returns a different bytes-like type from read()."""

    def __init__(self, data: bytes, wrap: type):
        super().__init__(data)
        self._wrap = wrap

    def read(self, size: int | None = -1) -> object:
        return self._wrap(super().read(size))


class BytesSubclass(bytes):
    pass


class BytearraySubclass(bytearray):
    pass


@pytest.mark.parametrize("wrap", [memoryview, bytearray, BytesSubclass])
def test_stream_bytes_like_reads(cs: cstruct, compiled: bool, wrap: type) -> None:
    """Test reading from streams that return a different bytes-like type than bytes."""
    cdef = """
    struct test {
        uint16  a;
        wchar   b[2];
        uint24  c;
        char    d[];
        wchar   e[];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    data = b"\x01\x00" + "ab".encode("utf-16-le") + b"\x02\x00\x00" + b"cd\x00" + "ef".encode("utf-16-le") + b"\x00\x00"
    obj = cs.test(WrappingStream(data, wrap))
    assert (obj.a, obj.b, obj.c, obj.d, obj.e) == (1, "ab", 2, b"cd", "ef")

    assert cs.char[None](WrappingStream(b"abc\x00", wrap)) == b"abc"
    assert cs.wchar[None](WrappingStream("abc\x00".encode("utf-16-le"), wrap)) == "abc"


@pytest.mark.parametrize(
    "factory",
    [
        BytesSubclass,
        BytearraySubclass,
        lambda data: memoryview(data).cast("I"),
        lambda data: memoryview(data).cast("H"),
    ],
    ids=["bytes-subclass", "bytearray-subclass", "memoryview-I", "memoryview-H"],
)
def test_bytes_like_subclasses(cs: cstruct, factory: type) -> None:
    """Test reading from bytes and bytearray subclasses, and memoryviews with a different format."""
    cdef = """
    struct test {
        uint16  a;
        uint16  b;
        uint32  c;
    };
    """
    cs.load(cdef)
    data = bytes(range(1, 9))

    for method in (lambda t, v: t(v), lambda t, v: t.reads(v), lambda t, v: t.read(v)):
        assert method(cs.uint32, factory(data)) == 0x04030201
        assert method(cs.uint24, factory(data)) == 0x030201
        assert method(cs.uint16[2], factory(data)) == [0x0201, 0x0403]
        assert method(cs.char[4], factory(data)) == b"\x01\x02\x03\x04"
        assert method(cs.wchar[2], factory(data)) == "\u0201\u0403"
        assert method(cs.test, factory(data)).c == 0x08070605


def test_reads_non_buffer(cs: cstruct) -> None:
    """Test that reading from something that isn't bytes-like raises the same error as the generic implementation."""
    with pytest.raises(TypeError, match="a bytes-like object is required"):
        cs.uint32.reads(io.BytesIO(b"\x00" * 4))


def test_write_stream_errors(cs: cstruct) -> None:
    """Test that writing to something that isn't a stream is a ``TypeError``, and errors of the stream pass through."""
    with pytest.raises(TypeError, match=r"^Invalid object type$"):
        cs.uint32.write(b"", 1)

    # A read-only stream raises io.UnsupportedOperation, which is a ValueError too
    with pytest.raises(io.UnsupportedOperation):
        cs.uint32.write(io.BufferedReader(io.BytesIO()), 1)


def test_array_struct_write(cs: cstruct, compiled: bool) -> None:
    """Test that arrays in a structure are written from any sequence, and pad values that are too short."""
    cdef = """
    struct test {
        uint8   a;
        uint16  b[2];
        uint16  c[2];
        uint8   d[0];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x01\x00\x02\x00\x03\x00\x04\x00"
    assert bytes(cs.test(a=1, b=[1, 2], c=[3, 4])) == buf
    assert bytes(cs.test(a=1, b=(1, 2), c=[3, 4])) == buf

    # Shorter values are padded
    assert bytes(cs.test(a=1, b=[1], c=[3, 4])) == b"\x01\x01\x00\x00\x00\x03\x00\x04\x00"

    # The total amount of values is right, but the second array is too long
    with pytest.raises(WriteError, match="Expected static array size 2, got 3 instead"):
        bytes(cs.test(a=1, b=[1], c=[2, 3, 4]))

    with pytest.raises(WriteError, match=r"^Cannot write test: "):
        bytes(cs.test(a=1, b=[1, 2**16], c=[3, 4]))

    with pytest.raises(WriteError, match="Expected static array size 0, got 1 instead"):
        bytes(cs.test(a=1, b=[1, 2], c=[3, 4], d=[1]))


def test_array_multidimensional_write_padding(cs: cstruct, compiled: bool) -> None:
    """Test that the entries of multi-dimensional arrays and arrays of structures are padded too."""
    cdef = """
    struct nested {
        uint8 a;
    };

    struct test {
        uint8   a[2][2];
        char    b[2][2];
        nested  c[2];
        uint8   d;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(a=[[1], [2, 3]], b=[b"a", b"bc"], c=[cs.nested(a=5)], d=7)
    assert bytes(obj) == b"\x01\x00\x02\x03a\x00bc\x05\x00\x07"


@pytest.mark.skipif(sys.version_info < (3, 12), reason="The buffer protocol of Python classes needs Python 3.12")
def test_buffer(cs: cstruct) -> None:
    """Test that instances support the buffer protocol, with the same bytes as ``bytes(obj)``."""
    cdef = """
    enum Test : uint16 {
        A = 1
    };

    struct test {
        uint8   a;
        char    b[];
    };
    """
    cs.load(cdef)

    assert memoryview(cs.uint16(0x0102)).tobytes() == b"\x02\x01"
    assert memoryview(cs.uint16[2]([1, 2])).tobytes() == b"\x01\x00\x02\x00"
    assert memoryview(cs.Test.A).tobytes() == b"\x01\x00"
    assert memoryview(cs.char[None](b"ab\x00")).tobytes() == b"ab"
    assert memoryview(cs.char[4]([97, 98])).tobytes() == b"ab\x00\x00"
    assert memoryview(cs.wchar[None]("ab")).tobytes() == b"a\x00b\x00"
    assert memoryview(cs.uint16[None]([1, 2])).tobytes() == b"\x01\x00\x02\x00"

    fh = io.BytesIO()
    assert fh.write(cs.test(a=1, b=b"ab")) == 4
    assert fh.getvalue() == b"\x01ab\x00"
