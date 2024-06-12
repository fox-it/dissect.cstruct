import inspect
from io import BytesIO
from types import MethodType
from unittest.mock import MagicMock, call, patch

import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.exceptions import ParserError
from dissect.cstruct.types.base import Array, BaseType
from dissect.cstruct.types.pointer import Pointer
from dissect.cstruct.types.structure import Field, Structure, StructureMetaType

from .utils import verify_compiled


@pytest.fixture
def TestStruct(cs: cstruct) -> type[Structure]:
    return cs._make_struct(
        "TestStruct",
        [Field("a", cs.uint32), Field("b", cs.uint32)],
    )


def test_structure(TestStruct: type[Structure]) -> None:
    assert issubclass(TestStruct, Structure)
    assert len(TestStruct.fields) == 2
    assert TestStruct.fields["a"].name == "a"
    assert TestStruct.fields["b"].name == "b"

    assert TestStruct.size == 8
    assert TestStruct.alignment == 4

    spec = inspect.getfullargspec(TestStruct.__init__)
    assert spec.args == ["self", "a", "b"]
    assert spec.defaults == (None, None)

    obj = TestStruct(1, 2)
    assert isinstance(obj, TestStruct)
    assert obj.a == 1
    assert obj.b == 2
    assert len(obj) == 8

    obj = TestStruct(a=1)
    assert obj.a == 1
    assert obj.b is None
    assert len(obj) == 8

    # Test hashing of values
    assert hash((obj.a, obj.b)) == hash(obj)


def test_structure_read(TestStruct: type[Structure]) -> None:
    obj = TestStruct(b"\x01\x00\x00\x00\x02\x00\x00\x00")

    assert isinstance(obj, TestStruct)
    assert obj.a == 1
    assert obj.b == 2


def test_structure_write(TestStruct: type[Structure]) -> None:
    buf = b"\x01\x00\x00\x00\x02\x00\x00\x00"
    obj = TestStruct(buf)

    assert obj.dumps() == buf

    obj = TestStruct(a=1, b=2)
    assert obj.dumps() == buf
    assert bytes(obj) == buf

    obj = TestStruct(a=1)
    assert obj.dumps() == b"\x01\x00\x00\x00\x00\x00\x00\x00"

    obj = TestStruct()
    assert obj.dumps() == b"\x00\x00\x00\x00\x00\x00\x00\x00"


def test_structure_array_read(TestStruct: type[Structure]) -> None:
    TestStructArray = TestStruct[2]

    assert issubclass(TestStructArray, Array)
    assert TestStructArray.num_entries == 2
    assert TestStructArray.type == TestStruct

    buf = b"\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x04\x00\x00\x00"
    obj = TestStructArray(buf)

    assert isinstance(obj, TestStructArray)
    assert len(obj) == 2
    assert obj[0].a == 1
    assert obj[0].b == 2
    assert obj[1].a == 3
    assert obj[1].b == 4

    assert obj.dumps() == buf
    assert obj == [TestStruct(1, 2), TestStruct(3, 4)]

    obj = TestStruct[None](b"\x01\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
    assert obj == [TestStruct(1, 2)]


def test_structure_array_write(TestStruct: type[Structure]) -> None:
    TestStructArray = TestStruct[2]

    obj = TestStructArray([TestStruct(1, 2), TestStruct(3, 4)])

    assert len(obj) == 2
    assert obj.dumps() == b"\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x04\x00\x00\x00"

    obj = TestStruct[None]([TestStruct(1, 2)])
    assert obj.dumps() == b"\x01\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"


def test_structure_modify(cs: cstruct) -> None:
    TestStruct = cs._make_struct("Test", [Field("a", cs.char)])

    assert len(TestStruct.fields) == len(TestStruct.lookup) == 1
    assert len(TestStruct) == 1
    spec = inspect.getfullargspec(TestStruct.__init__)
    assert spec.args == ["self", "a"]
    assert spec.defaults == (None,)

    TestStruct.add_field("b", cs.char)

    assert len(TestStruct.fields) == len(TestStruct.lookup) == 2
    assert len(TestStruct) == 2
    spec = inspect.getfullargspec(TestStruct.__init__)
    assert spec.args == ["self", "a", "b"]
    assert spec.defaults == (None, None)

    with TestStruct.start_update():
        TestStruct.add_field("c", cs.char)
        TestStruct.add_field("d", cs.char)

    assert len(TestStruct.fields) == len(TestStruct.lookup) == 4
    assert len(TestStruct) == 4
    spec = inspect.getfullargspec(TestStruct.__init__)
    assert spec.args == ["self", "a", "b", "c", "d"]
    assert spec.defaults == (None, None, None, None)

    obj = TestStruct(b"abcd")
    assert obj.a == b"a"
    assert obj.b == b"b"
    assert obj.c == b"c"
    assert obj.d == b"d"


def test_structure_single_byte_field(cs: cstruct) -> None:
    TestStruct = cs._make_struct("TestStruct", [Field("a", cs.char)])

    obj = TestStruct(b"aaaa")
    assert obj.a == b"a"

    cs.char._read = MagicMock()

    obj = TestStruct(b"a")
    assert obj.a == b"a"
    cs.char._read.assert_not_called()


def test_structure_same_name_method(cs: cstruct) -> None:
    TestStruct = cs._make_struct("TestStruct", [Field("add_field", cs.char)])

    assert isinstance(TestStruct.add_field, MethodType)

    obj = TestStruct(b"a")
    assert obj.add_field == b"a"


def test_structure_bool(TestStruct: type[Structure]) -> None:
    assert bool(TestStruct(1, 2)) is True
    assert bool(TestStruct()) is False
    assert bool(TestStruct(0, 0)) is False


def test_structure_cmp(TestStruct: type[Structure]) -> None:
    assert TestStruct(1, 2) == TestStruct(1, 2)
    assert TestStruct(1, 2) != TestStruct(2, 3)


def test_structure_repr(TestStruct: type[Structure]) -> None:
    obj = TestStruct(1, 2)
    assert repr(obj) == f"<{TestStruct.__name__} a=0x1 b=0x2>"


def test_structure_eof(TestStruct: type[Structure]) -> None:
    with pytest.raises(EOFError):
        TestStruct(b"")

    with pytest.raises(EOFError):
        TestStruct[2](b"\x01\x00\x00\x00\x02\x00\x00\x00")

    with pytest.raises(EOFError):
        TestStruct[None](b"\x01\x00\x00\x00\x02\x00\x00\x00")


def test_structure_definitions(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct _test {
        uint32  a;
        // uint32 comment
        uint32  b;
    } test, test1;
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert cs._test == cs.test == cs.test1
    assert cs.test.__name__ == "_test"
    assert cs._test.__name__ == "_test"

    assert "a" in cs.test.fields
    assert "b" in cs.test.fields

    with pytest.raises(ParserError):
        cdef = """
        struct {
            uint32  a;
        };
        """
        cs.load(cdef)


def test_structure_definition_simple(cs: cstruct, compiled: bool) -> None:
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
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"testt\x00e\x00s\x00t\x00\x01\x02\x03\x04\x05\x06\x07lalala\x00t\x00e\x00s\x00t\x00\x00\x00"
    obj = cs.test(buf)

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

    assert obj._sizes["magic"] == 4
    assert len(obj) == len(buf)
    assert obj.dumps() == buf

    assert repr(obj)

    fh = BytesIO()
    obj.write(fh)
    assert fh.getvalue() == buf


def test_structure_definition_simple_be(cs: cstruct, compiled: bool) -> None:
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
    cs.endian = ">"
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

    for name in obj.fields.keys():
        assert isinstance(getattr(obj, name), BaseType)


def test_structure_definition_expressions(cs: cstruct, compiled: bool) -> None:
    cdef = """
    #define const 1
    struct test {
        uint8   flag;
        uint8   data_1[(flag & 1) * 4];
        uint8   data_2[flag & (1 << 2)];
        uint8   data_3[const];
    };
    """
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


def test_structure_definition_sizes(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct static {
        uint32  test;
    };

    struct dynamic {
        uint32  test[];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.static, compiled)
    assert verify_compiled(cs.dynamic, compiled)

    assert len(cs.static) == 4

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


def test_structure_definition_nested(cs: cstruct, compiled: bool) -> None:
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


def test_structure_definition_write(cs: cstruct, compiled: bool) -> None:
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
        obj.nope

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


def test_structure_definition_write_be(cs: cstruct, compiled: bool) -> None:
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
    cs.endian = ">"
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


def test_structure_definition_write_anonymous(cs: cstruct) -> None:
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
    cs.load(cdef)

    obj = cs.test(a=1, c=3)
    assert obj.dumps() == b"\x01\x00\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00"


def test_structure_field_discard(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint8 a;
        uint8 _;
        uint16 b;
        uint16 _;
        uint16 c;
        char d;
        char _;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    with patch.object(cs.char, "__new__") as mock_char_new:
        cs.test(b"\x01\x02\x03\x00\x04\x00\x05\x00ab")

        assert len(mock_char_new.mock_calls) == 2
        mock_char_new.assert_has_calls([call(cs.char, b"a"), call(cs.char, b"b")])


def test_structure_definition_self(cs: cstruct) -> None:
    cdef = """
    struct test {
        uint32 a;
        struct test * b;
    };
    """
    cs.load(cdef)

    assert issubclass(cs.test.fields["b"].type, Pointer)
    assert cs.test.fields["b"].type.type is cs.test


def test_align_struct_in_struct(cs: cstruct) -> None:
    with patch.object(StructureMetaType, "_update_fields") as update_fields:
        cs._make_struct("test", [Field("a", cs.uint64)], align=True)

        _, kwargs = update_fields.call_args
        assert kwargs["align"]
