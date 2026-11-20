from __future__ import annotations

from unittest.mock import patch

import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.exception import NullPointerDereference, WriteError
from dissect.cstruct.types.pointer import Pointer
from tests.util import verify_compiled


def test_pointer(cs: cstruct) -> None:
    cs.pointer = cs.uint8

    ptr = cs._make_pointer(cs.uint8)
    assert issubclass(ptr, Pointer)
    assert ptr.__name__ == "uint8*"

    obj = ptr(b"\x01\xff")
    assert repr(obj) == "<uint8* @ 0x1>"

    assert obj == 1
    assert bytes(obj) == b"\x01"
    assert obj.dereference() == 255
    assert str(obj) == "255"

    with pytest.raises(NullPointerDereference):
        ptr(0, None, endian=cs.endian).dereference()


@pytest.mark.parametrize(
    ("type_name", "buf", "expected", "expected_str"),
    [
        ("char", b"\x02\x00asdf\x00", b"asdf", "b'asdf'"),
        ("wchar", b"\x02\x00a\x00s\x00d\x00f\x00\x00\x00", "asdf", "asdf"),
    ],
)
def test_pointer_char(cs: cstruct, type_name: str, buf: bytes, expected: bytes | str, expected_str: str) -> None:
    """Test that a ``char`` and ``wchar`` pointer dereference to a null-terminated string that can be written back."""
    cs.pointer = cs.uint8

    ptr = cs._make_pointer(cs.resolve(type_name))
    assert ptr.__name__ == f"{type_name}*"

    obj = ptr(buf)
    assert repr(obj) == f"<{type_name}* @ 0x2>"

    assert obj == 2
    assert obj.dereference() == expected
    assert str(obj) == expected_str

    value = obj.dereference()
    assert type(value).dumps(value) == buf[2:]


def test_pointer_operator(cs: cstruct) -> None:
    cs.pointer = cs.uint8

    ptr = cs._make_pointer(cs.uint8)
    obj = ptr(b"\x01\x00\xff")

    assert obj == 1
    assert bytes(obj) == b"\x01"
    assert obj.dereference() == 0

    obj += 1
    assert obj == 2
    assert bytes(obj) == b"\x02"
    assert obj.dereference() == 255

    obj -= 2
    assert obj == 0

    obj += 4
    assert obj == 4

    obj -= 2
    assert obj == 2

    obj *= 12
    assert obj == 24

    obj //= 2
    assert obj == 12

    obj %= 10
    assert obj == 2

    obj **= 4
    assert obj == 16

    obj <<= 1
    assert obj == 32

    obj >>= 2
    assert obj == 8

    obj &= 2
    assert obj == 0

    obj ^= 4
    assert obj == 4

    obj |= 8
    assert obj == 12


def test_pointer_eof(cs: cstruct) -> None:
    cs.pointer = cs.uint8

    ptr = cs._make_pointer(cs.uint8)
    obj = ptr(b"\x01")

    with pytest.raises(EOFError):
        obj.dereference()

    # An offset beyond any stream, e.g. from corrupt data
    cs.pointer = cs.uint64
    ptr = cs._make_pointer(cs.uint8)
    obj = ptr(b"\xff" * 8)

    with pytest.raises(EOFError, match=r"^Offset 0xffffffffffffffff is beyond the end of the stream$"):
        obj.dereference()


def test_pointer_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct ptrtest {
        uint32  *ptr1;
        uint32  *ptr2;
    };
    """
    cs.pointer = cs.uint16
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.ptrtest, compiled)
    assert cs.pointer is cs.uint16

    buf = b"\x04\x00\x08\x00\x01\x02\x03\x04\x05\x06\x07\x08"
    obj = cs.ptrtest(buf)

    assert repr(obj) == "<ptrtest ptr1=<uint32* @ 0x4> ptr2=<uint32* @ 0x8>>"

    assert obj.ptr1 != 0
    assert obj.ptr2 != 0
    assert obj.ptr1 != obj.ptr2
    assert obj.ptr1 == 4
    assert obj.ptr2 == 8
    assert obj.ptr1.dereference() == 0x04030201
    assert obj.ptr2.dereference() == 0x08070605

    obj.ptr1 += 2
    obj.ptr2 -= 2
    assert obj.ptr1 == obj.ptr2
    assert obj.ptr1.dereference() == obj.ptr2.dereference() == 0x06050403

    assert bytes(obj) == b"\x06\x00\x06\x00"

    with pytest.raises(NullPointerDereference):
        cs.ptrtest(b"\x00\x00\x00\x00").ptr1.dereference()


def test_pointer_struct_pointer(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        char    magic[4];
        wchar   wmagic[4];
        uint8   type;
        uint16  b;
        uint32  c;
        char    string[];
        wchar   wstring[];
    };

    struct ptrtest {
        test    *ptr;
    };
    """
    cs.pointer = cs.uint16
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert verify_compiled(cs.ptrtest, compiled)
    assert cs.pointer is cs.uint16

    buf = b"\x02\x00testt\x00e\x00s\x00t\x00\x01\x02\x03\x04\x05\x06\x07lalala\x00t\x00e\x00s\x00t\x00\x00\x00"
    obj = cs.ptrtest(buf)

    assert obj.ptr != 0

    assert obj.ptr.magic == b"test"
    assert obj.ptr.wmagic == "test"
    assert obj.ptr.type == 0x01
    assert obj.ptr.b == 0x0302
    assert obj.ptr.c == 0x07060504
    assert obj.ptr.string == b"lalala"
    assert obj.ptr.wstring == "test"

    assert bytes(obj) == b"\x02\x00"

    with pytest.raises(NullPointerDereference):
        cs.ptrtest(b"\x00\x00\x00\x00").ptr.magic  # noqa: B018


def test_pointer_array(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct mainargs {
        uint8_t argc;
        char *args[4];
    };
    """
    cs.pointer = cs.uint16
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.mainargs, compiled)
    assert cs.pointer is cs.uint16

    buf = b"\x02\x09\x00\x16\x00\x00\x00\x00\x00argument one\x00argument two\x00"
    obj = cs.mainargs(buf)

    assert obj.argc == 2
    assert obj.args[2] == 0
    assert obj.args[3] == 0
    assert obj.args[0].dereference() == b"argument one"
    assert obj.args[1].dereference() == b"argument two"


def test_pointer_sys_size() -> None:
    with patch("sys.maxsize", 2**64):
        cs = cstruct()
        assert cs.pointer is cs.uint64

    with patch("sys.maxsize", 2**32):
        cs = cstruct()
        assert cs.pointer is cs.uint32

    cs = cstruct(pointer="uint16")
    assert cs.pointer is cs.uint16


def test_pointer_of_pointer(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint32  **ptr;
    };
    """
    cs.pointer = cs.uint8
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(b"\x01\x02AAAA")
    assert isinstance(obj.ptr, Pointer)
    assert isinstance(obj.ptr.dereference(), Pointer)
    assert obj.ptr == 1
    assert obj.ptr.dereference() == 2
    assert obj.ptr.dereference().dereference() == 0x41414141


def test_pointer_default(cs: cstruct) -> None:
    cs.pointer = cs.uint8

    ptr = cs._make_pointer(cs.uint8)
    assert isinstance(ptr.__default__(), Pointer)
    assert ptr.__default__() == 0
    assert ptr[1].__default__() == [0]
    assert ptr[None].__default__() == []

    with pytest.raises(NullPointerDereference):
        ptr.__default__().dereference()


def test_pointer_changing_endian(cs: cstruct) -> None:
    cs.pointer = cs.uint16

    ptr = cs._make_pointer(cs.uint32)
    assert issubclass(ptr, Pointer)
    assert ptr.__name__ == "uint32*"

    assert cs.endian == "<"

    obj = ptr(b"\x00\x02\x01\x02\x03\x04", endian=">")
    assert repr(obj) == "<uint32* @ 0x2>"

    assert obj == 2
    assert ptr.dumps(obj, endian=">") == b"\x00\x02"
    assert obj.dereference() == 0x01020304
    assert obj.dereference(endian="<") == 0x04030201


def test_pointer_int_type_array(cs: cstruct, compiled: bool) -> None:
    """Test that compiled structures read arrays of pointers of ``Int`` types by the size of their entries."""
    cdef = """
    struct test {
        uint8   *a[2];
        uint8   b;
    };
    """
    cs.pointer = cs.uint24
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x00\x00\x02\x00\x00\x03"
    obj = cs.test(buf)
    assert obj.a == [1, 2]
    assert obj.b == 3
    assert bytes(obj) == buf


def test_pointer_struct_write(cs: cstruct, compiled: bool) -> None:
    """Test that pointers are written by their value, and raise an error if it doesn't fit."""
    cdef = """
    struct test {
        uint8   a;
        uint32  *b;
        uint8   *c[2];
    };
    """
    cs.pointer = cs.uint16
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert bytes(cs.test(a=1, b=2, c=[3, 4])) == b"\x01\x02\x00\x03\x00\x04\x00"

    with pytest.raises(WriteError, match=r"^Cannot write test: "):
        bytes(cs.test(a=1, b=2, c=[3, 2**16]))
