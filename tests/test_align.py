from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING

from tests.util import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


def test_align_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint32  a;  // 0x00
        uint64  b;  // 0x08
        uint16  c;  // 0x10
        uint32  d;  // 0x14
        uint8   e;  // 0x18
        uint16  f;  // 0x1a
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    fields = cs.test.__fields__
    assert cs.test.__align__
    assert cs.test.__alignment__ == 8
    assert len(cs.test) == 32
    assert fields[0].offset == 0x00
    assert fields[1].offset == 0x08
    assert fields[2].offset == 0x10
    assert fields[3].offset == 0x14
    assert fields[4].offset == 0x18
    assert fields[5].offset == 0x1A

    buf = """
        00 00 00 00 00 00 00 00  08 00 00 00 00 00 00 00
        10 00 00 00 14 00 00 00  18 00 1a 00 00 00 00 00
    """
    buf = bytes.fromhex(buf)
    fh = BytesIO(buf)

    obj = cs.test(fh)
    assert fh.tell() == 32

    for name, value in obj.__values__.items():
        assert cs.test.__members__[name].offset == value

    assert obj.dumps() == buf


def test_align_union(cs: cstruct) -> None:
    cdef = """
    union test {
        uint32  a;
        uint64  b;
    };
    """
    cs.load(cdef, align=True)

    assert cs.test.__align__
    assert cs.test.__alignment__ == 8
    assert len(cs.test) == 8

    buf = """
        00 00 00 01 00 00 00 02
    """
    buf = bytes.fromhex(buf)
    fh = BytesIO(buf)

    obj = cs.test(fh)
    assert fh.tell() == 8
    assert obj.a == 0x01000000
    assert obj.b == 0x0200000001000000

    assert obj.dumps() == buf


def test_align_union_tail(cs: cstruct) -> None:
    cdef = """
    union test {
        uint64 a;
        uint32 b[3];
    };
    """
    cs.load(cdef, align=True)

    assert cs.test.__align__
    assert cs.test.__alignment__ == 8
    assert len(cs.test) == 16


def test_align_array(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint32  a;      // 0x00
        uint64  b[4];   // 0x08
        uint16  c;      // 0x28
        uint32  d[2];   // 0x2c
        uint64  e;      // 0x38
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    fields = cs.test.__fields__
    assert cs.test.__align__
    assert cs.test.__alignment__ == 8
    assert len(cs.test) == 64
    assert fields[0].offset == 0x00
    assert fields[1].offset == 0x08
    assert fields[2].offset == 0x28
    assert fields[3].offset == 0x2C
    assert fields[4].offset == 0x38

    buf = """
        00 00 00 00 00 00 00 00  08 00 00 00 00 00 00 00
        10 00 00 00 00 00 00 00  18 00 00 00 00 00 00 00
        20 00 00 00 00 00 00 00  28 00 00 00 2c 00 00 00
        30 00 00 00 00 00 00 00  38 00 00 00 00 00 00 00
    """
    buf = bytes.fromhex(buf)

    obj = cs.test(buf)

    assert obj.a == 0x00
    assert obj.b == [0x08, 0x10, 0x18, 0x20]
    assert obj.c == 0x28
    assert obj.d == [0x2C, 0x30]
    assert obj.e == 0x38

    assert obj.dumps() == buf


def test_align_struct_array(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint32  a;      // 0x00
        uint64  b;      // 0x08
    };

    struct array {
        test    a[4];
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)
    assert verify_compiled(cs.array, compiled)

    fields = cs.test.__fields__
    assert cs.test.__align__
    assert cs.test.__alignment__ == 8
    assert len(cs.test) == 16
    assert fields[0].offset == 0x00
    assert fields[1].offset == 0x08

    buf = """
        00 00 00 00 00 00 00 00  08 00 00 00 00 00 00 00
        10 00 00 00 00 00 00 00  18 00 00 00 00 00 00 00
        20 00 00 00 00 00 00 00  28 00 00 00 00 00 00 00
        30 00 00 00 00 00 00 00  38 00 00 00 00 00 00 00
    """
    buf = bytes.fromhex(buf)

    obj = cs.array(buf)

    assert obj.a[0].a == 0x00
    assert obj.a[0].b == 0x08
    assert obj.a[1].a == 0x10
    assert obj.a[1].b == 0x18
    assert obj.a[2].a == 0x20
    assert obj.a[2].b == 0x28
    assert obj.a[3].a == 0x30
    assert obj.a[3].b == 0x38

    assert obj.dumps() == buf


def test_align_dynamic(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint8   a;      // 0x00 (value is 6 in test case)
        uint16  b[a];   // 0x02
        uint32  c;      // 0x?? (0x10 in test case)
        uint64  d;      // 0x?? (0x18 in test case)
        uint8   e;      // 0x?? (0x20, value is 2 in test case)
        uint32  f[e];   // 0x?? (0x24 in test case)
        uint64  g;      // 0x?? (0x30 in test case)
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    fields = cs.test.__fields__
    assert fields[0].offset == 0
    assert fields[1].offset == 2
    assert fields[2].offset is None
    assert fields[3].offset is None
    assert fields[4].offset is None
    assert fields[5].offset is None
    assert fields[6].offset is None

    buf = """
        06 00 02 00 04 00 06 00  08 00 0a 00 0c 00 00 00
        10 00 00 00 00 00 00 00  18 00 00 00 00 00 00 00
        02 00 00 00 24 00 00 00  28 00 00 00 00 00 00 00
        30 00 00 00 00 00 00 00
    """
    buf = bytes.fromhex(buf)
    obj = cs.test(buf)

    assert obj.a == 0x06
    assert obj.b == [0x02, 0x04, 0x06, 0x08, 0x0A, 0x0C]
    assert obj.c == 0x10
    assert obj.d == 0x18
    assert obj.e == 0x02
    assert obj.f == [0x24, 0x28]
    assert obj.g == 0x30

    assert obj.dumps() == buf


def test_align_nested_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint32  a;      // 0x00
        struct {
            uint64  b;  // 0x08
            uint32  c;  // 0x10
        } nested;
        uint64  d;      // 0x18
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    fields = cs.test.__fields__
    assert fields[0].offset == 0x00
    assert fields[1].offset == 0x08
    assert fields[2].offset == 0x18

    buf = """
        00 00 00 00 00 00 00 00  08 00 00 00 00 00 00 00
        10 00 00 00 00 00 00 00  18 00 00 00 00 00 00 00
    """
    buf = bytes.fromhex(buf)
    obj = cs.test(buf)

    assert obj.a == 0x00
    assert obj.nested.b == 0x08
    assert obj.nested.c == 0x10
    assert obj.d == 0x18

    assert obj.dumps() == buf


def test_align_bitfield(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint16  a:4;    // 0x00
        uint16  b:4;
        uint64  c:4;    // 0x08
        uint64  d:4;
        uint16  e;      // 0x10
        uint32  f:4;    // 0x14
        uint64  g;      // 0x18
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    fields = cs.test.__fields__
    assert fields[0].offset == 0x00
    assert fields[1].offset is None
    assert fields[2].offset == 0x08
    assert fields[3].offset is None
    assert fields[4].offset == 0x10
    assert fields[5].offset == 0x14
    assert fields[6].offset == 0x18

    buf = """
        12 00 00 00 00 00 00 00  12 00 00 00 00 00 00 00
        10 00 00 00 02 00 00 00  18 00 00 00 00 00 00 00
    """
    buf = bytes.fromhex(buf)
    obj = cs.test(buf)

    assert obj.a == 0b10
    assert obj.b == 0b01
    assert obj.c == 0b10
    assert obj.d == 0b01
    assert obj.e == 0x10
    assert obj.f == 0b10
    assert obj.g == 0x18

    assert obj.dumps() == buf


def test_align_pointer(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint32  a;
        uint32  *b;
        uint16  c;
        uint16  d;
    };
    """
    cs.pointer = cs.uint64
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    fields = cs.test.__fields__
    assert cs.test.__align__
    assert cs.test.__alignment__ == 8
    assert len(cs.test) == 24
    assert fields[0].offset == 0x00
    assert fields[1].offset == 0x08
    assert fields[2].offset == 0x10
    assert fields[3].offset == 0x12

    buf = """
        00 00 00 00 00 00 00 00  18 00 00 00 00 00 00 00
        10 00 12 00 00 00 00 00  18 00 00 00
    """
    buf = bytes.fromhex(buf)
    obj = cs.test(buf)

    assert obj.a == 0x00
    assert obj.b.dereference() == 0x18
    assert obj.c == 0x10
    assert obj.d == 0x12

    assert obj.dumps() == buf[:-4]  # Without pointer value


def test_align_field_after_nested_struct(cs: cstruct, compiled: bool) -> None:
    """Test that the fields after a nested structure are read at their aligned offsets."""
    cdef = """
    struct inner {
        uint16  a;
        uint16  b;
    };

    struct test {
        uint8   a;  // 0x00
        inner   i;  // 0x02
        uint32  c;  // 0x08
        uint8   d;  // 0x0c
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    fields = cs.test.__fields__
    assert len(cs.test) == 16
    assert fields[0].offset == 0x00
    assert fields[1].offset == 0x02
    assert fields[2].offset == 0x08
    assert fields[3].offset == 0x0C

    buf = """
        00 00 02 00 04 00 00 00  08 00 00 00 0c 00 00 00
    """
    buf = bytes.fromhex(buf)
    obj = cs.test(buf)

    assert obj.a == 0x00
    assert obj.i.a == 0x02
    assert obj.i.b == 0x04
    assert obj.c == 0x08
    assert obj.d == 0x0C

    assert obj.dumps() == buf


def test_align_after_dynamic_field(cs: cstruct, compiled: bool) -> None:
    """Test that fields after a dynamic field are aligned to the position in the stream."""
    cdef = """
    struct test {
        uint8  n;
        uint8  a[n];
        uint8  b;
        uint32 c;
        uint8  d;
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    # Fields after a dynamic field are aligned to the position in the stream, not relative to their preceding field
    buf = b"\x01\xaa\xbb\x00\x01\x02\x03\x04\xcc\x00\x00\x00"
    obj = cs.test(buf)
    assert obj.b == 0xBB
    assert obj.c == 0x04030201
    assert obj.d == 0xCC
    assert obj.dumps() == buf


def test_align_stream_position(cs: cstruct, compiled: bool) -> None:
    """Test that padding after a dynamic field or at the end of a structure follows the position in the stream."""
    cdef = """
    struct test_static {
        uint8   a;
        uint32  b;
        uint8   c;
    };

    struct test_dynamic {
        uint8   n;
        uint8   a[n];
        uint32  b;
        uint8   c;
    };

    struct nested {
        uint8   a;
        uint32  b;
    };

    struct test_nested {
        uint8   c;
        nested  d;
        uint64  e;
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test_static, compiled)
    assert verify_compiled(cs.test_dynamic, compiled)
    assert verify_compiled(cs.test_nested, compiled)

    # The padding between static fields depends on the structure, the padding at the end on the stream
    fh = BytesIO(b"\xff")
    fh.seek(1)
    assert cs.test_static(a=1, b=2, c=3).write(fh) == 11
    assert fh.getvalue() == b"\xff\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00"

    # The padding after a dynamic field depends on the stream
    fh = BytesIO(b"\xff")
    fh.seek(1)
    assert cs.test_dynamic(n=1, a=[2], b=3, c=4).write(fh) == 11
    assert fh.getvalue() == b"\xff\x01\x02\x00\x03\x00\x00\x00\x04\x00\x00\x00"

    # The padding at the end of a nested structure depends on the stream too
    fh = BytesIO(b"\xff")
    fh.seek(1)
    assert cs.test_nested(c=1, d=cs.nested(a=2, b=3), e=4).write(fh) == 31
    assert fh.getvalue() == (b"\xff\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\x04" + bytes(14))
