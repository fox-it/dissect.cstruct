from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from dissect.cstruct.exceptions import ParserError
from dissect.cstruct.parser import TokenParser
from dissect.cstruct.types import BaseArray, Pointer, Structure
from tests.utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


def test_nested_structs(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct nest {
        struct {
            uint32 b;
        } a[4];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.nest, compiled)

    data = b"\x00\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00"
    obj = cs.nest(data)
    for i in range(4):
        assert obj.a[i].b == i

    assert cs.nest.fields["a"].type.__name__ == "__anonymous_0__[4]"
    assert cs.nest.fields["a"].type.type.__name__ == "__anonymous_0__"


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

    assert issubclass(cs.uuid_t, BaseArray)
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
    typedef struct {
        int32 len;
        char str[len];
    } sub;

    typedef struct {
        sub data[1];
    } test;
    """
    cs.load(cdef)

    assert cs.sub.dynamic
    assert cs.test.dynamic


def test_structure_names(cs: cstruct) -> None:
    cdef = """
    struct a {
        uint32 _;
    };

    struct {
        uint32 _;
    } b;

    struct {
        uint32 _;
    } c, d;

    typedef struct {
        uint32 _;
    } e;
    """
    cs.load(cdef)

    assert all(c in cs.typedefs for c in ("a", "b", "c", "d", "e"))

    assert cs.a.__name__ == "a"
    assert cs.b.__name__ == "b"
    assert cs.c.__name__ == "c"
    assert cs.d.__name__ == "c"
    assert cs.e.__name__ == "e"


def test_includes(cs: cstruct) -> None:
    cdef = """
    /* Standard libs */
    #include <stdint.h> // defines fixed data types: int8_t...
    /* user libs */
    #include "myLib.h"  // my own header

    typedef struct myStruct
    {
        char charVal[16];
    }
    """
    cs.load(cdef)

    assert cs.includes == ["<stdint.h>", "myLib.h"]
    assert cs.myStruct.__name__ == "myStruct"
    assert len(cs.myStruct.fields) == 1
    assert cs.myStruct.fields.get("charVal")


def test_typedef_pointer(cs: cstruct) -> None:
    cdef = """
    typedef struct _IMAGE_DATA_DIRECTORY {
        DWORD VirtualAddress;
        DWORD Size;
    } IMAGE_DATA_DIRECTORY, *PIMAGE_DATA_DIRECTORY;
    """
    cs.load(cdef)

    assert issubclass(cs._IMAGE_DATA_DIRECTORY, Structure)
    assert cs.IMAGE_DATA_DIRECTORY is cs._IMAGE_DATA_DIRECTORY
    assert issubclass(cs.PIMAGE_DATA_DIRECTORY, Pointer)
    assert cs.PIMAGE_DATA_DIRECTORY.type == cs._IMAGE_DATA_DIRECTORY
