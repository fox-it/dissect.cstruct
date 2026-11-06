from __future__ import annotations

import inspect
from io import BytesIO
from textwrap import dedent
from types import MethodType
from unittest.mock import call, patch

import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.exception import ArraySizeError, ResolveError
from dissect.cstruct.types import structure
from dissect.cstruct.types.base import Array, BaseType
from dissect.cstruct.types.pointer import Pointer
from dissect.cstruct.types.structure import Field, Structure, StructureMetaType
from tests.util import verify_compiled


@pytest.fixture
def TestStruct(cs: cstruct) -> type[Structure]:
    return cs._make_struct(
        "TestStruct",
        [Field("a", cs.uint32), Field("b", cs.uint32)],
    )


def test_structure(TestStruct: type[Structure]) -> None:
    assert issubclass(TestStruct, Structure)
    assert len(TestStruct.__members__) == 2
    assert TestStruct.__members__["a"].name == "a"
    assert TestStruct.__members__["b"].name == "b"
    assert repr(TestStruct.__members__["a"]) == "<Field a uint32>"

    assert TestStruct.__size__ == 8
    assert TestStruct.__alignment__ == 4

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
    assert obj.b == 0
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
    assert obj.a == 0
    assert obj.dumps() == b"\x00\x00\x00\x00\x00\x00\x00\x00"

    obj.a = None
    assert obj.dumps() == b"\x00\x00\x00\x00\x00\x00\x00\x00"


def test_structure_array_read(TestStruct: type[Structure]) -> None:
    TestStructArray = TestStruct[2]

    assert issubclass(TestStructArray, Array)
    assert TestStructArray.__num_entries__ == 2
    assert TestStructArray.__type__ == TestStruct

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

    assert len(TestStruct.__members__) == len(TestStruct.__lookup__) == 1
    assert len(TestStruct) == 1
    spec = inspect.getfullargspec(TestStruct.__init__)
    assert spec.args == ["self", "a"]
    assert spec.defaults == (None,)

    TestStruct.add_field("b", cs.char)

    assert len(TestStruct.__members__) == len(TestStruct.__lookup__) == 2
    assert len(TestStruct) == 2
    spec = inspect.getfullargspec(TestStruct.__init__)
    assert spec.args == ["self", "a", "b"]
    assert spec.defaults == (None, None)

    with TestStruct.start_update():
        TestStruct.add_field("c", cs.char)
        TestStruct.add_field("d", cs.char)

    assert len(TestStruct.__members__) == len(TestStruct.__lookup__) == 4
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

    obj = TestStruct(b"a")
    assert obj.a == b"a"


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

    assert verify_compiled(cs._test, compiled)
    assert cs._test.__name__ == "_test"

    # test and test1 are variable names, not type names, so they should not be registered in the cstruct
    with pytest.raises(ResolveError, match="Unknown type test"):
        assert cs.resolve("test")

    with pytest.raises(ResolveError, match="Unknown type test1"):
        assert cs.resolve("test1")

    assert "a" in cs._test.__members__
    assert "b" in cs._test.__members__

    # This will work but is kind of pointless
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
        obj.nope  # noqa: B018

    assert obj.__dynamic_sizes__ == {"string": 7, "wstring": 10}
    assert obj.__sizes__ == {"magic": 4, "wmagic": 8, "a": 1, "b": 2, "c": 4, "string": 7, "wstring": 10}
    assert len(obj) == len(buf)
    assert obj.dumps() == buf

    assert repr(obj)

    fh = BytesIO()
    obj.write(fh)
    assert fh.getvalue() == buf


def test_structure_values_dict(cs: cstruct, compiled: bool) -> None:
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
    buf = b"testt\x00e\x00s\x00t\x00\x01\x02\x03\x04\x05\x06\x07lalala\x00t\x00e\x00s\x00t\x00\x00\x00"
    obj = cs.test(buf)

    # Test reading all values
    values = obj.__values__
    assert values["magic"] == b"test"
    assert values["wmagic"] == "test"
    assert values["a"] == 0x01
    assert values["b"] == 0x0302
    assert values["c"] == 0x07060504
    assert values["string"] == b"lalala"
    assert values["wstring"] == "test"

    # Test writing a single field through the proxy
    values["a"] = 0xFF
    assert obj.a == 0xFF

    # Test dictionary methods
    assert values.keys() == {"magic", "wmagic", "a", "b", "c", "string", "wstring"}


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

    for name in obj.__members__:
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

    with pytest.raises(TypeError, match="Dynamic size"):
        len(cs.dynamic)


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
        obj.nope  # noqa: B018

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


def test_structure_field_duplicate(cs: cstruct) -> None:
    cdef = """
    struct test {
        uint8 a;
        uint8 a;
    };
    """
    with pytest.raises(ValueError, match="Duplicate field name: a"):
        cs.load(cdef)


def test_structure_definition_self(cs: cstruct) -> None:
    cdef = """
    struct test {
        uint32 a;
        struct test * b;
    };
    """
    cs.load(cdef)

    assert issubclass(cs.test.__members__["b"].type, Pointer)
    assert cs.test.__members__["b"].type.__type__ is cs.test


def test_align_struct_in_struct(cs: cstruct) -> None:
    with patch.object(StructureMetaType, "_update_fields") as update_fields:
        cs._make_struct("test", [Field("a", cs.uint64)], align=True)

        _, kwargs = update_fields.call_args
        assert kwargs["align"]


def test_structure_default(cs: cstruct, compiled: bool) -> None:
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
        uint8   *t_pointer;
        uint8   *t_pointer_array[2];
    };

    struct test_nested {
        test    t_struct;
        test    t_struct_array[2];
    };
    """
    cs.pointer = cs.uint8
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert cs.test() == cs.test.__default__()

    obj = cs.test.__default__()
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
    assert obj.t_pointer == 0
    assert isinstance(obj.t_pointer, Pointer)
    assert obj.t_pointer_array == [0, 0]
    assert isinstance(obj.t_pointer_array[0], Pointer)
    assert isinstance(obj.t_pointer_array[1], Pointer)

    assert obj.dumps() == b"\x00" * 57

    for name in obj.__members__:
        assert isinstance(getattr(obj, name), BaseType)

    assert cs.test_nested() == cs.test_nested.__default__()

    obj = cs.test_nested.__default__()
    assert obj.t_struct == cs.test.__default__()
    assert obj.t_struct_array == [cs.test.__default__(), cs.test.__default__()]

    assert obj.dumps() == b"\x00" * 171

    for name in obj.__members__:
        assert isinstance(getattr(obj, name), BaseType)


def test_structure_default_dynamic(cs: cstruct, compiled: bool) -> None:
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
        uint8   *t_pointer_n[];
        uint8   *t_pointer_d[x];
    };

    struct test_nested {
        uint8   x;
        test    t_struct_n[];
        test    t_struct_array_d[x];
    };
    """
    cs.pointer = cs.uint8
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert cs.test() == cs.test.__default__()

    obj = cs.test()
    assert obj.t_int_array_n == obj.t_int_array_d == []
    assert obj.t_bytesint_array_n == obj.t_bytesint_array_d == []
    assert obj.t_char_array_n == obj.t_char_array_d == b""
    assert obj.t_wchar_array_n == obj.t_wchar_array_d == ""
    assert obj.t_enum_array_n == obj.t_enum_array_d == []
    assert obj.t_flag_array_n == obj.t_flag_array_d == []
    assert obj.t_pointer_n == obj.t_pointer_d == []

    assert obj.dumps() == b"\x00" * 20

    for name in obj.__members__:
        assert isinstance(getattr(obj, name), BaseType)

    assert cs.test_nested() == cs.test_nested.__default__()

    obj = cs.test_nested.__default__()
    assert obj.t_struct_n == obj.t_struct_array_d == []

    assert obj.dumps() == b"\x00" * 21

    for name in obj.__members__:
        assert isinstance(getattr(obj, name), BaseType)


def test_structure_partial_initialization(cs: cstruct) -> None:
    cdef = """
    struct test {
        uint8 a;
        uint8 b;
    };
    """
    cs.load(cdef)

    obj = cs.test()
    assert obj.a == 0
    assert obj.b == 0
    assert str(obj) == "<test a=0x0 b=0x0>"
    assert obj.__sizes__ == {"a": 1, "b": 1}

    obj = cs.test(1, 1)
    assert obj.a == 1
    assert obj.b == 1
    assert str(obj) == "<test a=0x1 b=0x1>"
    assert obj.__sizes__ == {"a": 1, "b": 1}

    obj = cs.test(1)
    assert obj.a == 1
    assert obj.b == 0
    assert str(obj) == "<test a=0x1 b=0x0>"
    assert obj.__sizes__ == {"a": 1, "b": 1}

    obj = cs.test(a=1)
    assert obj.a == 1
    assert obj.b == 0
    assert str(obj) == "<test a=0x1 b=0x0>"
    assert obj.__sizes__ == {"a": 1, "b": 1}

    obj = cs.test(b=1)
    assert obj.a == 0
    assert obj.b == 1
    assert str(obj) == "<test a=0x0 b=0x1>"


def test_codegen_make_init() -> None:
    _make__init__ = structure._make_structure__init__.__wrapped__.__wrapped__

    result = _make__init__([f"_{n}" for n in range(5)])
    expected = """
    def __init__(self, _0 = None, _1 = None, _2 = None, _3 = None, _4 = None):
     self._0 = _0 if _0 is not None else _0_default()
     self._1 = _1 if _1 is not None else _1_default()
     self._2 = _2 if _2 is not None else _2_default()
     self._3 = _3 if _3 is not None else _3_default()
     self._4 = _4 if _4 is not None else _4_default()
    """
    assert result == dedent(expected[1:].rstrip())

    structure._make_structure__init__.cache_clear()
    assert structure._make_structure__init__.cache_info() == (0, 0, 128, 0)
    result = structure._make_structure__init__(5)
    assert structure._make_structure__init__.cache_info() == (0, 1, 128, 1)
    cached = structure._make_structure__init__(5)
    assert structure._make_structure__init__.cache_info() == (1, 1, 128, 1)
    assert result is cached


def test_codegen_hashable(cs: cstruct) -> None:
    hashable_fields = [Field("a", cs.uint8), Field("b", cs.uint8)]
    unhashable_fields = [Field("a", cs.uint8[2]), Field("b", cs.uint8)]

    with pytest.raises(TypeError, match="unhashable type: 'uint8\\[2\\]'"):
        hash(unhashable_fields[0].type.__default__())

    assert hash(structure._generate_structure__init__(hashable_fields).__code__)
    assert hash(structure._generate_structure__init__(unhashable_fields).__code__)


def test_structure_definition_newline(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        char    magic[4
        ];

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
    obj.magic = b"test"
    obj.wmagic = "test"
    obj.a = 0x01
    obj.b = 0x0203
    obj.c = 0x04050607
    obj.string = b"lalala"
    obj.wstring = "test"

    assert obj.dumps() == buf


def test_cdef_struct(cs: cstruct) -> None:
    cs.load("struct Point { int32 x; int32 y; };")

    assert cs.Point.cdef() == dedent(
        """\
        struct Point {
            int32 x;
            int32 y;
        };"""
    )


def test_cdef_arrays_pointers_bitfields(cs: cstruct) -> None:
    cs.load(
        """
        struct Test {
            char magic[4];
            uint32 dynamic[len];
            uint8 terminated[];
            uint32 *ptr;
            uint16 field : 4;
        };
        """
    )

    assert cs.Test.cdef() == dedent(
        """\
        struct Test {
            char magic[4];
            uint32 dynamic[len];
            uint8 terminated[];
            uint32 *ptr;
            uint16 field : 4;
        };"""
    )


def test_cdef_anonymous_nested(cs: cstruct) -> None:
    cs.load(
        """
        struct Test {
            struct {
                uint8 a;
                uint8 b;
            } named;
            struct {
                uint32 c;
            };
        };
        """
    )

    assert cs.Test.cdef() == dedent(
        """\
        struct Test {
            struct {
                uint8 a;
                uint8 b;
            } named;
            struct {
                uint32 c;
            };
        };"""
    )


def test_cdef_referenced_define(cs: cstruct) -> None:
    cs.load(
        """
        #define HEADER_SIZE 8
        #define UNUSED 99
        struct Test {
            uint32 count;
            uint8 data[count * HEADER_SIZE];
        };
        """
    )

    # Only the constant referenced in the array size should be emitted
    assert cs.Test.cdef(recursive=True) == dedent(
        """\
        #define HEADER_SIZE 8

        struct Test {
            uint32 count;
            uint8 data[count * HEADER_SIZE];
        };"""
    )

    reparsed = cstruct()
    reparsed.load(cs.Test.cdef(recursive=True))
    assert reparsed.consts["HEADER_SIZE"] == 8
    assert "UNUSED" not in reparsed.consts


def test_cdef_referenced_define_deduplicated(cs: cstruct) -> None:
    """Constants referenced from multiple fields or nested structs should be emitted once,
    as a single contiguous block (no blank lines between ``#define`` entries).
    """
    cs.load(
        """
        #define HEADER_SIZE 8
        #define TRAILER_SIZE 4
        struct Inner {
            uint32 n;
            uint8 payload[n * HEADER_SIZE];
        };
        struct Test {
            uint32 count;
            uint8 data[count * HEADER_SIZE];
            uint8 tail[count * TRAILER_SIZE];
            uint8 pad[count * HEADER_SIZE + count];
            Inner inner;
        };
        """
    )

    assert cs.Test.cdef(recursive=True) == dedent(
        """\
        #define HEADER_SIZE 8
        #define TRAILER_SIZE 4

        struct Inner {
            uint32 n;
            uint8 payload[n * HEADER_SIZE];
        };

        struct Test {
            uint32 count;
            uint8 data[count * HEADER_SIZE];
            uint8 tail[count * TRAILER_SIZE];
            uint8 pad[count * HEADER_SIZE + count];
            Inner inner;
        };"""
    )


def test_cdef_non_recursive_references_by_name(cs: cstruct) -> None:
    cs.load("struct Inner { uint32 a; }; struct Outer { Inner inner; };")

    assert cs.Outer.cdef() == dedent(
        """\
        struct Outer {
            Inner inner;
        };"""
    )


def test_cdef_recursive(cs: cstruct) -> None:
    cs.load(
        """
        enum Color : uint16 { RED = 1, GREEN = 2 };
        struct Inner { uint32 a; };
        struct Outer { Inner inner; Color color; };
        """
    )

    assert cs.Outer.cdef(recursive=True) == dedent(
        """\
        struct Inner {
            uint32 a;
        };

        enum Color : uint16 {
            RED = 1,
            GREEN = 2,
        };

        struct Outer {
            Inner inner;
            Color color;
        };"""
    )


def test_cdef_recursive_self_reference(cs: cstruct) -> None:
    cs.load("struct Node { uint32 value; Node *next; };")

    # Should not recurse infinitely on self-referencing structures
    assert cs.Node.cdef(recursive=True) == dedent(
        """\
        struct Node {
            uint32 value;
            Node *next;
        };"""
    )


def test_cdef_round_trip(cs: cstruct) -> None:
    cs.load(
        """
        enum Color : uint16 { RED = 1, GREEN = 2, BLUE = 4 };
        struct Point { int32 x; int32 y; };
        union Val { uint32 as_int; float as_float; };
        struct Header {
            char magic[4];
            uint32 version;
            Color color;
            Point points[2];
            Val v;
            uint32 *ptr;
            struct { uint8 a : 3; uint8 b : 5; } bits;
        };
        """
    )

    reparsed = cstruct()
    reparsed.load(cs.Header.cdef(recursive=True))

    for name in ("Header", "Point", "Color", "Val"):
        original = getattr(cs, name)
        result = getattr(reparsed, name)
        assert len(original) == len(result)

        if hasattr(original, "__fields__"):
            assert [f._name for f in original.__fields__] == [f._name for f in result.__fields__]
            assert [f.offset for f in original.__fields__] == [f.offset for f in result.__fields__]


def test_structure_changing_endian(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint32 a;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert cs.endian == "<"

    buf = b"\x01\x02\x03\x04"
    obj = cs.test(buf)

    assert obj.a == 0x04030201

    assert obj.dumps() == buf

    obj = cs.test(buf, endian=">")
    assert obj.a == 0x01020304

    assert obj.dumps(endian=">") == buf


def test_structure_endian_name_conflict(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        uint32 endian;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert cs.endian == "<"

    assert cs.test(endian=69).endian == 69
    assert cs.test(b"\x45\x00\x00\x00").endian == 69
    assert cs.test(b"\x45\x00\x00\x00", endian=">").endian == 0x45000000

    with pytest.raises(EOFError):
        cs.test(b"", endian=">")


def test_structure_changing_endian_field_types(cs: cstruct, compiled: bool) -> None:
    """Test that the endian argument is used for wchar and non-standard integer fields too."""
    cdef = """
    struct test {
        uint16  a;
        wchar   b[2];
        wchar   c;
        int24   d;
        uint24  e[2];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = bytes(range(1, 18))
    obj = cs.test(buf)

    assert obj.a == 0x0201
    assert obj.b == "\u0403\u0605"
    assert obj.c == "\u0807"
    assert obj.d == 0x0B0A09
    assert obj.e == [0x0E0D0C, 0x11100F]

    assert obj.dumps() == buf

    obj = cs.test(buf, endian=">")

    assert obj.a == 0x0102
    assert obj.b == "\u0304\u0506"
    assert obj.c == "\u0708"
    assert obj.d == 0x090A0B
    assert obj.e == [0x0C0D0E, 0x0F1011]

    assert obj.dumps(endian=">") == buf


def test_structure_subclass_init(cs: cstruct, compiled: bool) -> None:
    """Test that subclasses of a structure call their own __init__ method when reading."""
    cdef = """
    struct test {
        uint32  a;
        uint32  b;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    class Subclass(cs.test):
        def __init__(self, a: int | None = None, b: int | None = None):
            super().__init__(a, b)
            self.initialized = True

    obj = Subclass(b"\x01\x00\x00\x00\x02\x00\x00\x00")
    assert isinstance(obj, Subclass)
    assert obj.initialized
    assert (obj.a, obj.b) == (1, 2)

    obj = cs.test(b"\x01\x00\x00\x00\x02\x00\x00\x00")
    assert type(obj) is cs.test
    assert list(obj.__dict__) == ["a", "b", "__dynamic_sizes__"]


def test_structure_default_not_shared(cs: cstruct, compiled: bool) -> None:
    """Test that nested structures and arrays in default values aren't shared between instances or array entries."""
    cdef = """
    struct nested {
        uint8 a;
    };

    struct test {
        nested b;
        uint8  c[2];
        nested d[2];
        uint8  e[2][2];
    };
    """
    cs.load(cdef, compiled=compiled)

    obj = cs.test()
    obj.b.a = 1
    obj.c[0] = 2
    obj.d[0].a = 3
    obj.e[0][0] = 4

    # Entries of an array are separate values
    assert obj.d[1].a == 0
    assert obj.e[1] == [0, 0]

    # Values of different instances are separate values
    assert cs.test().dumps() == b"\x00\x00\x00\x00\x00\x00\x00\x00\x00"


def test_structure_write_return_value(cs: cstruct, compiled: bool) -> None:
    """Test that writing a structure returns the amount of bytes written, including padding and bit fields."""
    cdef = """
    struct test {
        uint8  a;
        uint16 b : 4;
        uint16 c : 12;
        uint32 d;
        uint8  e;
    };
    """
    cs.load(cdef, compiled=compiled, align=True)

    assert verify_compiled(cs.test, compiled)

    fh = BytesIO()
    assert cs.test(a=1, b=2, c=3, d=4, e=5).write(fh) == 12
    assert fh.getvalue() == b"\x01\x00\x32\x00\x04\x00\x00\x00\x05\x00\x00\x00"


def test_structure_write_missing_attribute(cs: cstruct, compiled: bool) -> None:
    """Test that writing a structure raises an error for missing attributes, instead of writing a default value."""
    cdef = """
    struct nested {
        uint8 a;
    };

    struct test {
        uint8  b;
        nested c;
        uint8  n;
        uint8  d[n];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(b=1, c=cs.nested(a=2), n=1, d=[3])
    assert obj.dumps() == b"\x01\x02\x01\x03"

    del obj.b
    with pytest.raises(AttributeError, match="'test' object has no attribute 'b'"):
        obj.dumps()

    obj = cs.test(b=1, c=cs.nested(a=2), n=1, d=[3])
    del obj.d
    with pytest.raises(AttributeError, match="'test' object has no attribute 'd'"):
        obj.dumps()

    obj = cs.test(b=1, c=cs.nested(a=2), n=1, d=[3])
    del obj.c.a
    with pytest.raises(AttributeError, match="'nested' object has no attribute 'a'"):
        obj.dumps()


def test_structure_write_dynamic(cs: cstruct, compiled: bool) -> None:
    """Test that dynamic fields are written by the length of their value instead of by evaluating their expression."""
    cdef = """
    struct test {
        uint8   n;
        uint16  a[n];
        uint8   b;
        char    c[n];
        wchar   d[];
        uint8   e;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x02\x01\x00\x02\x00\x03ab\x78\x00\x00\x00\x04"
    fh = BytesIO()
    assert cs.test(buf).write(fh) == len(buf)
    assert fh.getvalue() == buf

    # The length of a value doesn't have to match the expression
    assert (
        cs.test(n=1, a=[1, 2, 3], b=4, c=b"xy", d="", e=5).dumps() == b"\x01\x01\x00\x02\x00\x03\x00\x04xy\x00\x00\x05"
    )


def test_structure_write_nested(cs: cstruct, compiled: bool) -> None:
    """Test that nested structures are written in both endiannesses, and raise errors for invalid values."""
    cdef = """
    struct inner {
        uint8   a;
        char    b[2];
    };

    struct nested {
        uint16  c;
        inner   d;
    };

    struct test {
        uint8   e;
        nested  f;
        uint8   g;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x02\x00\x03ab\x04"
    obj = cs.test(buf)
    assert obj.dumps() == buf
    assert obj.dumps(endian=">") == b"\x01\x00\x02\x03ab\x04"

    # Any other value that isn't a structure doesn't have the attributes to write
    with pytest.raises(AttributeError, match="'int' object has no attribute"):
        cs.test(e=1, f=5, g=4).dumps()
    with pytest.raises(AttributeError, match="'int' object has no attribute"):
        cs.test(e=1, f=cs.nested(c=2, d=5), g=4).dumps()

    with pytest.raises(ArraySizeError, match="Expected static array size 2, got 3 instead"):
        cs.test(e=1, f=cs.nested(c=2, d=cs.inner(a=3, b=b"abc")), g=4).dumps()


def test_structure_write_nested_padding(cs: cstruct, compiled: bool) -> None:
    """Test that the padding of an offset in a nested structure is written as a part of that structure."""
    cdef = """
    struct nested {
        uint8   a;
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.nested.add_field("b", cs.uint16, offset=4)

    cdef = """
    struct test {
        uint8   c;
        nested  d;
        uint8   e;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    fh = BytesIO()
    assert cs.test(c=1, d=cs.nested(a=2, b=3), e=4).write(fh) == 8
    assert fh.getvalue() == b"\x01\x02\x00\x00\x00\x03\x00\x04"


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        # Padding
        (8, b"\x01\x02\x00\x00\x00\x00\x00\x00\x03\x00\x04"),
        # Exactly at the current position
        (5, b"\x01\x02\x00\x00\x00\x03\x00\x04"),
        # Before the current position, writing doesn't go back
        (2, b"\x01\x02\x00\x00\x00\x03\x00\x04"),
    ],
)
def test_structure_write_offset(cs: cstruct, compiled: bool, offset: int, expected: bytes) -> None:
    """Test that fields with an offset get padding if they're ahead of the stream, and that writing doesn't go back."""
    cdef = """
    struct test {
        uint8   a;
        uint32  b;
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.test.add_field("c", cs.uint16, offset=offset)
    cs.test.add_field("d", cs.uint8)

    assert verify_compiled(cs.test, compiled)

    fh = BytesIO()
    assert cs.test(a=1, b=2, c=3, d=4).write(fh) == len(expected)
    assert fh.getvalue() == expected


def test_structure_write_offset_not_packed(cs: cstruct, compiled: bool) -> None:
    """Test that a field with an offset gets padding if it's written using its own type."""
    cdef = """
    struct test {
        uint8   a;
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.test.add_field("b", cs.uint8[2][1], offset=4)
    cs.test.add_field("c", cs.uint8)

    assert verify_compiled(cs.test, compiled)

    fh = BytesIO()
    assert cs.test(a=1, b=[[2, 3]], c=4).write(fh) == 7
    assert fh.getvalue() == b"\x01\x00\x00\x00\x02\x03\x04"


def test_structure_write_offset_after_dynamic_field(cs: cstruct, compiled: bool) -> None:
    """Test that a field with an offset after a dynamic field only gets padding if the dynamic field is short enough."""
    cdef = """
    struct test {
        uint8   n;
        uint8   a[n];
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.test.add_field("b", cs.uint8, offset=4)
    cs.test.add_field("c", cs.uint8, offset=6)
    cs.test.add_field("d", cs.uint8)

    assert verify_compiled(cs.test, compiled)

    # Padding only if the dynamic field is short enough
    fh = BytesIO()
    assert cs.test(n=1, a=[2], b=3, c=4, d=5).write(fh) == 8
    assert fh.getvalue() == b"\x01\x02\x00\x00\x03\x00\x04\x05"

    fh = BytesIO()
    assert cs.test(n=5, a=[2, 2, 2, 2, 2], b=3, c=4, d=5).write(fh) == 9
    assert fh.getvalue() == b"\x05\x02\x02\x02\x02\x02\x03\x04\x05"


def test_structure_write_field_names(cs: cstruct, compiled: bool) -> None:
    """Test that field names that aren't valid identifiers and duplicate field names are written correctly."""
    cdef = """
    struct test {
        uint8   class;
        uint8   from;
        uint8   _;
        uint8   _;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    # Duplicate fields use the same attribute
    obj = cs.test(b"\x01\x02\x03\x04")
    assert obj.dumps() == b"\x01\x02\x04\x04"


def test_structure_write_none(cs: cstruct, compiled: bool) -> None:
    """Test that values of ``None`` are written with the default value of their type, for every kind of field."""
    cdef = """
    enum Test : uint8 {
        A = 1
    };

    struct nested {
        uint8 a;
    };

    struct test {
        uint16  b;
        uint24  c;
        Test    d;
        char    e;
        char    f[2];
        wchar   g;
        wchar   h[2];
        uint8   i[2];
        uint24  j[1];
        nested  k;
        uint8   l : 4;
        uint8   m : 4;
        uint8   n[2][1];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test()
    for field in cs.test.__fields__:
        setattr(obj, field._name, None)

    assert obj.dumps() == bytes(24)
