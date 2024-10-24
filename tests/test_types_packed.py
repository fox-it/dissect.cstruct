from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_packed_read(cs: cstruct) -> None:
    assert cs.uint32(b"AAAA") == 0x41414141
    assert cs.uint32(b"\xff\xff\xff\xff") == 0xFFFFFFFF

    assert cs.int32(b"\xff\x00\x00\x00") == 255
    assert cs.int32(b"\xff\xff\xff\xff") == -1

    assert cs.float16(b"\x00\x3c") == 1.0

    assert cs.float(b"\x00\x00\x80\x3f") == 1.0

    assert cs.double(b"\x00\x00\x00\x00\x00\x00\xf0\x3f") == 1.0


def test_packed_write(cs: cstruct) -> None:
    assert cs.uint32(0x41414141).dumps() == b"AAAA"
    assert cs.uint32(0xFFFFFFFF).dumps() == b"\xff\xff\xff\xff"
    assert cs.uint32(b"AAAA").dumps() == b"AAAA"

    assert cs.int32(255).dumps() == b"\xff\x00\x00\x00"
    assert cs.int32(-1).dumps() == b"\xff\xff\xff\xff"

    assert cs.float16(1.0).dumps() == b"\x00\x3c"

    assert cs.float(1.0).dumps() == b"\x00\x00\x80\x3f"

    assert cs.double(1.0).dumps() == b"\x00\x00\x00\x00\x00\x00\xf0\x3f"


def test_packed_array_read(cs: cstruct) -> None:
    assert cs.uint32[2](b"AAAABBBB") == [0x41414141, 0x42424242]
    assert cs.uint32[None](b"AAAABBBB\x00\x00\x00\x00") == [0x41414141, 0x42424242]

    assert cs.int32[2](b"\x00\x00\x00\x00\xff\xff\xff\xff") == [0, -1]
    assert cs.int32[None](b"\xff\xff\xff\xff\x00\x00\x00\x00") == [-1]

    assert cs.float[2](b"\x00\x00\x80\x3f\x00\x00\x00\x40") == [1.0, 2.0]
    assert cs.float[None](b"\x00\x00\x80\x3f\x00\x00\x00\x00") == [1.0]


def test_packed_array_write(cs: cstruct) -> None:
    assert cs.uint32[2]([0x41414141, 0x42424242]).dumps() == b"AAAABBBB"
    assert cs.uint32[None]([0x41414141, 0x42424242]).dumps() == b"AAAABBBB\x00\x00\x00\x00"

    assert cs.int32[2]([0, -1]).dumps() == b"\x00\x00\x00\x00\xff\xff\xff\xff"
    assert cs.int32[None]([-1]).dumps() == b"\xff\xff\xff\xff\x00\x00\x00\x00"

    assert cs.float[2]([1.0, 2.0]).dumps() == b"\x00\x00\x80\x3f\x00\x00\x00\x40"
    assert cs.float[None]([1.0]).dumps() == b"\x00\x00\x80\x3f\x00\x00\x00\x00"


def test_packed_be_read(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.uint32(b"AAA\x00") == 0x41414100
    assert cs.uint32(b"\xff\xff\xff\x00") == 0xFFFFFF00

    assert cs.int32(b"\x00\x00\x00\xff") == 255
    assert cs.int32(b"\xff\xff\xff\xff") == -1

    assert cs.float16(b"\x3c\x00") == 1.0

    assert cs.float(b"\x3f\x80\x00\x00") == 1.0

    assert cs.double(b"\x3f\xf0\x00\x00\x00\x00\x00\x00") == 1.0


def test_packed_be_write(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.uint32(0x41414100).dumps() == b"AAA\x00"
    assert cs.uint32(0xFFFFFF00).dumps() == b"\xff\xff\xff\x00"

    assert cs.int32(255).dumps() == b"\x00\x00\x00\xff"
    assert cs.int32(-1).dumps() == b"\xff\xff\xff\xff"

    assert cs.float16(1.0).dumps() == b"\x3c\x00"

    assert cs.float(1.0).dumps() == b"\x3f\x80\x00\x00"

    assert cs.double(1.0).dumps() == b"\x3f\xf0\x00\x00\x00\x00\x00\x00"


def test_packed_be_array_read(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.uint32[2](b"\x00\x00\x00\x01\x00\x00\x00\x02") == [1, 2]
    assert cs.uint32[None](b"\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x00") == [1, 2]

    assert cs.int32[2](b"\x00\x00\x00\x01\xff\xff\xff\xfe") == [1, -2]
    assert cs.int32[None](b"\xff\xff\xff\xfe\x00\x00\x00\x00") == [-2]

    assert cs.float[2](b"\x3f\x80\x00\x00\x40\x00\x00\x00") == [1.0, 2.0]
    assert cs.float[None](b"\x3f\x80\x00\x00\x00\x00\x00\x00") == [1.0]


def test_packed_be_array_write(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.uint32[2]([1, 2]).dumps() == b"\x00\x00\x00\x01\x00\x00\x00\x02"
    assert cs.uint32[None]([1, 2]).dumps() == b"\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x00"

    assert cs.int32[2]([1, -2]).dumps() == b"\x00\x00\x00\x01\xff\xff\xff\xfe"
    assert cs.int32[None]([-2]).dumps() == b"\xff\xff\xff\xfe\x00\x00\x00\x00"

    assert cs.float[2]([1.0, 2.0]).dumps() == b"\x3f\x80\x00\x00\x40\x00\x00\x00"
    assert cs.float[None]([1.0]).dumps() == b"\x3f\x80\x00\x00\x00\x00\x00\x00"


def test_packed_eof(cs: cstruct) -> None:
    with pytest.raises(EOFError):
        cs.uint32(b"\x00")

    with pytest.raises(EOFError):
        cs.uint32[2](b"\x00\x00\x00\x00")

    with pytest.raises(EOFError):
        cs.uint32[None](b"\x00\x00\x00\x01")


def test_packed_range(cs: cstruct) -> None:
    cs.float16(-65519.999999999996).dumps()
    cs.float16(65519.999999999996).dumps()
    with pytest.raises(OverflowError):
        cs.float16(-65519.999999999997).dumps()
    with pytest.raises(OverflowError):
        cs.float16(65519.999999999997).dumps()


def test_packed_float_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        float16 a;
        float   b;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"69\xb1U$G"
    obj = cs.test(buf)

    assert obj.a == 0.6513671875
    assert obj.b == 42069.69140625


def test_packed_float_struct_be(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        float16 a;
        float   b;
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.endian = ">"

    assert verify_compiled(cs.test, compiled)

    buf = b"69G$U\xb1"
    obj = cs.test(buf)

    assert obj.a == 0.388916015625
    assert obj.b == 42069.69140625


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
