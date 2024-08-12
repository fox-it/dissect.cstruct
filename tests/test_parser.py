from unittest.mock import Mock

import pytest

from dissect.cstruct import cstruct
from dissect.cstruct.exceptions import ParserError
from dissect.cstruct.parser import TokenParser
from dissect.cstruct.types import ArrayMetaType, Pointer


def test_nested_structs(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct nest {
        struct {
            uint32 b;
        } a[4];
    };
    """

    cs.load(cdef, compiled=compiled)
    data = b"\x00\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00"
    obj = cs.nest(data)
    for i in range(0, 4):
        assert obj.a[i].b == i


def test_preserve_comment_newlines() -> None:
    cdef = """
    // normal comment
    #define normal_anchor
    /*
     * Multi
     * line
     * comment
     */
    #define multi_anchor
    """
    data = TokenParser._remove_comments(cdef)

    mock_token = Mock()
    mock_token.match.string = data
    mock_token.match.start.return_value = data.index("#define normal_anchor")
    assert TokenParser._lineno(mock_token) == 3

    mock_token.match.start.return_value = data.index("#define multi_anchor")
    assert TokenParser._lineno(mock_token) == 9


def test_typedef_types(cs: cstruct) -> None:
    cdef = """
    typedef char uuid_t[16];
    typedef uint32 *ptr;

    struct test {
        uuid_t uuid;
        ptr ptr;
    };
    """
    cs.pointer = cs.uint8
    cs.load(cdef)

    assert isinstance(cs.uuid_t, ArrayMetaType)
    assert cs.uuid_t(b"\x01" * 16) == b"\x01" * 16

    assert issubclass(cs.ptr, Pointer)
    assert cs.ptr(b"\x01AAAA") == 1
    assert cs.ptr(b"\x01AAAA").dereference() == 0x41414141

    obj = cs.test(b"\x01" * 16 + b"\x11AAAA")
    assert obj.uuid == b"\x01" * 16
    assert obj.ptr.dereference() == 0x41414141

    with pytest.raises(ParserError, match="line 1: typedefs cannot have bitfields"):
        cs.load("""typedef uint8 with_bits : 4;""")


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
