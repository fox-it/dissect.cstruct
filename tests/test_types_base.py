from __future__ import annotations

from typing import TYPE_CHECKING, BinaryIO

import pytest

from dissect.cstruct.exceptions import ArraySizeError
from dissect.cstruct.types.base import BaseArray, BaseType

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_array_size_mismatch(cs: cstruct) -> None:
    with pytest.raises(ArraySizeError):
        cs.uint8[2]([1, 2, 3]).dumps()

    assert cs.uint8[2]([1, 2]).dumps()


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
        def _read(cls, stream: BinaryIO, context: dict | None = None) -> CustomType:
            length = stream.read(1)[0]
            value = stream.read(length)
            return type.__call__(cls, value)

        class ArrayType(BaseArray):
            @classmethod
            def __default__(cls) -> CustomType:
                return cls.type()

            @classmethod
            def _read(cls, stream: BinaryIO, context: dict | None = None) -> CustomType:
                value = cls.type._read(stream, context)
                if str(cls.num_entries) == "lower":
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
