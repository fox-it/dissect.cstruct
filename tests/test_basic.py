from __future__ import annotations

import textwrap
from io import BytesIO
from typing import TYPE_CHECKING, BinaryIO

import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.exceptions import ArraySizeError, ParserError, ResolveError
from dissect.cstruct.types import BaseType

from .utils import verify_compiled

if TYPE_CHECKING:
    from pathlib import Path


def test_duplicate_type(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint32  a;
    };
    """
    cs.load(cdef, compiled=compiled)

    with pytest.raises(ValueError, match="Duplicate type"):
        cs.load(cdef)


def test_load_file(cs: cstruct, compiled: bool, tmp_path: Path) -> None:
    cdef = """
    struct test {
        uint32  a;
    };
    """
    tmp_path.joinpath("testdef.txt").write_text(textwrap.dedent(cdef))

    cs.loadfile(tmp_path.joinpath("testdef.txt"), compiled=compiled)
    assert "test" in cs.typedefs


def test_load_init() -> None:
    cdef = """
    struct test {
        DWORD   a;
        QWORD   b;
    };
    """
    # load with first positional argument
    cs = cstruct(cdef)
    assert "test" in cs.typedefs
    assert cs.endian == "<"

    # load from keyword argument and big endian
    cs = cstruct(load=cdef, endian=">")
    assert "test" in cs.typedefs
    a = cs.test(a=0xBADC0DE, b=0xACCE55ED)
    assert len(bytes(a)) == 12
    assert bytes(a) == a.dumps()
    assert bytes(a) == b"\x0b\xad\xc0\xde\x00\x00\x00\x00\xac\xce\x55\xed"

    # load using positional argument and little endian
    cs = cstruct(cdef, endian="<")
    assert "test" in cs.typedefs
    a = cs.test(a=0xBADC0DE, b=0xACCE55ED)
    assert len(bytes(a)) == 12
    assert bytes(a) == a.dumps()
    assert bytes(a) == b"\xde\xc0\xad\x0b\xed\x55\xce\xac\x00\x00\x00\x00"


def test_load_init_kwargs_only() -> None:
    cdef = """
    struct test {
        uint32  a;
    };
    """

    # kwargs only check
    with pytest.raises(TypeError, match="takes from .* positional arguments but .* were given"):
        cs = cstruct(cdef, ">")

    cs = cstruct(cdef, endian=">")
    assert "test" in cs.typedefs
    assert cs.endian == ">"


def test_read_type_name(cs: cstruct) -> None:
    assert cs.read("uint32", b"\x01\x00\x00\x00") == 1


def test_type_resolve(cs: cstruct) -> None:
    assert cs.resolve("BYTE") == cs.uint8

    with pytest.raises(ResolveError, match="Unknown type"):
        cs.resolve("fake")

    cs.add_type("ref0", "uint32")
    for i in range(1, 15):  # Recursion limit is currently 10
        cs.add_type(f"ref{i}", f"ref{i - 1}")

    with pytest.raises(ResolveError, match="Recursion limit exceeded"):
        cs.resolve("ref14")


def test_constants(cs: cstruct) -> None:
    cdef = """
    #define a 1
    #define b 0x2
    #define c "test"
    #define d 1 << 1
    """
    cs.load(cdef)

    assert cs.a == 1
    assert cs.b == 2
    assert cs.c == "test"
    assert cs.d == 2


def test_duplicate_types(cs: cstruct) -> None:
    cdef = """
    struct A {
        uint32 a;
    };
    """
    cs.load(cdef)
    assert cs.A

    with pytest.raises(ValueError, match="Duplicate type"):
        cs.load(cdef)

    cs.load("""typedef uint32 Test;""")
    assert cs.Test is cs.uint32

    cs.load("""typedef uint32 Test;""")
    assert cs.Test is cs.uint32

    with pytest.raises(ValueError, match="Duplicate type"):
        cs.load("""typedef uint64 Test;""")


def test_typedef(cs: cstruct) -> None:
    cdef = """
    typedef uint32 test;
    """
    cs.load(cdef)

    assert cs.test == cs.uint32
    assert cs.resolve("test") == cs.uint32


def test_lookups(cs: cstruct, compiled: bool) -> None:
    cdef = """
    #define test_1 1
    #define test_2 2
    $a = {'test_1': 3, 'test_2': 4}
    """
    cs.load(cdef, compiled=compiled)
    assert cs.lookups["a"] == {1: 3, 2: 4}


def test_config_flag_nocompile(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct compiled_global
    {
        uint32  a;
    };

    #[nocompile]
    struct never_compiled
    {
        uint32  a;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.compiled_global, compiled)
    assert verify_compiled(cs.never_compiled, False)


def test_compiler_slicing_multiple(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct compile_slicing {
        char single;
        char multiple[2];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.compile_slicing, compiled)

    obj = cs.compile_slicing(b"\x01\x02\x03")
    assert obj.single == b"\x01"
    assert obj.multiple == b"\x02\x03"


def test_underscores_attribute(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct __test {
        uint32 test_val;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.__test, compiled)

    data = b"\x39\x05\x00\x00"
    obj = cs.__test(data)
    assert obj.test_val == 1337


def test_half_compiled_struct(cs: cstruct) -> None:
    class OffByOne(int, BaseType):
        type: BaseType

        @classmethod
        def _read(cls, stream: BinaryIO, context: dict | None = None) -> OffByOne:
            return cls(cls.type._read(stream, context) + 1)

        @classmethod
        def _write(cls, stream: BinaryIO, data: int) -> OffByOne:
            return cls(cls.type._write(stream, data - 1))

    # Add an unsupported type for the cstruct compiler
    # so that it returns the original struct,
    # only partially compiling the struct.
    offbyone = cs._make_type("offbyone", (OffByOne,), 8, attrs={"type": cs.uint64})
    cs.add_type("offbyone", offbyone)

    cdef = """
    struct uncompiled {
        uint32      a;
        offbyone    b;
        uint16      c;
    };

    struct compiled {
        char        a[4];
        uncompiled  b;
        uint16      c;
    };
    """
    cs.load(cdef, compiled=True)

    assert verify_compiled(cs.compiled, True)
    assert verify_compiled(cs.uncompiled, False)

    buf = b"zomg\x01\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x03\x00\x04\x00"
    obj = cs.compiled(buf)
    assert obj.a == b"zomg"
    assert obj.b.a == 1
    assert obj.b.b == 3
    assert obj.b.c == 3
    assert obj.c == 4

    assert obj.dumps() == buf


def test_cstruct_bytearray(cs: cstruct) -> None:
    cdef = """
    struct test {
        uint8 a;
    };
    """
    cs.load(cdef)

    obj = cs.test(bytearray([10]))
    assert obj.a == 10


def test_multipart_type_name(cs: cstruct) -> None:
    cdef = """
    enum TestEnum : unsigned int {
        A = 0,
        B = 1
    };

    struct test {
        unsigned int    a;
        unsigned long long  b;
    };
    """
    cs.load(cdef)

    assert cs.TestEnum.type == cs.resolve("unsigned int")
    assert cs.test.__fields__[0].type == cs.resolve("unsigned int")
    assert cs.test.__fields__[1].type == cs.resolve("unsigned long long")

    cdef = """
    struct test1 {
        unsigned long long unsigned a;
    };
    """
    with pytest.raises(ResolveError, match="Unknown type unsigned long long unsigned"):
        cs.load(cdef)

    cdef = """
    enum TestEnum : unsigned int and more {
        A = 0,
        B = 1
    };
    """
    with pytest.raises(ResolveError, match="Unknown type unsigned int and more"):
        cs.load(cdef)


def test_dunder_bytes(cs: cstruct) -> None:
    cdef = """
    struct test {
        DWORD   a;
        QWORD   b;
    };
    """
    cs.endian = ">"
    cs.load(cdef)

    a = cs.test(a=0xBADC0DE, b=0xACCE55ED)
    assert len(bytes(a)) == 12
    assert bytes(a) == a.dumps()
    assert bytes(a) == b"\x0b\xad\xc0\xde\x00\x00\x00\x00\xac\xce\x55\xed"


def test_array_of_null_terminated_strings(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct args {
        uint32 argc;
        char   argv[argc][];
    }
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.args, compiled)

    buf = b"\x02\x00\x00\x00hello\0world\0"
    obj = cs.args(buf)

    assert obj.argc == 2
    assert obj.argv[0] == b"hello"
    assert obj.argv[1] == b"world"

    cdef = """
    struct args2 {
        uint32 argc;
        char   argv[][argc];
    }
    """
    with pytest.raises(ParserError, match="Depth required for multi-dimensional array"):
        cs.load(cdef)


def test_array_of_size_limited_strings(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct args {
        uint32 argc;
        char   argv[argc][8];
    }
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.args, compiled)

    buf = b"\x04\x00\x00\x00lorem\0\0\0ipsum\0\0\0dolor\0\0\0sit amet"
    obj = cs.args(buf)

    assert obj.argc == 4
    assert obj.argv[0] == b"lorem\0\0\0"
    assert obj.argv[1] == b"ipsum\0\0\0"
    assert obj.argv[2] == b"dolor\0\0\0"
    assert obj.argv[3] == b"sit amet"


def test_array_three_dimensional(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint8   a[2][2][2];
    }
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    obj = cs.test(buf)

    assert obj.a[0][0][0] == 1
    assert obj.a[0][0][1] == 2
    assert obj.a[0][1][0] == 3
    assert obj.a[0][1][1] == 4
    assert obj.a[1][0][0] == 5
    assert obj.a[1][0][1] == 6
    assert obj.a[1][1][0] == 7
    assert obj.a[1][1][1] == 8

    assert obj.dumps() == buf


def test_nested_array_of_variable_size(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint8   outer;
        uint8   medior;
        uint8   inner;
        uint8   a[outer][medior][inner];
    }
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x02\x01\x03\x01\x02\x03\x04\x05\x06"
    obj = cs.test(buf)

    assert obj.outer == 2
    assert obj.medior == 1
    assert obj.inner == 3
    assert obj.a[0][0][0] == 1
    assert obj.a[0][0][1] == 2
    assert obj.a[0][0][2] == 3
    assert obj.a[1][0][0] == 4
    assert obj.a[1][0][1] == 5
    assert obj.a[1][0][2] == 6

    assert obj.dumps() == buf


def test_report_array_size_mismatch(cs: cstruct) -> None:
    cdef = """
    struct test {
        uint8   a[2];
    };
    """
    cs.load(cdef)

    a = cs.test(a=[1, 2, 3])

    with pytest.raises(ArraySizeError):
        a.dumps()


def test_reserved_keyword(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct in {
        uint8 a;
    };

    struct class {
        uint8 a;
    };

    struct for {
        uint8 a;
    };
    """
    cs.load(cdef, compiled=compiled)

    for name in ["in", "class", "for"]:
        assert name in cs.typedefs
        assert verify_compiled(cs.resolve(name), compiled)

        assert cs.resolve(name)(b"\x01").a == 1


def test_array_class_name(cs: cstruct) -> None:
    cdef = """
    struct test {
        uint8   a[2];
    };

    struct test2 {
        uint8   a;
        uint8   b[a + 1];
    };
    """
    cs.load(cdef)

    assert cs.test.__fields__[0].type.__name__ == "uint8[2]"
    assert cs.test2.__fields__[1].type.__name__ == "uint8[a + 1]"


def test_size_and_aligment(cs: cstruct) -> None:
    test = cs._make_int_type("test", 1, False, alignment=8)
    assert test.size == 1
    assert test.alignment == 8

    test = cs._make_packed_type("test", "B", int, alignment=8)
    assert test.size == 1
    assert test.alignment == 8


def test_dynamic_substruct_size(cs: cstruct) -> None:
    cdef = """
    struct {
        int32 len;
        char str[len];
    } sub;

    struct {
        sub data[1];
    } test;
    """
    cs.load(cdef)

    assert cs.sub.dynamic
    assert cs.test.dynamic


def test_dumps_write_overload(cs: cstruct) -> None:
    assert cs.uint8.dumps(1) == cs.uint8(1).dumps() == b"\x01"

    fh = BytesIO()
    cs.uint8.write(fh, 1)
    assert fh.getvalue() == b"\x01"
    cs.uint8(2).write(fh)
    assert fh.getvalue() == b"\x01\x02"


def test_linked_list(cs: cstruct) -> None:
    cdef = """
    struct node {
        uint16 data;
        node* next;
    };
    """
    cs.pointer = cs.uint16
    cs.load(cdef)

    assert cs.node.__fields__[1].type.type == cs.node

    obj = cs.node(b"\x01\x00\x04\x00\x02\x00\x00\x00")
    assert repr(obj) == "<node data=0x1 next=<node* @ 0x4>>"

    assert obj.data == 1
    assert obj.next.data == 2
