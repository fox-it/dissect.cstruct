from __future__ import annotations

import pytest

from dissect.cstruct import cstruct
from dissect.cstruct.exception import ParserError, ResolveError
from dissect.cstruct.lexer import tokenize
from dissect.cstruct.parser import CStyleParser
from dissect.cstruct.types import BaseArray, Pointer, Structure
from tests.utils import verify_compiled


def test_struct(cs: cstruct, compiled: bool) -> None:
    """Test parsing of a simple struct."""
    cdef = """
    struct test {
        uint8  a;
        uint16 b;
    };

    struct test1 {
        uint8  a;
    } test2, *test3;

    struct {
        uint32 _;
    } b, c, **d;
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert cs.resolve("test") is cs.test
    assert cs.resolve("test1") is cs.test1

    # test2, test3, b, c and d are variable names, so they should be silently ignored
    for name in ("test2", "test3", "b", "c", "d"):
        with pytest.raises(ResolveError, match=f"Unknown type {name}"):
            cs.resolve(name)


def test_nested_structs(cs: cstruct, compiled: bool) -> None:
    """Test parsing of nested structs, including anonymous ones."""
    cdef = """
    struct nest {
        struct {
            uint32 b;
        } a[4];
    };

    struct also_nest {
        struct named {
            uint32 c;
        } d;
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

    assert cs.also_nest.fields["d"].type == cs.named


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

    tokens = tokenize(cdef)

    # Verify that comment removal preserves line numbers
    # by checking that the anchors appear on the correct lines
    for t in tokens:
        if t.value == "normal_anchor":
            assert t.line == 3
        if t.value == "multi_anchor":
            assert t.line == 9


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


def test_struct_names(cs: cstruct) -> None:
    cdef = """
    struct a {
        uint32 _;
    };

    typedef struct {
        uint32 _;
    } b;

    typedef struct c {
        uint32 _;
    } d, e;
    """
    cs.load(cdef)

    assert all(c in cs.typedefs for c in ("a", "b", "c", "d", "e"))

    assert cs.a.__name__ == "a"
    # For convenience, unnamed structs get the same name as their typedef if they have one
    assert cs.b.__name__ == "b"
    # These all refer to the same underlying struct
    assert cs.c.__name__ == "c"
    assert cs.d.__name__ == "c"
    assert cs.e.__name__ == "c"


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


def test_typedef_enum(cs: cstruct) -> None:
    cdef = """
    typedef enum {
        VAL1 = 1,
        VAL2 = 2,
        VAL3 = 4
    } test_enum;
    """
    cs.load(cdef)

    assert cs.test_enum.VAL1 == 1
    assert cs.test_enum.VAL2 == 2
    assert cs.test_enum.VAL3 == 4


def test_enum_flag_digit_member_name(cs: cstruct) -> None:
    # For historical reasons, we allow enum/flag member names to start with a digit, e.g. `32BIT`
    cdef = """
    enum test_enum : uint8 {
        32BIT = 1,
        64BIT = 2
    };

    flag test_flag : uint8 {
        32BIT = 1,
        64BIT = 2
    };
    """
    cs.load(cdef)

    assert cs.test_enum["32BIT"] == 1
    assert cs.test_enum["64BIT"] == 2
    assert cs.test_flag["32BIT"] == 1
    assert cs.test_flag["64BIT"] == 2


def test_define(cs: cstruct) -> None:
    cdef = """
    #define CONST 42
    #define EXPR (1 + 2 * 3)
    #define RAW somevalue
    #define STR "hello"
    #define BYTES b"world"
    #define NULLRAW ADCRYPT\00
    #define NULLSTR "ADCRYPT\00"
    #define NULLBYTES b"ADCRYPT\00"
    #define ARBITRARYBYTES b"\x00\x01\x02"
    #define MULTILINE (1 + \
                        2 + \
                        3)
    #define QUOTES "\'\"a'b\""
    #define ESCAPE "\\'\\"a'b\\"\\n"
    #define BYTES_ESCAPE b"`\\n"
    #define FUNC(x) ( x == 0 )
    #define TERNARY(x) ( x ? 1 : 0 )
    """
    cs.load(cdef)

    assert cs.consts["CONST"] == 42
    assert cs.consts["EXPR"] == 7
    assert cs.consts["RAW"] == "somevalue"
    assert cs.consts["STR"] == "hello"
    assert cs.consts["BYTES"] == b"world"
    assert cs.consts["NULLRAW"] == "ADCRYPT\00"
    assert cs.consts["NULLSTR"] == "ADCRYPT\00"
    assert cs.consts["NULLBYTES"] == b"ADCRYPT\00"
    assert cs.consts["ARBITRARYBYTES"] == b"\x00\x01\x02"
    assert cs.consts["MULTILINE"] == 6
    assert cs.consts["QUOTES"] == "'\"a'b\""
    assert cs.consts["ESCAPE"] == "'\"a'b\"\n"
    assert cs.consts["BYTES_ESCAPE"] == b"`\n"
    # We don't evaluate function-like macros yet, so they should be stored as their raw string representation
    assert cs.consts["FUNC"] == "(x) ( x == 0 )"
    assert cs.consts["TERNARY"] == "(x) ( x ? 1 : 0 )"


def test_define_flag_value(cs: cstruct) -> None:
    cdef = """
    flag test {
        VAL1 = 1,
        VAL2 = 2,
        VAL3 = 4
    };

    #define FLAG_VAL1 test.VAL1
    #define FLAG_VAL3 test.VAL1 | test.VAL2
    """
    cs.load(cdef)

    assert cs.consts["FLAG_VAL1"] == 1
    assert cs.consts["FLAG_VAL3"] == 3


def test_undef(cs: cstruct) -> None:
    cdef = """
    #define MY_CONST 42
    #undef MY_CONST
    """
    cs.load(cdef)

    assert "MY_CONST" not in cs.consts

    with pytest.raises(ParserError, match="line 1: constant 'MY_CONST' not defined"):
        cs.load("#undef MY_CONST")  # This should raise an error since MY_CONST is not defined


def test_conditional_ifdef(cs: cstruct) -> None:
    cdef = """
    #define MY_CONST 42

    #ifdef MY_CONST
    struct test {
        uint32 a;
    };
    #endif
    """
    cs.load(cdef)

    assert "test" in cs.typedefs


def test_conditional_ifndef(cs: cstruct) -> None:
    cdef = """
    #ifndef MYVAR
        #define MYVAR  (1)
    #endif
    """
    cs.load(cdef)

    assert "MYVAR" in cs.consts
    assert cs.consts["MYVAR"] == 1


def test_conditional_ifndef_guard(cs: cstruct) -> None:
    cdef = """
    /* Define Guard */
    #ifndef __MYGUARD
    #define __MYGUARD

    typedef struct myStruct
    {
        char   charVal[16];
    }
    #endif // __MYGUARD
    """
    cs.load(cdef)

    assert "__MYGUARD" in cs.consts
    assert "myStruct" in cs.typedefs


def test_conditional_nested() -> None:
    cdef = """
    #ifndef MYSWITCH1
        #define MYVAR1 (1)
    #else
        #ifdef MYSWITCH2
            #define MYVAR1 (2)
        #else
            #define MYVAR1 (3)
        #endif
    #endif
    """
    cs = cstruct().load(cdef)

    assert "MYVAR1" in cs.consts
    assert cs.consts["MYVAR1"] == 1

    cs = cstruct().load("#define MYSWITCH1")

    assert "MYSWITCH1" in cs.consts

    cs.load(cdef)

    assert "MYVAR1" in cs.consts
    assert cs.consts["MYVAR1"] == 3


def test_conditional_in_struct(cs: cstruct) -> None:
    cdef = """
    struct t_bitfield {
        union {
            struct {
                uint32_t bit0:1;
                uint32_t bit1:1;
                #ifdef MYSWT
                uint32_t bit2:1;
                #endif
            } fval;
            uint32_t bits;
        };
    };
    """
    cs.load(cdef)

    assert "t_bitfield" in cs.typedefs
    assert "fval" in cs.t_bitfield.fields
    assert "bit0" in cs.t_bitfield.fields["fval"].type.fields
    assert "bit1" in cs.t_bitfield.fields["fval"].type.fields
    assert "bit2" not in cs.t_bitfield.fields["fval"].type.fields


def test_conditional_parsing_error(cs: cstruct) -> None:
    cdef = """
    #ifndef __HELP
    #define __HELP
    #endif
    struct test {
        uint32 a;
    };
    #endif
    """
    with pytest.raises(ParserError, match="line 8: #endif without matching #ifdef/#ifndef"):
        cs.load(cdef)

    cdef = """
    #ifndef __HELP
    #define __HELP
    struct test {
        uint32 a;
    };
    """
    with pytest.raises(ParserError, match="line 2: unclosed conditional statement"):
        cs.load(cdef)


def test_multiline_define(cs: cstruct) -> None:
    """Test parsing of multi-line ``#define`` directives."""
    cdef = """
    #define MULTILINE_DEF (1 + \\
                          2 + \\
                          3)
    """
    cs.load(cdef)

    assert "MULTILINE_DEF" in cs.consts
    assert cs.consts["MULTILINE_DEF"] == 6


def test_multiple_declarators(cs: cstruct) -> None:
    """Test parsing of multiple declarators in a single struct field declaration."""
    cdef = """
    struct test {
        uint32 a, b, c;
        struct { uint8 _; } d, e;
    };
    """
    cs.load(cdef)

    assert "test" in cs.typedefs
    assert all(field in cs.test.fields for field in ("a", "b", "c", "d", "e"))
    assert cs.test.fields["a"].type == cs.uint32
    assert cs.test.fields["b"].type == cs.uint32
    assert cs.test.fields["c"].type == cs.uint32
    assert cs.test.fields["d"].type.__name__ == "__anonymous_0__"
    assert cs.test.fields["e"].type is cs.test.fields["d"].type


def test_config_flags(cs: cstruct) -> None:
    """Test that we parse configuration flag directives correctly."""
    cdef = """
    #[a, b, c]
    """
    parser = CStyleParser(cs)
    parser.parse(cdef)

    assert parser._flags == ["a", "b", "c"]


def test_preprocessor_in_struct_body(cs: cstruct) -> None:
    """Test #define, #ifdef, #ifndef, #else, and #undef inside struct bodies."""
    cdef = """
    struct test {
        #define VERSION 2

        uint32 always_present;

        #ifdef VERSION
        uint16 version;
        #endif

        #ifndef EXTRA
        uint8 basic;
        #else
        uint32 extra;
        #endif

        #define EXTRA
        #ifdef EXTRA
        uint64 bonus;
        #endif

        #undef EXTRA
        #ifdef EXTRA
        uint32 should_not_exist;
        #endif
    };
    """
    cs.load(cdef)

    assert cs.consts["VERSION"] == 2
    assert "always_present" in cs.test.fields
    assert "version" in cs.test.fields
    assert "basic" in cs.test.fields
    assert "extra" not in cs.test.fields
    assert "bonus" in cs.test.fields
    assert "should_not_exist" not in cs.test.fields

    assert cs.test.fields["always_present"].type == cs.uint32
    assert cs.test.fields["version"].type == cs.uint16
    assert cs.test.fields["basic"].type == cs.uint8
    assert cs.test.fields["bonus"].type == cs.uint64


def test_preprocessor_define_from_enum_in_struct() -> None:
    """Test #define referencing enum values used for conditional fields and array sizes."""
    cdef = """
    enum protocol : uint8 {
        TCP = 6,
        UDP = 17
    };

    #define PROTO protocol.TCP
    #define HAS_OPTIONS 1
    #define HEADER_LEN 4

    struct packet {
        uint8 type;

        #ifdef HAS_OPTIONS
        uint32 options[HEADER_LEN];

        enum flags : uint16 {
            SYN = 1,
            ACK = 2,
            FIN = 4
        };

        #define FLAG_SYNACK flags.SYN | flags.ACK
        #define FLAG_BIG flags.PSH | YOMOMMA

        #ifndef NO_PAYLOAD
        #ifdef HAS_OPTIONS
        uint8 payload[20];
        #else
        uint8 payload[4];
        #endif
        #endif

        #endif

        uint16 checksum;
    };
    """
    cs = cstruct()
    cs.load(cdef)

    assert cs.consts["PROTO"] == 6
    assert cs.consts["FLAG_SYNACK"] == 3
    assert cs.consts["FLAG_BIG"] == "flags.PSH | YOMOMMA"

    assert "type" in cs.packet.fields
    assert "options" in cs.packet.fields
    assert "payload" in cs.packet.fields
    assert "checksum" in cs.packet.fields

    assert cs.packet.fields["options"].type.num_entries == 4
    assert cs.packet.fields["payload"].type.num_entries == 20
