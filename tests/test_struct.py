from io import BytesIO

import pytest

from dissect import cstruct

from .utils import verify_compiled


def test_struct_simple(compiled):
    cdef = """
    struct test {
        char    magic[4];
        wchar   wmagic[4];
        uint8   a;
        uint16  b;
        uint32  c;
        char    string[];
        wchar   wstring[];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"testt\x00e\x00s\x00t\x00\x01\x02\x03\x04\x05\x06\x07lalala\x00t\x00e\x00s\x00t\x00\x00\x00"
    obj = cs.test(buf)

    assert "magic" in obj
    assert obj.magic == b"test"
    assert obj["magic"] == obj.magic
    assert obj.wmagic == "test"
    assert obj.a == 0x01
    assert obj.b == 0x0302
    assert obj.c == 0x07060504
    assert obj.string == b"lalala"
    assert obj.wstring == "test"

    with pytest.raises(AttributeError):
        obj.nope

    assert obj._size("magic") == 4
    assert len(obj) == len(buf)
    assert obj.dumps() == buf

    assert repr(obj)

    fh = BytesIO()
    obj.write(fh)
    assert fh.getvalue() == buf


def test_struct_simple_be(compiled):
    cdef = """
    struct test {
        char    magic[4];
        wchar   wmagic[4];
        uint8   a;
        uint16  b;
        uint32  c;
        char    string[];
        wchar   wstring[];
    };
    """
    cs = cstruct.cstruct(endian=">")
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"test\x00t\x00e\x00s\x00t\x01\x02\x03\x04\x05\x06\x07lalala\x00\x00t\x00e\x00s\x00t\x00\x00"
    obj = cs.test(buf)

    assert obj.magic == b"test"
    assert obj.wmagic == "test"
    assert obj.a == 0x01
    assert obj.b == 0x0203
    assert obj.c == 0x04050607
    assert obj.string == b"lalala"
    assert obj.wstring == "test"
    assert obj.dumps() == buf


def test_struct_definitions(compiled):
    cdef = """
    struct _test {
        uint32  a;
        // uint32 comment
        uint32  b;
    } test, test1;
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert cs._test == cs.test == cs.test1
    assert cs.test.name == "_test"
    assert cs._test.name == "_test"

    assert "a" in cs.test.lookup
    assert "b" in cs.test.lookup

    with pytest.raises(cstruct.ParserError):
        cdef = """
        struct {
            uint32  a;
        };
        """
        cs.load(cdef)


def test_struct_expressions(compiled):
    cdef = """
    #define const 1
    struct test {
        uint8   flag;
        uint8   data_1[flag & 1 * 4];
        uint8   data_2[flag & (1 << 2)];
        uint8   data_3[const];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(b"\x01\x00\x01\x02\x03\xff")
    assert obj.flag == 1
    assert obj.data_1 == [0, 1, 2, 3]
    assert obj.data_2 == []
    assert obj.data_3 == [255]

    obj = cs.test(b"\x04\x04\x05\x06\x07\xff")
    assert obj.flag == 4
    assert obj.data_1 == []
    assert obj.data_2 == [4, 5, 6, 7]
    assert obj.data_3 == [255]


def test_struct_sizes(compiled):
    cdef = """
    struct static {
        uint32  test;
    };

    struct dynamic {
        uint32  test[];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.static, compiled)
    assert verify_compiled(cs.dynamic, compiled)

    assert len(cs.static) == 4

    if not compiled:
        cs.static.add_field("another", cs.uint32)
        assert len(cs.static) == 8
        cs.static.add_field("atoffset", cs.uint32, offset=12)
        assert len(cs.static) == 16

        obj = cs.static(b"\x01\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00")
        assert obj.test == 1
        assert obj.another == 2
        assert obj.atoffset == 3

        with pytest.raises(TypeError) as excinfo:
            len(cs.dynamic)
        assert str(excinfo.value) == "Dynamic size"
    else:
        with pytest.raises(NotImplementedError) as excinfo:
            cs.static.add_field("another", cs.uint32)
        assert str(excinfo.value) == "Can't add fields to a compiled structure"


def test_struct_nested(compiled):
    cdef = """
    struct test_named {
        char magic[4];
        struct {
            uint32 a;
            uint32 b;
        } a;
        struct {
            char   c[8];
        } b;
    };

    struct test_anonymous {
        char magic[4];
        struct {
            uint32 a;
            uint32 b;
        };
        struct {
            char   c[8];
        };
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test_named, compiled)
    assert verify_compiled(cs.test_anonymous, compiled)

    assert len(cs.test_named) == len(cs.test_anonymous) == 20

    data = b"zomg\x39\x05\x00\x00\x28\x23\x00\x00deadbeef"
    obj = cs.test_named(data)
    assert obj.magic == b"zomg"
    assert obj.a.a == 1337
    assert obj.a.b == 9000
    assert obj.b.c == b"deadbeef"
    assert obj.dumps() == data

    obj = cs.test_anonymous(data)
    assert obj.magic == b"zomg"
    assert obj.a == 1337
    assert obj.b == 9000
    assert obj.c == b"deadbeef"
    assert obj.dumps() == data


def test_struct_write(compiled):
    cdef = """
    struct test {
        char    magic[4];
        wchar   wmagic[4];
        uint8   a;
        uint16  b;
        uint32  c;
        char    string[];
        wchar   wstring[];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"testt\x00e\x00s\x00t\x00\x01\x02\x03\x04\x05\x06\x07lalala\x00t\x00e\x00s\x00t\x00\x00\x00"

    obj = cs.test()
    obj.magic = "test"
    obj.wmagic = "test"
    obj.a = 0x01
    obj.b = 0x0302
    obj.c = 0x07060504
    obj.string = b"lalala"
    obj.wstring = "test"

    with pytest.raises(AttributeError):
        obj.nope = 1

    assert obj.dumps() == buf

    inst = cs.test(
        magic=b"test",
        wmagic="test",
        a=0x01,
        b=0x0302,
        c=0x07060504,
        string=b"lalala",
        wstring="test",
    )
    assert inst.dumps() == buf


def test_struct_write_be(compiled):
    cdef = """
    struct test {
        char    magic[4];
        wchar   wmagic[4];
        uint8   a;
        uint16  b;
        uint32  c;
        char    string[];
        wchar   wstring[];
    };
    """
    cs = cstruct.cstruct(endian=">")
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"test\x00t\x00e\x00s\x00t\x01\x02\x03\x04\x05\x06\x07lalala\x00\x00t\x00e\x00s\x00t\x00\x00"

    obj = cs.test()
    obj.magic = "test"
    obj.wmagic = "test"
    obj.a = 0x01
    obj.b = 0x0203
    obj.c = 0x04050607
    obj.string = b"lalala"
    obj.wstring = "test"

    assert obj.dumps() == buf


def test_struct_write_anonymous():
    cdef = """
    struct test {
        uint32 a;
        union {
            struct {
                uint16 b1;
                uint16 b2;
            };
            uint32 b;
        };
        uint32 c;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef)

    obj = cs.test(a=1, c=3)
    assert obj.dumps() == b"\x01\x00\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00"
