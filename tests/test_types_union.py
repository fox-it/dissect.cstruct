from __future__ import annotations

import inspect
from textwrap import dedent

import pytest

from dissect.cstruct import compiler
from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.types import structure
from dissect.cstruct.types.base import Array, BaseType
from dissect.cstruct.types.structure import Field, Union, UnionProxy

from .utils import parsed_state, source_lines, verify_compiled


@pytest.fixture
def TestUnion(cs: cstruct, compiled: bool) -> type[Union]:
    union = cs._make_union(
        "TestUnion",
        [Field("a", cs.uint32), Field("b", cs.uint16)],
    )
    if compiled:
        compiler.compile_structure(union)

    assert verify_compiled(union, compiled)
    return union


def test_union(TestUnion: type[Union]) -> None:
    assert issubclass(TestUnion, Union)
    assert len(TestUnion.__members__) == 2
    assert TestUnion.__members__["a"].name == "a"
    assert TestUnion.__members__["b"].name == "b"

    assert TestUnion.__size__ == 4
    assert TestUnion.__alignment__ == 4

    spec = inspect.getfullargspec(TestUnion.__init__)
    assert spec.args == ["self", "a", "b"]
    assert spec.defaults == (None, None)

    obj = TestUnion(1, 2)
    assert isinstance(obj, TestUnion)
    assert obj.a == 1
    assert obj.b == 1
    assert len(obj) == 4

    obj = TestUnion(a=1)
    assert obj.a == 1
    assert obj.b == 1
    assert len(obj) == 4

    obj = TestUnion(b=1)
    assert obj.a == 1
    assert obj.b == 1
    assert len(obj) == 4

    assert hash((obj.a, obj.b)) == hash(obj)


def test_union_read(TestUnion: type[Union]) -> None:
    obj = TestUnion(b"\x01\x00\x00\x00")

    assert isinstance(obj, TestUnion)
    assert obj.a == 1
    assert obj.b == 1


def test_union_read_offset(cs: cstruct, TestUnion: type[Union]) -> None:
    TestUnion.add_field("c", cs.uint8, offset=3)

    obj = TestUnion(b"\x01\x00\x00\x02")
    assert obj.a == 0x02000001
    assert obj.b == 0x0001
    assert obj.c == 0x02

    obj = TestUnion(1)
    assert obj.a == 1
    assert obj.b == 1
    assert obj.c == 0


def test_union_write(TestUnion: type[Union]) -> None:
    buf = b"\x01\x00\x00\x00"
    obj = TestUnion(buf)

    assert obj.dumps() == buf

    obj = TestUnion(a=1, b=2)
    assert obj.dumps() == buf
    assert bytes(obj) == buf

    obj = TestUnion(b=1)
    assert obj.dumps() == b"\x01\x00\x00\x00"

    obj = TestUnion()
    assert obj.dumps() == b"\x00\x00\x00\x00"

    obj = TestUnion(5, 1)
    assert obj.dumps() == b"\x05\x00\x00\x00"
    obj.a = None
    assert obj.a == 0
    assert obj.dumps() == b"\x00\x00\x00\x00"

    obj = TestUnion(None, 1)
    assert obj.a == 0
    assert obj.dumps() == b"\x00\x00\x00\x00"

    obj = TestUnion(1, None)
    assert obj.b == 1
    assert obj.dumps() == b"\x01\x00\x00\x00"


def test_union_write_anonymous(cs: cstruct, compiled: bool) -> None:
    cdef = """
    union test {
        struct {
            uint32 a;
        };
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(b"\x01\x00\x00\x00")
    assert obj.a == 1
    assert obj.dumps() == b"\x01\x00\x00\x00"


def test_union_array_read(TestUnion: type[Union]) -> None:
    TestUnionArray = TestUnion[2]

    assert issubclass(TestUnionArray, Array)
    assert TestUnionArray.__num_entries__ == 2
    assert TestUnionArray.__type__ == TestUnion

    buf = b"\x01\x00\x00\x00\x02\x00\x00\x00"
    obj = TestUnionArray(buf)

    assert isinstance(obj, TestUnionArray)
    assert len(obj) == 2
    assert obj[0].a == 1
    assert obj[0].b == 1
    assert obj[1].a == 2
    assert obj[1].b == 2

    assert obj.dumps() == buf
    assert obj == [TestUnion(1), TestUnion(2)]

    obj = TestUnion[None](b"\x01\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00")
    assert obj == [TestUnion(1), TestUnion(2)]


def test_union_array_write(TestUnion: type[Union]) -> None:
    TestUnionArray = TestUnion[2]

    obj = TestUnionArray([TestUnion(1), TestUnion(2)])

    assert len(obj) == 2
    assert obj.dumps() == b"\x01\x00\x00\x00\x02\x00\x00\x00"

    obj = TestUnion[None]([TestUnion(1)])
    assert obj.dumps() == b"\x01\x00\x00\x00\x00\x00\x00\x00"


def test_union_modify(cs: cstruct) -> None:
    TestUnion = cs._make_union("Test", [Field("a", cs.char)])

    assert len(TestUnion.__members__) == len(TestUnion.__lookup__) == 1
    assert len(TestUnion) == 1
    spec = inspect.getfullargspec(TestUnion.__init__)
    assert spec.args == ["self", "a"]
    assert spec.defaults == (None,)

    TestUnion.add_field("b", cs.uint32)

    assert len(TestUnion.__members__) == len(TestUnion.__lookup__) == 2
    assert len(TestUnion) == 4
    spec = inspect.getfullargspec(TestUnion.__init__)
    assert spec.args == ["self", "a", "b"]
    assert spec.defaults == (None, None)

    with TestUnion.start_update():
        TestUnion.add_field("c", cs.uint16)
        TestUnion.add_field("d", cs.uint8)

    assert len(TestUnion.__members__) == len(TestUnion.__lookup__) == 4
    assert len(TestUnion) == 4
    spec = inspect.getfullargspec(TestUnion.__init__)
    assert spec.args == ["self", "a", "b", "c", "d"]
    assert spec.defaults == (None, None, None, None)

    obj = TestUnion(b"\x01\x02\x03\x04")
    assert obj.a == b"\x01"
    assert obj.b == 0x04030201
    assert obj.c == 0x0201
    assert obj.d == 0x01


def test_union_bool(TestUnion: type[Union]) -> None:
    assert bool(TestUnion(1, 2)) is True
    assert bool(TestUnion(1, 1)) is True
    assert bool(TestUnion()) is False
    assert bool(TestUnion(0, 0)) is False


def test_union_cmp(TestUnion: type[Union]) -> None:
    assert TestUnion(1) == TestUnion(1)
    assert TestUnion(1, 2) == TestUnion(1, 2)
    assert TestUnion(1, 2) != TestUnion(2, 3)
    assert TestUnion(b=2) == TestUnion(a=2)


def test_union_repr(TestUnion: type[Union]) -> None:
    obj = TestUnion(1, 2)
    assert repr(obj) == f"<{TestUnion.__name__} a=0x1 b=0x1>"


def test_union_eof(TestUnion: type[Union]) -> None:
    with pytest.raises(EOFError):
        TestUnion(b"")

    with pytest.raises(EOFError):
        TestUnion[2](b"\x01\x00\x00\x00")

    with pytest.raises(EOFError):
        TestUnion[None](b"\x01\x00\x00\x00\x02\x00\x00\x00")


def test_union_definition(cs: cstruct, compiled: bool) -> None:
    cdef = """
    union test {
        uint32 a;
        char   b[8];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert len(cs.test) == 8

    buf = b"zomgbeef"
    obj = cs.test(buf)

    assert obj.a == 0x676D6F7A
    assert obj.b == b"zomgbeef"
    assert list(obj.__dict__) == ["a", "b", "__dynamic_sizes__", "_buf", "_endian"]

    assert obj.dumps() == buf
    assert cs.test().dumps() == b"\x00\x00\x00\x00\x00\x00\x00\x00"


def test_union_definition_nested(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        char magic[4];
        union {
            struct {
                uint32 a;
                uint32 b;
            } a;
            struct {
                char   b[8];
            } b;
        } c;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert verify_compiled(cs.test.__lookup__["c"].type, compiled)

    assert len(cs.test) == 12

    buf = b"zomgholybeef"
    obj = cs.test(buf)

    assert isinstance(obj.c.a, UnionProxy)
    assert len(obj.c.a) == 8
    assert bytes(obj.c.a) == b"holybeef"
    assert repr(obj.c.a) == "<__anonymous_0__ a=0x796c6f68 b=0x66656562>"

    assert obj.magic == b"zomg"
    assert obj.c.a.a == 0x796C6F68
    assert obj.c.a.b == 0x66656562
    assert obj.c.b.b == b"holybeef"

    assert obj.dumps() == buf


def test_union_definition_anonymous(cs: cstruct, compiled: bool) -> None:
    cdef = """
    typedef struct test
    {
        union
        {
            uint32 a;
            struct
            {
                char b[3];
                char c;
            };
        };
        uint32 d;
    }
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert verify_compiled(cs.test.__fields__[0].type, compiled)

    buf = b"\x01\x01\x02\x02\x03\x03\x04\x04"
    obj = cs.test(buf)

    assert obj.a == 0x02020101
    assert obj.b == b"\x01\x01\x02"
    assert obj.c == b"\x02"
    assert obj.d == 0x04040303
    assert obj.dumps() == buf


def test_union_definition_dynamic(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct dynamic {
        uint8   size;
        char    data[size];
    };

    union test {
        dynamic a;
        uint64  b;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, False)

    buf = b"\x09aaaaaaaaa"
    obj = cs.test(buf)

    assert obj.a.size == 9
    assert obj.a.data == b"aaaaaaaaa"
    assert obj.b == 0x6161616161616109

    with pytest.raises(NotImplementedError, match="Writing dynamic unions is not yet supported"):
        obj.dumps()


def test_union_update(cs: cstruct, compiled: bool) -> None:
    cdef = """
    union test {
        uint8   a;
        uint16  b;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test()
    obj.a = 1
    assert obj.b == 1
    obj.b = 2
    assert obj.a == 2
    obj.b = 0xFFFF
    assert obj.a == 0xFF
    assert obj.dumps() == b"\xff\xff"


def test_union_nested_update(cs: cstruct) -> None:
    cdef = """
    struct test {
        char magic[4];
        union {
            struct {
                uint32 a;
                uint32 b;
            } a;
            struct {
                char   b[8];
            } b;
        } c;
    };
    """
    cs.load(cdef)

    obj = cs.test()
    obj.magic = b"1337"
    obj.c.b.b = b"ABCDEFGH"
    assert obj.c.a.a == 0x44434241
    assert obj.c.a.b == 0x48474645
    assert obj.dumps() == b"1337ABCDEFGH"

    obj.c.b.b = b"AAAAAAAA"
    assert obj.c.a.a == 0x41414141
    assert obj.dumps() == b"1337AAAAAAAA"


def test_union_anonymous_update(cs: cstruct) -> None:
    cdef = """
    typedef struct test
    {
        union {
            uint32 a;
            struct
            {
                char b[3];
                char c;
            };
        };
        uint32 d;
    }
    """
    cs.load(cdef)

    obj = cs.test()
    obj.a = 0x41414141
    assert obj.b == b"AAA"


def test_union_default(cs: cstruct, compiled: bool) -> None:
    cdef = """
    union test {
        uint32 a;
        char   b[8];
    };

    struct test_nested {
        test   t_union;
        test   t_union_array[2];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert cs.test() == cs.test.__default__()

    obj = cs.test()
    assert obj.a == 0
    assert obj.b == b"\x00\x00\x00\x00\x00\x00\x00\x00"

    assert obj.dumps() == b"\x00" * 8

    for name in obj.__members__:
        assert isinstance(getattr(obj, name), BaseType)

    assert cs.test_nested() == cs.test_nested.__default__()

    obj = cs.test_nested.__default__()
    assert obj.t_union == cs.test.__default__()
    assert obj.t_union_array == [cs.test.__default__(), cs.test.__default__()]

    assert obj.dumps() == b"\x00" * 24

    for name in obj.__members__:
        assert isinstance(getattr(obj, name), BaseType)


def test_union_default_dynamic(cs: cstruct, compiled: bool) -> None:
    """Initialization of a dynamic union is not yet supported."""
    cdef = """
    union test {
        uint8  x;
        char   b_n[];
        char   b_d[x];
    };

    struct test_nested {
        uint8  x;
        test   t_union_n[];
        test   t_union_d[x];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, False)

    obj = cs.test()
    assert obj.x == 0
    assert obj.b_n == b""
    assert obj.b_d == b""

    obj = cs.test_nested()
    assert obj.x == 0
    assert obj.t_union_n == []
    assert obj.t_union_d == []


def test_union_partial_initialization(cs: cstruct, compiled: bool) -> None:
    """Partial initialization of a union should fill in the rest with appropriate values."""
    cdef = """
    union test {
        uint8 a;
        uint8 b;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

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
    assert obj.b == 1
    assert str(obj) == "<test a=0x1 b=0x1>"

    obj = cs.test(a=1)
    assert obj.a == 1
    assert obj.b == 1
    assert str(obj) == "<test a=0x1 b=0x1>"

    obj = cs.test(b=1)
    assert obj.a == 1
    assert obj.b == 1
    assert str(obj) == "<test a=0x1 b=0x1>"

    obj = cs.test(a=1, b=2)
    assert obj.a == 1
    assert obj.b == 1
    assert str(obj) == "<test a=0x1 b=0x1>"

    obj = cs.test(b=2, a=1)
    assert obj.a == 2
    assert obj.b == 2
    assert str(obj) == "<test a=0x2 b=0x2>"


def test_union_partial_initialization_dynamic(cs: cstruct, compiled: bool) -> None:
    """Partial initialization of a dynamic union should fill in the rest with appropriate values."""
    cdef = """
    union test {
        uint8  x;
        char   b_n[];
        char   b_d[x];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, False)

    # Default initialization should already work
    cs.test()

    with pytest.raises(NotImplementedError, match="Initializing a dynamic union is not yet supported"):
        cs.test(1)

    with pytest.raises(NotImplementedError, match="Initializing a dynamic union is not yet supported"):
        cs.test(x=1)


def test_codegen_hashable(cs: cstruct) -> None:
    hashable_fields = [Field("a", cs.uint8), Field("b", cs.uint8)]
    unhashable_fields = [Field("a", cs.uint8[2]), Field("b", cs.uint8)]

    with pytest.raises(TypeError, match="unhashable type: 'uint8\\[2\\]'"):
        hash(unhashable_fields[0].type.__default__())

    assert hash(structure._generate_union__init__(hashable_fields).__code__)
    assert hash(structure._generate_union__init__(unhashable_fields).__code__)


def test_cdef_union(cs: cstruct, compiled: bool) -> None:
    cs.load("union Val { uint32 as_int; float as_float; };", compiled=compiled)

    assert verify_compiled(cs.Val, compiled)
    assert cs.Val.cdef() == dedent(
        """\
        union Val {
            uint32 as_int;
            float as_float;
        };"""
    )


def test_union_changing_endian(cs: cstruct, compiled: bool) -> None:
    cdef = """
    union test {
        uint32 a;
        char   b[8];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert len(cs.test) == 8
    assert cs.endian == "<"

    buf = b"zomgbeef"
    obj = cs.test(buf, endian=">")

    assert obj.a == 0x7A6F6D67
    assert obj.b == b"zomgbeef"

    assert obj.dumps(endian=">") == buf


UNION_DEF = """
enum Kind : uint16 {
    A = 1,
    B = 2,
};

struct pair {
    uint16  low;
    uint16  high;
};

union value {
    uint32      raw;
    pair        parts;
    Kind        kind;
    char        text[6];
    wchar       wide[3];
    uint8       bytes[6];
    uint24      small[2];
    struct {
        uint8   first;
        uint8   second;
    };
};

union unsupported {
    uint8   size;
    char    data[size];
};
"""


@pytest.mark.parametrize("endian", ["<", ">", "!", "="])
def test_compiled_union(endian: str) -> None:
    """Test that compiled unions read the same values as the interpreted version."""
    compiled = cstruct().load(UNION_DEF)
    interpreted = cstruct().load(UNION_DEF, compiled=False)

    assert compiled.value.__compiled__
    assert not compiled.unsupported.__compiled__

    for buf in (bytes(range(1, 7)), b"\x01\x00\x00\x00\x00\x00", b"\xff" * 6):
        obj = compiled.value(buf, endian=endian)
        expected = interpreted.value(buf, endian=endian)
        assert parsed_state(obj) == parsed_state(expected)
        assert list(obj.__dict__) == list(expected.__dict__)

        # Modifying the union rebuilds all values, like the interpreted version
        obj.parts.low = 0x4142
        expected.parts.low = 0x4142
        assert parsed_state(obj) == parsed_state(expected)

    # Arrays of unions read every entry with the compiled version
    buf = bytes(range(1, 13))
    assert parsed_state(compiled.value[2](buf)) == parsed_state(interpreted.value[2](buf))

    # The generated code was used, it would revert to the interpreted version on failure
    assert compiled.value.__compiled__


def test_compiled_union_source(cs: cstruct) -> None:
    """Test the exact source code that is generated for a union."""
    cdef = """
    union test {
        uint32  a;
        struct {
            uint16  b;
            uint16  c;
        } d;
    };
    """
    cs.load(cdef)

    # Every member is read from the bytes of the union, structures are proxied like Union._proxify
    expected = """
    def _read(cls, stream, *, context=None, endian):
        if cls is not _cls0 or _type1.__init__ is not _init0: return _union_read(cls, stream, context=context, endian=endian)
        buf = stream.read(4)
        if len(buf) != 4: raise EOFError(f"Read {len(buf)} bytes, but expected 4")
        obj = _object_new(cls)
        _data0 = _unpack_from0[endian](buf, 0)
        _object_setattr(obj, 'a', _type_call(_type0, _data0[0]))
        _data1 = _unpack_from1[endian](buf, 0)
        _object0 = _object_new(_type1)
        _object0.b = _type_call(_type2, _data1[0])
        _object0.c = _type_call(_type2, _data1[1])
        _object0.__dynamic_sizes__ = {}
        _object_setattr(obj, 'd', _object0)
        _object_setattr(obj, '__dynamic_sizes__', {})
        _object_setattr(obj, '_buf', buf)
        _object_setattr(obj, '_endian', endian)
        _nested0 = _getattr(obj, 'd')
        _object_setattr(obj, 'd', _UnionProxy(obj, 'd', _nested0))
        return obj
    """  # noqa: E501
    assert cs.test._read.__source__ == dedent(expected).strip()


def test_compiled_union_eof(cs: cstruct) -> None:
    """Test that a short read of a compiled union raises an error with the number of bytes read."""
    cs.load(UNION_DEF)

    for size in range(len(cs.value)):
        with pytest.raises(EOFError, match=f"^Read {size} bytes, but expected {len(cs.value)}$"):
            cs.value(bytes(range(1, size + 1)))


def test_compiled_union_generic() -> None:
    """Test the cases in which a compiled union uses the generic read method."""
    compiled = cstruct().load(UNION_DEF)
    interpreted = cstruct().load(UNION_DEF, compiled=False)
    buf = bytes(range(1, 7))

    # Subclasses use the generic method
    results = []
    for cs in (compiled, interpreted):

        class Subclass(cs.value):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                object.__setattr__(self, "initialized", True)

        obj = Subclass(buf)
        results.append((type(obj) is Subclass, hasattr(obj, "initialized"), parsed_state(obj)))

    assert results[0] == results[1]

    # Modifying a nested structure after compilation uses the generic method, like for inlined structures
    compiled.value(buf)
    compiled.pair.add_field("extra", compiled.uint8)
    interpreted.pair.add_field("extra", interpreted.uint8)
    assert parsed_state(compiled.value(buf)) == parsed_state(interpreted.value(buf))

    # Changing the union itself recompiles it
    compiled.value.add_field("tail", compiled.uint64)
    interpreted.value.add_field("tail", interpreted.uint64)
    assert compiled.value.__compiled__
    buf = bytes(range(1, 9))
    assert parsed_state(compiled.value(buf)) == parsed_state(interpreted.value(buf))

    # Changes that the compiler doesn't support revert to the generic method
    compiled.value.add_field("dynamic", compiled.char[None])
    assert not compiled.value.__compiled__
    assert compiled.value._read.__func__ is type(compiled.value)._read


def test_compiled_union_member_offset() -> None:
    """Test that a union with a member beyond its size isn't compiled or inlined."""
    cdef = """
    union test {
        uint16  a;
    };
    """
    cdef_outer = """
    struct outer {
        test    t;
        uint16  c;
    };
    """
    compiled = cstruct().load(cdef)
    interpreted = cstruct().load(cdef, compiled=False)

    # A member that doesn't fit in the union can't be read from the union's bytes
    for cs in (compiled, interpreted):
        cs.test.add_field("b", cs.uint16, offset=1)
        cs.load(cdef_outer)

    assert not compiled.test.__compiled__
    # The union isn't inlined in the outer structure, but read by its type
    read = "_value0 = values['t'] = _type0._read(stream, context=values, endian=endian)"
    assert read in source_lines(compiled.outer)

    for name in ("test", "outer"):
        messages = []
        for cs in (compiled, interpreted):
            with pytest.raises(EOFError) as exc:
                cs.resolve(name)(bytes(range(1, 5)))
            messages.append(str(exc.value))

        assert messages[0] == messages[1]
