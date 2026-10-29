from __future__ import annotations

import io
from typing import TYPE_CHECKING, BinaryIO

import pytest

from dissect.cstruct.exception import ArraySizeError
from dissect.cstruct.expression import Expression
from dissect.cstruct.types.base import BaseArray, BaseType

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import Endianness, cstruct


def test_array_size_mismatch(cs: cstruct) -> None:
    with pytest.raises(ArraySizeError):
        cs.uint8[2]([1, 2, 3]).dumps()

    assert cs.uint8[2]([1, 2]).dumps()


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
    assert test_char.dumps() == b"abc"

    test_wchar = cs.test_wchar("abc".encode("utf-16-le"))
    assert test_wchar.data == "abc"
    assert test_wchar.dumps() == "abc".encode("utf-16-le")

    test_packed = cs.test_packed(b"\x01\x00\x02\x00")
    assert test_packed.data == [1, 2]
    assert test_packed.dumps() == b"\x01\x00\x02\x00"

    test_int = cs.test_int(b"\x01\x00\x00\x02\x00\x00")
    assert test_int.data == [1, 2]
    assert test_int.dumps() == b"\x01\x00\x00\x02\x00\x00"

    test_enum = cs.test_enum(b"\x01\x00")
    assert test_enum.data == [cs.Test.A]
    assert test_enum.dumps() == b"\x01\x00"

    test_eof_field = cs.test_eof_field(b"\x01a\x02")
    assert test_eof_field.data == b"a"
    assert test_eof_field.remainder == 2
    assert test_eof_field.dumps() == b"\x01a\x02"


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
        assert method(cs.test, factory(data)).c == 0x08070605


def test_reads_non_buffer(cs: cstruct) -> None:
    """Test that reading from something that isn't bytes-like raises the same error as the generic implementation."""
    with pytest.raises(TypeError, match="a bytes-like object is required"):
        cs.uint32.reads(io.BytesIO(b"\x00" * 4))
