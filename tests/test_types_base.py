import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.exceptions import ArraySizeError

from .utils import verify_compiled


def test_array_size_mismatch(cs: cstruct):
    with pytest.raises(ArraySizeError):
        cs.uint8[2]([1, 2, 3]).dumps()

    assert cs.uint8[2]([1, 2]).dumps()


def test_eof(cs: cstruct, compiled: bool):
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
