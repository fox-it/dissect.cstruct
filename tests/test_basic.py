import os
import pytest

from dissect import cstruct
from dissect.cstruct.exceptions import ResolveError

from .utils import verify_compiled


def test_simple_types():
    cs = cstruct.cstruct()
    assert cs.uint32(b"\x01\x00\x00\x00") == 1
    assert cs.uint32[10](b"A" * 20 + b"B" * 20) == [0x41414141] * 5 + [0x42424242] * 5
    assert cs.uint32[None](b"A" * 20 + b"\x00" * 4) == [0x41414141] * 5

    with pytest.raises(EOFError):
        cs.char[None](b"aaa")

    with pytest.raises(EOFError):
        cs.wchar[None](b"a\x00a\x00a")


def test_write():
    cs = cstruct.cstruct()

    assert cs.uint32.dumps(1) == b"\x01\x00\x00\x00"
    assert cs.uint16.dumps(255) == b"\xff\x00"
    assert cs.int8.dumps(-10) == b"\xf6"
    assert cs.uint8[4].dumps([1, 2, 3, 4]) == b"\x01\x02\x03\x04"
    assert cs.uint24.dumps(300) == b"\x2c\x01\x00"
    assert cs.int24.dumps(-1337) == b"\xc7\xfa\xff"
    assert cs.uint24[4].dumps([1, 2, 3, 4]) == b"\x01\x00\x00\x02\x00\x00\x03\x00\x00\x04\x00\x00"
    assert cs.uint24[None].dumps([1, 2]) == b"\x01\x00\x00\x02\x00\x00\x00\x00\x00"
    assert cs.char.dumps(0x61) == b"a"
    assert cs.wchar.dumps("lala") == b"l\x00a\x00l\x00a\x00"
    assert cs.uint32[None].dumps([1]) == b"\x01\x00\x00\x00\x00\x00\x00\x00"


def test_write_be():
    cs = cstruct.cstruct(endian=">")

    assert cs.uint32.dumps(1) == b"\x00\x00\x00\x01"
    assert cs.uint16.dumps(255) == b"\x00\xff"
    assert cs.int8.dumps(-10) == b"\xf6"
    assert cs.uint8[4].dumps([1, 2, 3, 4]) == b"\x01\x02\x03\x04"
    assert cs.uint24.dumps(300) == b"\x00\x01\x2c"
    assert cs.int24.dumps(-1337) == b"\xff\xfa\xc7"
    assert cs.uint24[4].dumps([1, 2, 3, 4]) == b"\x00\x00\x01\x00\x00\x02\x00\x00\x03\x00\x00\x04"
    assert cs.char.dumps(0x61) == b"a"
    assert cs.wchar.dumps("lala") == b"\x00l\x00a\x00l\x00a"


def test_duplicate_type(compiled):
    cdef = """
    struct test {
        uint32  a;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    with pytest.raises(ValueError):
        cs.load(cdef)


def test_load_file(compiled):
    path = os.path.join(os.path.dirname(__file__), "data/testdef.txt")

    cs = cstruct.cstruct()
    cs.loadfile(path, compiled=compiled)
    assert "test" in cs.typedefs


def test_read_type_name():
    cs = cstruct.cstruct()
    cs.read("uint32", b"\x01\x00\x00\x00") == 1


def test_type_resolve():
    cs = cstruct.cstruct()

    assert cs.resolve("BYTE") == cs.uint8

    with pytest.raises(cstruct.ResolveError) as excinfo:
        cs.resolve("fake")
    assert "Unknown type" in str(excinfo.value)

    cs.addtype("ref0", "uint32")
    for i in range(1, 15):  # Recursion limit is currently 10
        cs.addtype(f"ref{i}", f"ref{i - 1}")

    with pytest.raises(cstruct.ResolveError) as excinfo:
        cs.resolve("ref14")
    assert "Recursion limit exceeded" in str(excinfo.value)


def test_constants():
    cdef = """
    #define a 1
    #define b 0x2
    #define c "test"
    #define d 1 << 1
    """
    cs = cstruct.cstruct()
    cs.load(cdef)

    assert cs.a == 1
    assert cs.b == 2
    assert cs.c == "test"
    assert cs.d == 2


def test_duplicate_types():
    cs = cstruct.cstruct()
    cdef = """
    struct A {
        uint32 a;
    };
    """
    cs.load(cdef)
    assert cs.A

    with pytest.raises(ValueError) as excinfo:
        cs.load(cdef)
    assert "Duplicate type" in str(excinfo.value)

    cs.load("""typedef uint32 Test;""")
    assert cs.Test is cs.uint32

    cs.load("""typedef uint32 Test;""")
    assert cs.Test is cs.uint32

    with pytest.raises(ValueError) as excinfo:
        cs.load("""typedef uint64 Test;""")
    assert "Duplicate type" in str(excinfo.value)


def test_typedef():
    cdef = """
    typedef uint32 test;
    """
    cs = cstruct.cstruct()
    cs.load(cdef)

    assert cs.test == cs.uint32
    assert cs.resolve("test") == cs.uint32


def test_lookups(compiled):
    cdef = """
    #define test_1 1
    #define test_2 2
    $a = {'test_1': 3, 'test_2': 4}
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)
    assert cs.lookups["a"] == {1: 3, 2: 4}


def test_default_constructors(compiled):
    cdef = """
    enum Enum {
        a = 0,
        b = 1
    };

    flag Flag {
        a = 0,
        b = 1
    };

    struct test {
        uint32  t_int;
        uint32  t_int_array[2];
        uint24  t_bytesint;
        uint24  t_bytesint_array[2];
        char    t_char;
        char    t_char_array[2];
        wchar   t_wchar;
        wchar   t_wchar_array[2];
        Enum    t_enum;
        Enum    t_enum_array[2];
        Flag    t_flag;
        Flag    t_flag_array[2];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test()
    assert obj.t_int == 0
    assert obj.t_int_array == [0, 0]
    assert obj.t_bytesint == 0
    assert obj.t_bytesint_array == [0, 0]
    assert obj.t_char == b"\x00"
    assert obj.t_char_array == b"\x00\x00"
    assert obj.t_wchar == "\x00"
    assert obj.t_wchar_array == "\x00\x00"
    assert obj.t_enum == cs.Enum(0)
    assert obj.t_enum_array == [cs.Enum(0), cs.Enum(0)]
    assert obj.t_flag == cs.Flag(0)
    assert obj.t_flag_array == [cs.Flag(0), cs.Flag(0)]

    assert obj.dumps() == b"\x00" * 54


def test_default_constructors_dynamic(compiled):
    cdef = """
    enum Enum {
        a = 0,
        b = 1
    };
    flag Flag {
        a = 0,
        b = 1
    };
    struct test {
        uint8   x;
        uint32  t_int_array_n[];
        uint32  t_int_array_d[x];
        uint24  t_bytesint_array_n[];
        uint24  t_bytesint_array_d[x];
        char    t_char_array_n[];
        char    t_char_array_d[x];
        wchar   t_wchar_array_n[];
        wchar   t_wchar_array_d[x];
        Enum    t_enum_array_n[];
        Enum    t_enum_array_d[x];
        Flag    t_flag_array_n[];
        Flag    t_flag_array_d[x];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)
    assert verify_compiled(cs.test, compiled)
    obj = cs.test()
    assert obj.t_int_array_n == obj.t_int_array_d == []
    assert obj.t_bytesint_array_n == obj.t_bytesint_array_d == []
    assert obj.t_char_array_n == obj.t_char_array_d == b""
    assert obj.t_wchar_array_n == obj.t_wchar_array_d == ""
    assert obj.t_enum_array_n == obj.t_enum_array_d == []
    assert obj.t_flag_array_n == obj.t_flag_array_d == []
    assert obj.dumps() == b"\x00" * 19


def test_config_flag_nocompile(compiled):
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
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.compiled_global, compiled)
    assert verify_compiled(cs.never_compiled, False)


def test_compiler_slicing_multiple(compiled):
    cdef = """
    struct compile_slicing {
        char single;
        char multiple[2];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.compile_slicing, compiled)

    obj = cs.compile_slicing(b"\x01\x02\x03")
    assert obj.single == b"\x01"
    assert obj.multiple == b"\x02\x03"


def test_underscores_attribute(compiled):
    cdef = """
    struct __test {
        uint32 test_val;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.__test, compiled)

    data = b"\x39\x05\x00\x00"
    obj = cs.__test(data)
    assert obj.test_val == 1337


def test_half_compiled_struct():
    from dissect.cstruct import RawType

    class OffByOne(RawType):
        def __init__(self, cstruct_obj):
            self._t = cstruct_obj.uint64
            super().__init__(cstruct_obj, "OffByOne", 8)

        def _read(self, stream):
            return self._t._read(stream) + 1

        def _write(self, stream, data):
            return self._t._write(stream, data - 1)

        def default(self):
            return 0

    cs = cstruct.cstruct()
    # Add an unsupported type for the cstruct compiler
    # so that it returns the original struct,
    # only partially compiling the struct.
    cs.addtype("offbyone", OffByOne(cs))
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


def test_cstruct_bytearray():
    cdef = """
    struct test {
        uint8 a;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef)

    obj = cs.test(bytearray([10]))
    assert obj.a == 10


def test_multipart_type_name():
    d = """
    enum TestEnum : unsigned int {
        A = 0,
        B = 1
    };

    struct test {
        unsigned int    a;
        unsigned long long  b;
    };
    """
    c = cstruct.cstruct()
    c.load(d)

    assert c.TestEnum.type == c.resolve("unsigned int")
    assert c.test.fields[0].type == c.resolve("unsigned int")
    assert c.test.fields[1].type == c.resolve("unsigned long long")

    with pytest.raises(ResolveError) as exc:
        d = """
        struct test {
            unsigned long long unsigned a;
        };
        """
        c = cstruct.cstruct()
        c.load(d)

    with pytest.raises(ResolveError) as exc:
        d = """
        enum TestEnum : unsigned int and more {
            A = 0,
            B = 1
        };
        """
        c = cstruct.cstruct()
        c.load(d)

    assert str(exc.value) == "Unknown type unsigned int and more"


def test_dunder_bytes():
    d = """
    struct test {
        DWORD   a;
        QWORD   b;
    };
    """
    c = cstruct.cstruct(endian=">")
    c.load(d)

    a = c.test(a=0xBADC0DE, b=0xACCE55ED)
    assert len(bytes(a)) == 12
    assert bytes(a) == a.dumps()
    assert bytes(a) == b"\x0b\xad\xc0\xde\x00\x00\x00\x00\xac\xceU\xed"
