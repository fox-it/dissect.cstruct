from __future__ import annotations

import inspect
from io import BytesIO
from textwrap import dedent
from types import MethodType
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call, patch

import pytest

from dissect.cstruct.exceptions import ParserError
from dissect.cstruct.types import structure
from dissect.cstruct.types.base import Array, BaseType
from dissect.cstruct.types.pointer import Pointer
from dissect.cstruct.types.structure import Field, Structure, StructureMetaType

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


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
    assert repr(TestStruct.fields["a"]) == "<Field a uint32>"

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

    cdef = """
    struct {
        uint32  a;
    };
    """
    with pytest.raises(ParserError, match="struct has no name"):
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

    for name in obj.fields:
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

    assert issubclass(cs.test.fields["b"].type, Pointer)
    assert cs.test.fields["b"].type.type is cs.test


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

    for name in obj.fields:
        assert isinstance(getattr(obj, name), BaseType)

    assert cs.test_nested() == cs.test_nested.__default__()

    obj = cs.test_nested.__default__()
    assert obj.t_struct == cs.test.__default__()
    assert obj.t_struct_array == [cs.test.__default__(), cs.test.__default__()]

    assert obj.dumps() == b"\x00" * 171

    for name in obj.fields:
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

    for name in obj.fields:
        assert isinstance(getattr(obj, name), BaseType)

    assert cs.test_nested() == cs.test_nested.__default__()

    obj = cs.test_nested.__default__()
    assert obj.t_struct_n == obj.t_struct_array_d == []

    assert obj.dumps() == b"\x00" * 21

    for name in obj.fields:
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

    obj = cs.test(1, 1)
    assert obj.a == 1
    assert obj.b == 1
    assert str(obj) == "<test a=0x1 b=0x1>"

    obj = cs.test(1)
    assert obj.a == 1
    assert obj.b == 0
    assert str(obj) == "<test a=0x1 b=0x0>"

    obj = cs.test(a=1)
    assert obj.a == 1
    assert obj.b == 0
    assert str(obj) == "<test a=0x1 b=0x0>"

    obj = cs.test(b=1)
    assert obj.a == 0
    assert obj.b == 1
    assert str(obj) == "<test a=0x0 b=0x1>"


def test_codegen_make_init() -> None:
    _make__init__ = structure._make_structure__init__.__wrapped__.__wrapped__

    result = _make__init__([f"_{n}" for n in range(5)])
    expected = """
    def __init__(self, _0 = None, _1 = None, _2 = None, _3 = None, _4 = None):
     self._0 = _0 if _0 is not None else _0_default
     self._1 = _1 if _1 is not None else _1_default
     self._2 = _2 if _2 is not None else _2_default
     self._3 = _3 if _3 is not None else _3_default
     self._4 = _4 if _4 is not None else _4_default
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
