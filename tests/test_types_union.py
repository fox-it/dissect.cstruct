import inspect

import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.types.base import Array
from dissect.cstruct.types.structure import Field, Union

from .utils import verify_compiled


@pytest.fixture
def TestUnion(cs: cstruct) -> type[Union]:
    return cs._make_union(
        "TestUnion",
        [Field("a", cs.uint32), Field("b", cs.uint16)],
    )


def test_union(TestUnion: type[Union]) -> None:
    assert issubclass(TestUnion, Union)
    assert len(TestUnion.fields) == 2
    assert TestUnion.fields["a"].name == "a"
    assert TestUnion.fields["b"].name == "b"

    assert TestUnion.size == 4
    assert TestUnion.alignment == 4

    spec = inspect.getfullargspec(TestUnion.__init__)
    assert spec.args == ["self", "a", "b"]
    assert spec.defaults == (None, None)

    obj = TestUnion(1, 2)
    assert isinstance(obj, TestUnion)
    assert obj.a == 1
    assert obj.b == 2
    assert len(obj) == 4

    obj = TestUnion(a=1)
    assert obj.a == 1
    assert obj.b is None
    assert len(obj) == 4

    assert hash((obj.a, obj.b)) == hash(obj)


def test_union_read(TestUnion: type[Union]) -> None:
    obj = TestUnion(b"\x01\x00\x00\x00")

    assert isinstance(obj, TestUnion)
    assert obj.a == 1
    assert obj.b == 1


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


def test_union_array_read(TestUnion: type[Union]) -> None:
    TestUnionArray = TestUnion[2]

    assert issubclass(TestUnionArray, Array)
    assert TestUnionArray.num_entries == 2
    assert TestUnionArray.type == TestUnion

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

    assert len(TestUnion.fields) == len(TestUnion.lookup) == 1
    assert len(TestUnion) == 1
    spec = inspect.getfullargspec(TestUnion.__init__)
    assert spec.args == ["self", "a"]
    assert spec.defaults == (None,)

    TestUnion.add_field("b", cs.uint32)

    assert len(TestUnion.fields) == len(TestUnion.lookup) == 2
    assert len(TestUnion) == 4
    spec = inspect.getfullargspec(TestUnion.__init__)
    assert spec.args == ["self", "a", "b"]
    assert spec.defaults == (None, None)

    with TestUnion.start_update():
        TestUnion.add_field("c", cs.uint16)
        TestUnion.add_field("d", cs.uint8)

    assert len(TestUnion.fields) == len(TestUnion.lookup) == 4
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
    assert repr(obj) == f"<{TestUnion.__name__} a=0x1 b=0x2>"


def test_union_eof(TestUnion: type[Union]) -> None:
    with pytest.raises(EOFError):
        TestUnion(b"")

    with pytest.raises(EOFError):
        TestUnion[2](b"\x01\x00\x00\x00")

    with pytest.raises(EOFError):
        TestUnion[None](b"\x01\x00\x00\x00\x02\x00\x00\x00")


def test_union_definition(cs: cstruct) -> None:
    cdef = """
    union test {
        uint32 a;
        char   b[8];
    };
    """
    cs.load(cdef, compiled=False)

    assert len(cs.test) == 8

    buf = b"zomgbeef"
    obj = cs.test(buf)

    assert obj.a == 0x676D6F7A
    assert obj.b == b"zomgbeef"

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

    assert len(cs.test) == 12

    buf = b"zomgholybeef"
    obj = cs.test(buf)

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

    buf = b"\x01\x01\x02\x02\x03\x03\x04\x04"
    obj = cs.test(buf)

    assert obj.a == 0x02020101
    assert obj.b == b"\x01\x01\x02"
    assert obj.c == b"\x02"
    assert obj.d == 0x04040303
    assert obj.dumps() == buf


def test_union_definition_dynamic(cs: cstruct) -> None:
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
    cs.load(cdef, compiled=False)

    buf = b"\x09aaaaaaaaa"
    obj = cs.test(buf)

    assert obj.a.size == 9
    assert obj.a.data == b"aaaaaaaaa"
    assert obj.b == 0x6161616161616109


def test_union_update(cs: cstruct) -> None:
    cdef = """
    union test {
        uint8   a;
        uint16  b;
    };
    """
    cs.load(cdef)

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
