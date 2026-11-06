from __future__ import annotations

import io
from operator import itemgetter
from textwrap import dedent
from typing import TYPE_CHECKING, BinaryIO
from unittest.mock import Mock, patch

import pytest

from dissect.cstruct import compiler
from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.exception import ExpressionParserError
from dissect.cstruct.expression import Expression
from dissect.cstruct.types import Packed
from dissect.cstruct.types.structure import Field
from tests.util import parsed_state, source_lines, verify_compiled

if TYPE_CHECKING:
    from collections.abc import Iterator

    from dissect.cstruct.cstruct import Endianness
    from dissect.cstruct.types.base import BaseType
    from dissect.cstruct.types.enum import Enum


def f(field_type: type[BaseType], offset: int | None = 0, name: str = "") -> Field:
    return Field(name, field_type, offset=offset)


def read_generator(cs: cstruct, fields: list[Field]) -> compiler._ReadSourceGenerator:
    return compiler._ReadSourceGenerator(cs._make_struct("test", []), fields)


def write_generator(cs: cstruct, fields: list[Field]) -> compiler._WriteSourceGenerator:
    return compiler._WriteSourceGenerator(cs._make_struct("test", []), fields)


def strip_fields(info: Iterator[tuple[Field, int, str]]) -> list[tuple[int, str]]:
    return list(map(itemgetter(1, 2), info))


def mkfmt(info: Iterator[tuple[Field, int, str]]) -> str:
    return "".join(f"{count}{char}" for _, count, char in info)


@pytest.fixture
def TestEnum(cs: cstruct) -> type[Enum]:
    return cs._make_enum("Test", cs.uint8, {"a": 1})


def test_generate_struct_info(cs: cstruct, TestEnum: type[Enum]) -> None:
    fields = [f(cs.uint8), f(cs.int16), f(cs.uint32), f(cs.int64)]
    fmt = strip_fields(compiler._generate_struct_info(fields))
    assert fmt == [(1, "B"), (1, "h"), (1, "I"), (1, "q")]

    fields = [f(cs.uint8[4]), f(cs.int16[4]), f(cs.uint32[4]), f(cs.int64[4])]
    fmt = strip_fields(compiler._generate_struct_info(fields))
    assert fmt == [(4, "B"), (4, "h"), (4, "I"), (4, "q")]

    fields = [f(cs.char), f(cs.wchar), f(cs.uint24), f(cs.int128)]
    fmt = strip_fields(compiler._generate_struct_info(fields))
    assert fmt == [(1, "x"), (2, "x"), (3, "x"), (16, "x")]

    fields = [f(cs.char[2]), f(cs.wchar[2]), f(cs.uint24[2]), f(cs.int128[2])]
    fmt = strip_fields(compiler._generate_struct_info(fields))
    assert fmt == [(2, "x"), (4, "x"), (6, "x"), (32, "x")]

    fields = [f(cs.char), f(cs.char[2]), f(cs.char)]
    fmt = strip_fields(compiler._generate_struct_info(fields))
    assert fmt == [(1, "x"), (2, "x"), (1, "x")]

    fields = [f(cs.uint8), f(cs.void), f(cs.int16)]
    fmt = strip_fields(compiler._generate_struct_info(fields))
    assert fmt == [(1, "B"), (1, "h")]

    fields = [f(cs.uint8), f(cs.uint16), f(cs.char[0])]
    fmt = strip_fields(compiler._generate_struct_info(fields))
    assert fmt == [(1, "B"), (1, "H"), (0, "x")]

    cs.pointer = cs.uint64
    TestPointer = cs._make_pointer(TestEnum)
    fields = [f(TestEnum), f(TestPointer)]
    fmt = strip_fields(compiler._generate_struct_info(fields))
    assert fmt == [(1, "B"), (1, "Q")]


def test_generate_struct_info_offsets(cs: cstruct) -> None:
    fields = [f(cs.uint8, 0), f(cs.uint8, 4), f(cs.uint8[2], 5), f(cs.uint8, 8)]
    fmt = strip_fields(compiler._generate_struct_info(fields))
    assert fmt == [(1, "B"), (3, "x"), (1, "B"), (2, "B"), (1, "x"), (1, "B")]

    # Different starting offsets are handled in the field reading loop of the compilation
    fields = [f(cs.uint8, 4)]
    fmt = strip_fields(compiler._generate_struct_info(fields))
    assert fmt == [(1, "B")]


@pytest.mark.parametrize(
    ("fields", "fmt"),
    [
        ([(1, "B"), (3, "B")], "4B"),
        ([(1, "B"), (3, "B"), (2, "H")], "4B2H"),
        ([(1, "B"), (0, "x")], "B"),
        ([(1, "B"), (0, "x"), (2, "H")], "B2H"),
        ([(1, "B"), (0, "x"), (2, "x"), (1, "H")], "B2xH"),
        ([(0, "x"), (1, "B"), (1, "B")], "2B"),
        ([(1, "B"), (0, "H"), (1, "B")], "BB"),
        ([(2, "s"), (3, "s"), (1, "B")], "2s3sB"),
        ([], ""),
    ],
)
def test_optimize_struct_fmt(fields: list[tuple], fmt: str) -> None:
    assert compiler._optimize_struct_fmt(fields) == fmt


def test_generate_packed_read(cs: cstruct) -> None:
    fields = [
        f(cs.uint8, name="a"),
        f(cs.int16, name="b"),
        f(cs.uint32, name="c"),
        f(cs.int64, name="d"),
    ]
    code = next(read_generator(cs, fields)._generate_packed_source(fields))

    expected = """
    buf = stream.read(15)
    if len(buf) != 15: raise EOFError(f"Read {len(buf)} bytes, but expected 15")
    data = _unpack0[endian](buf)
    _value0 = _type_call(_type0, data[0])
    _value1 = _type_call(_type1, data[1])
    _value2 = _type_call(_type2, data[2])
    _value3 = _type_call(_type3, data[3])
    """

    assert code == dedent(expected)


def test_generate_packed_read_array(cs: cstruct) -> None:
    fields = [
        f(cs.uint8[2], name="a"),
        f(cs.int16[3], name="b"),
        f(cs.uint32[4], name="c"),
        f(cs.int64[5], name="d"),
    ]
    code = next(read_generator(cs, fields)._generate_packed_source(fields))

    expected = """
    buf = stream.read(64)
    if len(buf) != 64: raise EOFError(f"Read {len(buf)} bytes, but expected 64")
    data = _unpack0[endian](buf)
    _value0 = _type_call(_type0, list(map(_type_call, _repeat(_type1), data[0:2])))
    _value1 = _type_call(_type2, list(map(_type_call, _repeat(_type3), data[2:5])))
    _value2 = _type_call(_type4, list(map(_type_call, _repeat(_type5), data[5:9])))
    _value3 = _type_call(_type6, list(map(_type_call, _repeat(_type7), data[9:14])))
    """

    assert code == dedent(expected)


def test_generate_packed_read_byte_types(cs: cstruct) -> None:
    fields = [
        f(cs.char, name="a"),
        f(cs.char[2], name="b"),
        f(cs.wchar, name="c"),
        f(cs.wchar[2], name="d"),
        f(cs.int24, name="e"),
        f(cs.int24[2], name="f"),
    ]
    code = next(read_generator(cs, fields)._generate_packed_source(fields))

    expected = """
    buf = stream.read(18)
    if len(buf) != 18: raise EOFError(f"Read {len(buf)} bytes, but expected 18")
    _value0 = _type_call(_type0, buf[0:1])
    _value1 = _type_call(_type1, buf[1:3])
    _value2 = _type_call(_type2, str(buf[3:5], _encoding0[endian], 'surrogatepass'))
    _value3 = _type_call(_type3, str(buf[5:9], _encoding0[endian], 'surrogatepass'))
    _value4 = _type_call(_type4, _int_from_bytes(buf[9:12], _byteorder[endian], signed=True))
    _array_buf = buf[12:18]
    """
    expected = dedent(expected) + (
        "_value5 = _type_call(_type5, list(map(_type_call, _repeat(_type4), "
        "[_int_from_bytes(_array_buf[i:i + 3], _byteorder[endian], signed=True) for i in range(0, 6, 3)])))\n"
    )

    assert code == expected


def test_generate_packed_read_composite_types(cs: cstruct, TestEnum: type[Enum]) -> None:
    cs.pointer = cs.uint64
    TestPointer = cs._make_pointer(TestEnum)

    fields = [
        f(TestEnum, name="a"),
        f(TestPointer, name="b"),
        f(cs.void),
        f(TestEnum[2], name="c"),
    ]
    code = next(read_generator(cs, fields)._generate_packed_source(fields))

    expected = """
    buf = stream.read(11)
    if len(buf) != 11: raise EOFError(f"Read {len(buf)} bytes, but expected 11")
    data = _unpack0[endian](buf)
    _enum_value = data[0]
    if (_member := _type0._value2member_map_.get(_enum_value)) is None: _member = _type_call(_type0, _enum_value)
    _value0 = _member
    values = {'a': _value0}
    _value1 = values['b'] = _type1.__new__(_type1, data[1], stream, context=values, endian=endian)
    _value2 = values['c'] = _type_call(_type2, list(map(_type_call, _repeat(_type0), data[2:4])))
    """

    assert code == dedent(expected)


def test_generate_packed_read_offsets(cs: cstruct) -> None:
    fields = [
        f(cs.uint8, name="a"),
        f(cs.uint8, 8, name="b"),
    ]
    code = next(read_generator(cs, fields)._generate_packed_source(fields))

    expected = """
    buf = stream.read(9)
    if len(buf) != 9: raise EOFError(f"Read {len(buf)} bytes, but expected 9")
    data = _unpack0[endian](buf)
    _value0 = _type_call(_type0, data[0])
    _value1 = _type_call(_type0, data[1])
    """

    assert code == dedent(expected)


def test_generate_structure_read(cs: cstruct) -> None:
    field = Field("a", Mock(__alignment__=None, __dynamic__=True, __anonymous__=False))
    code = next(read_generator(cs, [field])._generate_field_source(field))

    expected = """
    values = {}
    _offset = stream.tell()
    _value0 = values['a'] = _type0._read(stream, context=values, endian=endian)
    sizes['a'] = stream.tell() - _offset
    """

    assert code == dedent(expected)


def test_generate_structure_read_anonymous(cs: cstruct) -> None:
    field = Field("a", Mock(__alignment__=None, __dynamic__=True, __anonymous__=True))
    code = next(read_generator(cs, [field])._generate_field_source(field))

    expected = """
    values = {}
    _offset = stream.tell()
    _value0 = values['a'] = _type0._read(stream, context=values, endian=endian)
    sizes['a'] = stream.tell() - _offset
    """

    assert code == dedent(expected)


def test_generate_array_read(cs: cstruct) -> None:
    field = Field("a", Mock(__alignment__=None, __dynamic__=True))
    code = next(read_generator(cs, [field])._generate_field_source(field))

    expected = """
    values = {}
    _offset = stream.tell()
    _value0 = values['a'] = _type0._read(stream, context=values, endian=endian)
    sizes['a'] = stream.tell() - _offset
    """

    assert code == dedent(expected)


def test_generate_bits_read(cs: cstruct, TestEnum: type[Enum]) -> None:
    field = Field("a", cs.int8, 2)
    code = next(read_generator(cs, [field])._generate_bits_source(field))

    expected = """
    _bit_buffer = _type0._read(stream, endian=endian)
    if endian == "<": _bit_value = _bit_buffer & 3; _bit_buffer >>= 2
    else: _bit_value = (_bit_buffer >> 6) & 3
    _value0 = _type_call(_type0, _bit_value)
    """

    assert code == dedent(expected)

    field = Field("b", TestEnum, 2)
    code = next(read_generator(cs, [field])._generate_bits_source(field))

    expected = """
    _bit_buffer = _type0._read(stream, endian=endian)
    if endian == "<": _bit_value = _bit_buffer & 3; _bit_buffer >>= 2
    else: _bit_value = (_bit_buffer >> 6) & 3
    if (_member := _type1._value2member_map_.get(_bit_value)) is None: _member = _type_call(_type1, _bit_value)
    _value0 = _member
    """

    assert code == dedent(expected)


@pytest.mark.parametrize("other_type", ["int8", "uint64"])
def test_generate_fields_dynamic_after_bitfield(cs: cstruct, TestEnum: Enum, other_type: str) -> None:
    _type = getattr(cs, other_type)

    fields = [
        Field("size", cs.uint16, offset=0),
        Field("a", TestEnum, 4, offset=2),
        Field("b", _type, 4),
        Field("c", cs.char[Expression("size")], offset=3),
    ]

    output = "\n".join(read_generator(cs, fields)._generate_fields_source())

    shift = _type.__size__ * 8 - 4
    expected = f"""
    buf = stream.read(2)
    if len(buf) != 2: raise EOFError(f"Read {{len(buf)}} bytes, but expected 2")
    data = _unpack0[endian](buf)
    _value0 = _type_call(_type0, data[0])


    _bit_buffer = _type1._read(stream, endian=endian)
    if endian == "<": _bit_value = _bit_buffer & 15; _bit_buffer >>= 4
    else: _bit_value = (_bit_buffer >> 4) & 15
    if (_member := _type2._value2member_map_.get(_bit_value)) is None: _member = _type_call(_type2, _bit_value)
    _value1 = _member


    _bit_buffer = _type3._read(stream, endian=endian)
    if endian == "<": _bit_value = _bit_buffer & 15; _bit_buffer >>= 4
    else: _bit_value = (_bit_buffer >> {shift}) & 15
    _value2 = _type_call(_type3, _bit_value)

    stream.seek(start + 3)

    values = {{'size': _value0, 'a': _value1, 'b': _value2}}
    _count = max(0, int(_value0))
    _offset = stream.tell()
    _value3 = values['c'] = _type_call(_type4, _type5._read_array(stream, _count, context=values, endian=endian))
    sizes['c'] = stream.tell() - _offset
    """

    assert output.strip() == dedent(expected).strip()


@pytest.mark.parametrize("other_type", ["int8", "uint64"])
def test_generate_fields_dynamic_before_bitfield(cs: cstruct, TestEnum: Enum, other_type: str) -> None:
    _type = getattr(cs, other_type)

    fields = [
        Field("size", cs.uint16, offset=0),
        Field("a", _type, 4, offset=2),
        Field("b", TestEnum, 4),
        Field("c", cs.char[Expression("size")], offset=3),
    ]

    output = "\n".join(read_generator(cs, fields)._generate_fields_source())

    shift = _type.__size__ * 8 - 4
    expected = f"""
    buf = stream.read(2)
    if len(buf) != 2: raise EOFError(f"Read {{len(buf)}} bytes, but expected 2")
    data = _unpack0[endian](buf)
    _value0 = _type_call(_type0, data[0])


    _bit_buffer = _type1._read(stream, endian=endian)
    if endian == "<": _bit_value = _bit_buffer & 15; _bit_buffer >>= 4
    else: _bit_value = (_bit_buffer >> {shift}) & 15
    _value1 = _type_call(_type1, _bit_value)


    _bit_buffer = _type2._read(stream, endian=endian)
    if endian == "<": _bit_value = _bit_buffer & 15; _bit_buffer >>= 4
    else: _bit_value = (_bit_buffer >> 4) & 15
    if (_member := _type3._value2member_map_.get(_bit_value)) is None: _member = _type_call(_type3, _bit_value)
    _value2 = _member

    stream.seek(start + 3)

    values = {{'size': _value0, 'a': _value1, 'b': _value2}}
    _count = max(0, int(_value0))
    _offset = stream.tell()
    _value3 = values['c'] = _type_call(_type4, _type5._read_array(stream, _count, context=values, endian=endian))
    sizes['c'] = stream.tell() - _offset
    """

    assert output.strip() == dedent(expected).strip()


def test_compiled_dynamic_array_sizes() -> None:
    """Test that compiled structures calculate the sizes of dynamic arrays like the interpreted version."""
    cdef = """
    #define HDR 2
    enum Kind : uint8 { A = 1 };
    struct inner { uint8 size; };
    struct test {
        uint8   n;
        Kind    kind;
        inner   hdr;
        char    a[n];
        wchar   b[n - HDR];
        uint16  c[kind * 2];
        uint8   d[hdr.size];
        inner   e[n + sizeof(inner)];
        char    f[EOF];
    };
    struct unknown {
        uint8   n;
        char    a[missing];
    };
    """
    compiled = cstruct().load(cdef)
    interpreted = cstruct().load(cdef, compiled=False)

    # Integer fields read before are used directly, everything else is resolved like the interpreted version
    # The array with the size EOF is read by its type
    lines = source_lines(compiled.test)
    assert [line for line in lines if line.startswith("_count = ") or "._read" in line] == [
        "_count = max(0, int(_value0))",
        "_value3 = values['a'] = _type_call(_type3, _type4._read_array(stream, _count, context=values, endian=endian))",
        "_count = max(0, (int(_value0) - _identifier(cs, values, 'HDR')))",
        "_value4 = values['b'] = _type_call(_type5, _type6._read_array(stream, _count, context=values, endian=endian))",
        "_count = max(0, (int(_value1) * 2))",
        "_value5 = values['c'] = _type_call(_type7, _type8._read_array(stream, _count, context=values, endian=endian))",
        "_count = max(0, _identifier(cs, values, 'hdr.size'))",
        "_value6 = values['d'] = _type_call(_type9, _type0._read_array(stream, _count, context=values, endian=endian))",
        "_count = max(0, (int(_value0) + _sizeof(cs, 'inner')))",
        "_value7 = values['e'] = _type_call(_type10, _type2._read_array("
        "stream, _count, context=values, endian=endian))",
        "_value8 = values['f'] = _type11._read(stream, context=values, endian=endian)",
    ]

    buf = bytes([4, 1, 2]) + bytes(range(65, 120))
    assert parsed_state(compiled.test(buf)) == parsed_state(interpreted.test(buf))

    messages = []
    for cs in (compiled, interpreted):
        with pytest.raises(ExpressionParserError) as excinfo:
            cs.unknown(buf)
        messages.append(str(excinfo.value))
    assert messages[0] == messages[1]


INLINE_DEF = """
enum Kind : uint16 {
    A = 1,
    B = 2,
};

struct reference {
    uint32  low;
    uint16  high;
    uint16  sequence;
};

struct inner {
    reference   ref;
    char        name[4];
    Kind        kind;
};

struct header {
    uint8       type;
    inner       a;
    union {
        struct {
            uint32  length;
            uint16  offset;
        } resident;
        struct {
            uint64  vcn;
            uint8   reserved[3];
        } nonresident;
        uint32  tag;
    } form;
    union {
        struct {
            uint16  x;
            uint16  y;
        };
        uint32  xy;
    };
    uint16      count;
    uint8       data[count];
    reference   after;
};
"""


def _inline_buf() -> bytes:
    # Small byte values keep any count field within the buffer, also when the layout changes
    return bytes((i * 7 + 1) % 5 for i in range(2000))


@pytest.fixture
def inline_cs() -> tuple[cstruct, cstruct]:
    inlined = cstruct().load(INLINE_DEF)
    not_inlined = cstruct().load(INLINE_DEF)

    for name in ("inner", "header"):
        type_ = not_inlined.resolve(name)
        type_._read = compiler._ReadSourceGenerator(type_, type_.__fields__, inline=False).generate()

    return inlined, not_inlined


def test_inline_nested(inline_cs: tuple[cstruct, cstruct]) -> None:
    """Test that nested structures and unions are inlined, and read the same values as without inlining."""
    inlined, not_inlined = inline_cs

    # The static part of the header is read at once, including the nested structures and unions
    # Only the fields from the dynamic array onwards are read by their types
    lines = source_lines(inlined.header)
    assert [line for line in lines if "stream.read(" in line or "._read" in line] == [
        "buf = stream.read(32)",
        "_value5 = values['data'] = _type_call(_type14, _type0._read_array("
        "stream, _count, context=values, endian=endian))",
        "_value6 = values['after'] = _type2._read(stream, context=values, endian=endian)",
    ]
    # The structures in the unions (resident, nonresident and the anonymous one) are proxied
    assert sum("_UnionProxy(" in line for line in lines) == 3

    buf = _inline_buf()
    for endian in ("<", ">"):
        obj = inlined.header(buf, endian=endian)
        expected = not_inlined.header(buf, endian=endian)
        assert parsed_state(obj) == parsed_state(expected)
        assert obj.dumps() == expected.dumps()
        assert obj.__dynamic_sizes__ == expected.__dynamic_sizes__
        assert obj.form.resident.length == expected.form.resident.length
        assert obj.x == expected.x

    # Union semantics still work on the inlined union
    obj = inlined.header(buf)
    obj.form.resident.length = 0x41414141
    assert obj.form.tag == 0x41414141
    assert obj.form.nonresident.vcn & 0xFFFFFFFF == 0x41414141


@pytest.mark.parametrize("size", [0, 1, 10, 30, 50])
def test_inline_nested_eof(inline_cs: tuple[cstruct, cstruct], size: int) -> None:
    """Test that a short read in a block with inlined structures raises an error for the whole block."""
    for cs in inline_cs:
        with pytest.raises(EOFError, match=r"^Read \d+ bytes, but expected \d+$"):
            cs.header(io.BytesIO(_inline_buf()[:size]))


def test_inline_nested_modified(inline_cs: tuple[cstruct, cstruct]) -> None:
    """Test that changing a nested structure after compiling falls back to the version without inlining."""
    inlined, _ = inline_cs
    interpreted = cstruct().load(INLINE_DEF, compiled=False)

    # Use the inlined version once
    buf = _inline_buf()
    inlined.header(buf)

    # Modifying a nested structure falls back to the behaviour of not inlining
    # The field offsets of the outer structure are now outdated, which the compiled version handles like the
    # interpreted version
    inlined.reference.add_field("extra", inlined.uint8)
    interpreted.reference.add_field("extra", interpreted.uint8)

    assert parsed_state(inlined.header(buf)) == parsed_state(interpreted.header(buf))
    assert inlined.header(buf).a.ref.extra == interpreted.header(buf).a.ref.extra


def test_inline_nested_modified_before_use() -> None:
    """Test that a nested structure isn't inlined if it's changed before the first read."""
    cs = cstruct().load(INLINE_DEF)
    other = cstruct().load(INLINE_DEF)

    # Modify a nested structure before the lazily compiled read method is used
    cs.reference.add_field("extra", cs.uint8)
    other.reference.add_field("extra", other.uint8)
    other.header._read = compiler._ReadSourceGenerator(other.header, other.header.__fields__, inline=False).generate()

    buf = _inline_buf()
    assert parsed_state(cs.header(buf)) == parsed_state(other.header(buf))


@pytest.mark.parametrize(
    ("name", "type_name", "offset", "size"),
    [
        # Offsets that do or don't match the offset of the field without the dynamic field
        ("x", "uint16", 1, 39),
        ("x", "uint16", 6, 39),
        ("i", "inner", 1, 39),
        ("i", "inner", 6, 39),
        # Short read in a block that could have an inlined structure
        ("i", "inner", 1, 7),
    ],
)
def test_compiled_offset_after_dynamic(name: str, type_name: str, offset: int, size: int) -> None:
    """Test that compiled structures read fields with an offset after a dynamic field like the interpreted version."""
    cdef = """
    struct inner {
        uint16  a;
        uint16  b;
    };

    struct test {
        uint8   n;
        char    s[n];
    };
    """
    results = []
    for compiled in (False, True):
        cs = cstruct().load(cdef, compiled=compiled)
        cs.test.add_field(name, cs.resolve(type_name), offset=offset)
        cs.test.add_field("y", cs.uint8)

        try:
            results.append(parsed_state(cs.test(bytes(range(1, size + 1)))))
        except EOFError as e:
            results.append(str(e))

    assert results[0] == results[1]


def test_compiled_bits_offset() -> None:
    """Test that the offsets of fields are tracked correctly through bit fields."""
    cdef = """
    struct inner { uint16 a; uint16 b; };
    struct test {
        uint16  a : 4;
        uint16  b : 12;
        uint16  c : 16;
        uint8   d : 4;
        uint8   e : 4;
        uint8   f : 8;
        inner   i;
        uint8   g;
    };
    """
    interpreted = cstruct().load(cdef, compiled=False)
    compiled = cstruct().load(cdef)

    # The tracked offset matches the field offsets, so the fields are read without seeking
    lines = source_lines(compiled.test)
    assert [line for line in lines if line.startswith(("_bit_buffer = ", "buf = ", "stream."))] == [
        "_bit_buffer = _type0._read(stream, endian=endian)",
        "_bit_buffer = _type0._read(stream, endian=endian)",
        "_bit_buffer = _type1._read(stream, endian=endian)",
        "_bit_buffer = _type1._read(stream, endian=endian)",
        "buf = stream.read(5)",
    ]

    # The interpreted version returns bit fields as plain integers, so only compare the values
    obj = compiled.test(bytes(range(1, 40)))
    expected = interpreted.test(bytes(range(1, 40)))
    assert [getattr(obj, name) for name in "abcdefg"] == [getattr(expected, name) for name in "abcdefg"]
    assert parsed_state(obj.i) == parsed_state(expected.i)


def test_lazy_compile(cs: cstruct) -> None:
    """Test that a structure is only compiled when it's first read."""
    cdef = """
    struct test {
        uint32  a;
    };
    """
    cs.load(cdef)

    assert cs.test.__compiled__
    assert isinstance(cs.test.__dict__["_read"], compiler._LazyCompileRead)

    expected = """
    def _read(cls, stream, *, context=None, endian):

        buf = stream.read(4)
        if len(buf) != 4: raise EOFError(f"Read {len(buf)} bytes, but expected 4")
        data = _unpack0[endian](buf)
        _value0 = _type_call(_type0, data[0])

        if cls is _cls0:
            obj = _object_new(cls)
            obj.a = _value0
            obj.__dynamic_sizes__ = {}
            return obj
        obj = _type_call(cls, **{'a': _value0})
        obj.__dynamic_sizes__ = {}
        return obj
    """
    assert cs.test._read.__source__ == dedent(expected).strip()
    assert isinstance(cs.test.__dict__["_read"], classmethod)
    assert cs.test(b"\x01\x00\x00\x00").a == 1


def test_generate_packed_write(cs: cstruct) -> None:
    """Test the generated code for packing numbers."""
    fields = [f(cs.uint8, name="a"), f(cs.int16, name="b"), f(cs.uint32, name="c")]
    code = next(write_generator(cs, fields)._generate_packed_source(fields))

    expected = """
    try:
        buf = _pack0[endian](data.a, data.b, data.c)
    except _struct_error:
        buf = _pack0[endian](_or_default(data.a, _type0), _or_default(data.b, _type1), _or_default(data.c, _type2))
    stream.write(buf)
    """

    assert code == dedent(expected)


def test_generate_packed_write_arrays(cs: cstruct, TestEnum: type[Enum]) -> None:
    """Test the generated code for packing arrays."""
    fields = [f(cs.uint16[2], name="a"), f(TestEnum[2], name="b"), f(cs.uint24[2], name="c")]
    gen = write_generator(cs, fields)
    code = next(gen._generate_packed_source(fields))

    expected = """
    if (_value0 := data.a) is None or len(_value0) != 2: _value0 = _array_values(_type0, _value0)
    if (_value1 := data.b) is None or len(_value1) != 2: _value1 = _array_values(_type1, _value1)
    if (_value2 := data.c) is None or len(_value2) != 2: _value2 = _array_values(_type2, _value2)
    stream.write(_pack0[endian](*_value0, *_value1, b''.join([item.to_bytes(3, _byteorder[endian], signed=False) for item in _value2])))
    """  # noqa: E501

    assert code == dedent(expected)
    assert gen.symbols["_pack0"]["<"].__self__.format == "<2H2B6s"


def test_generate_packed_write_byte_types(cs: cstruct) -> None:
    """Test the generated code for packing ``char`` and ``wchar`` fields."""
    fields = [f(cs.char, name="a"), f(cs.char[2], name="b"), f(cs.wchar, name="c"), f(cs.wchar[2], name="d")]
    gen = write_generator(cs, fields)
    code = next(gen._generate_packed_source(fields))

    expected = """
    if not isinstance(_value0 := data.a, bytes) or len(_value0) > 1: _value0 = _field_bytes(_type0, _value0, endian)
    if not isinstance(_value1 := data.b, bytes) or len(_value1) > 2: _value1 = _field_bytes(_type1, _value1, endian)
    if (_value2 := data.c) is None or len(_value2 := _value2.encode(_encoding0[endian], 'surrogatepass')) > 2: _value2 = _field_bytes(_type2, data.c, endian)
    if (_value3 := data.d) is None or len(_value3 := _value3.encode(_encoding0[endian], 'surrogatepass')) > 4: _value3 = _field_bytes(_type3, data.d, endian)
    stream.write(_pack0[endian](_value0, _value1, _value2, _value3))
    """  # noqa: E501

    assert code == dedent(expected)
    assert gen.symbols["_pack0"]["<"].__self__.format == "<1s2s2s4s"


def test_generate_packed_write_numbers(cs: cstruct, TestEnum: type[Enum]) -> None:
    """Test the generated code for packing enums, pointers and ``Int`` types together with a default value check."""
    cs.pointer = cs.uint64
    fields = [f(TestEnum, name="a"), f(cs._make_pointer(TestEnum), name="b"), f(cs.uint24, name="c")]
    gen = write_generator(cs, fields)
    code = next(gen._generate_packed_source(fields))

    expected = """
    if (_value0 := data.a) is None: _value0 = _type0.__default__()
    if (_value1 := data.c) is None: _value1 = _type2.__default__()
    try:
        buf = _pack0[endian](_value0._value_, data.b, _value1.to_bytes(3, _byteorder[endian], signed=False))
    except _struct_error:
        buf = _pack0[endian](_value0._value_, _or_default(data.b, _type1), _value1.to_bytes(3, _byteorder[endian], signed=False))
    stream.write(buf)
    """  # noqa: E501

    assert code == dedent(expected)
    assert gen.symbols["_pack0"]["<"].__self__.format == "<BQ3s"


def test_generate_field_write(cs: cstruct) -> None:
    """Test the generated code for writing a field using its own type."""
    field = Field("a", cs.uleb128)
    code = next(write_generator(cs, [field])._generate_field_source(field))

    expected = """
    _value = data.a
    if _value is None: _value = _type0.__default__()
    _type0._write(stream, _value, endian=endian)
    """

    assert code == dedent(expected)


def test_generate_bits_write(cs: cstruct, TestEnum: type[Enum]) -> None:
    """Test the generated code for writing the bit fields that share a value of the bit buffer."""
    fields = [Field("a", cs.uint8, 2), Field("b", TestEnum, 6)]
    code = next(write_generator(cs, fields)._generate_bits_source(fields))

    expected = """
    if (_value0 := data.a) is None: _value0 = _type0.__default__()
    if (_value1 := data.b) is None: _value1 = _type1.__default__()
    stream.write(_pack0[endian]((_value0 << 0 | _value1._value_ << 2 if endian == '<' else _value0 << 6 | _value1._value_ << 0)))
    """  # noqa: E501

    assert code == dedent(expected)


def test_generate_structure_write(cs: cstruct) -> None:
    """Test the generated code of a complete structure with packed, inlined, dynamic and bit fields."""
    cdef = """
    struct nested {
        uint8   a;
    };

    struct test {
        uint32  b;
        char    c[2];
        nested  d;
        uint8   n;
        uint8   e[n];
        uint16  f : 4;
        uint16  g : 12;
    };
    """
    cs.load(cdef)

    assert cs.test.__compiled__
    assert isinstance(cs.test.__dict__["_write"], compiler._LazyCompileWrite)

    expected = """
    def _write(cls, stream, data, *, endian):
        if cls is not _cls0 or _type2.__init__ is not _init0: return _struct_write(cls, stream, data, endian=endian)
        start = stream.tell()

        if not isinstance(_value0 := data.c, bytes) or len(_value0) > 2: _value0 = _field_bytes(_type1, _value0, endian)
        if (_value1 := data.d) is None: _value1 = _type2.__default__()
        try:
            buf = _pack0[endian](data.b, _value0, _value1.a, data.n)
        except _struct_error:
            buf = _pack0[endian](_or_default(data.b, _type0), _value0, _or_default(_value1.a, _type3), _or_default(data.n, _type3))
        stream.write(buf)


        _value = data.e
        if _value is None: _value = _type4.__default__()
        _type4._write(stream, _value, endian=endian)


        if (_value2 := data.f) is None: _value2 = _type5.__default__()
        if (_value3 := data.g) is None: _value3 = _type5.__default__()
        stream.write(_pack1[endian]((_value2 << 0 | _value3 << 4 if endian == '<' else _value2 << 12 | _value3 << 0)))

        return stream.tell() - start
    """  # noqa: E501
    assert cs.test._write.__source__ == dedent(expected).strip()
    assert isinstance(cs.test.__dict__["_write"], classmethod)

    obj = cs.test(b=1, c=b"ab", d=cs.nested(a=2), n=1, e=[3], f=4, g=5)
    assert obj.dumps() == b"\x01\x00\x00\x00ab\x02\x01\x03\x54\x00"


def test_generate_union_write(cs: cstruct) -> None:
    """Test the generated code of a union, which is written by its largest field and unwraps its proxies."""
    cdef = """
    union test {
        struct {
            uint16  a;
            uint16  b;
        } c;
        uint16  d;
    };
    """
    cs.load(cdef)

    expected = """
    def _write(cls, stream, data, *, endian):
        if cls is not _cls0 or _type0.__init__ is not _init0: return _union_write(cls, stream, data, endian=endian)

        if (_value0 := data.c) is None: _value0 = _type0.__default__()
        if type(_value0) is _UnionProxy: _value0 = _value0.__target__
        try:
            buf = _pack0[endian](_value0.a, _value0.b)
        except _struct_error:
            buf = _pack0[endian](_or_default(_value0.a, _type1), _or_default(_value0.b, _type1))
        stream.write(buf)

        return 4
    """
    assert cs.test._write.__source__ == dedent(expected).strip()


def test_generate_align_write(cs: cstruct) -> None:
    """Test the generated code of an aligned structure, which pads to the position in the stream."""
    cdef = """
    struct test {
        uint8   n;
        uint8   a[n];
        uint32  b;
    };
    """
    cs.load(cdef, align=True)

    expected = r"""
    def _write(cls, stream, data, *, endian):
        if cls is not _cls0: return _struct_write(cls, stream, data, endian=endian)
        start = stream.tell()

        try:
            buf = _pack0[endian](data.n)
        except _struct_error:
            buf = _pack0[endian](_or_default(data.n, _type0))
        stream.write(buf)


        _value = data.a
        if _value is None: _value = _type1.__default__()
        _type1._write(stream, _value, endian=endian)

        stream.write(b"\x00" * (-stream.tell() & (4 - 1)))

        try:
            buf = _pack1[endian](data.b)
        except _struct_error:
            buf = _pack1[endian](_or_default(data.b, _type2))
        stream.write(buf)

        stream.write(b"\x00" * (-stream.tell() & (cls.__alignment__ - 1)))
        return stream.tell() - start
    """
    assert cs.test._write.__source__ == dedent(expected).strip()


def test_generate_static_write(cs: cstruct) -> None:
    """Test that the generated code of a static structure doesn't need the position in the stream."""
    cdef = """
    struct test {
        uint32  a;
        uint8   b;
    };
    """
    cs.load(cdef)

    expected = """
    def _write(cls, stream, data, *, endian):
        if cls is not _cls0: return _struct_write(cls, stream, data, endian=endian)

        try:
            buf = _pack0[endian](data.a, data.b)
        except _struct_error:
            buf = _pack0[endian](_or_default(data.a, _type0), _or_default(data.b, _type1))
        stream.write(buf)

        return 5
    """
    assert cs.test._write.__source__ == dedent(expected).strip()


def test_generate_offset_write(cs: cstruct) -> None:
    """Test the generated code for a field with an offset after a dynamic field, which pads depending on the stream."""
    cdef = """
    struct test {
        uint8   n;
        uint8   a[n];
    };
    """
    cs.load(cdef)
    cs.test.add_field("b", cs.uint8)
    cs.test.add_field("c", cs.uint8, offset=4)

    expected = r"""
    def _write(cls, stream, data, *, endian):
        if cls is not _cls0: return _struct_write(cls, stream, data, endian=endian)
        start = stream.tell()

        try:
            buf = _pack0[endian](data.n)
        except _struct_error:
            buf = _pack0[endian](_or_default(data.n, _type0))
        stream.write(buf)


        _value = data.a
        if _value is None: _value = _type1.__default__()
        _type1._write(stream, _value, endian=endian)


        try:
            buf = _pack1[endian](data.b)
        except _struct_error:
            buf = _pack1[endian](_or_default(data.b, _type0))
        stream.write(buf)

        stream.write(b"\x00" * (start + 4 - stream.tell()))

        try:
            buf = _pack2[endian](data.c)
        except _struct_error:
            buf = _pack2[endian](_or_default(data.c, _type0))
        stream.write(buf)

        return stream.tell() - start
    """
    assert cs.test._write.__source__ == dedent(expected).strip()


def test_generate_static_call_write(cs: cstruct) -> None:
    """Test that the generated code keeps track of the position through a static field written using its type."""
    cdef = """
    struct test {
        uint8   a[1][1];
        uint8   b;
        uint8   c;
    };
    """
    cs.load(cdef)

    expected = """
    def _write(cls, stream, data, *, endian):
        if cls is not _cls0: return _struct_write(cls, stream, data, endian=endian)
        start = stream.tell()

        _value = data.a
        if _value is None: _value = _type0.__default__()
        _type0._write(stream, _value, endian=endian)


        try:
            buf = _pack0[endian](data.b, data.c)
        except _struct_error:
            buf = _pack0[endian](_or_default(data.b, _type1), _or_default(data.c, _type1))
        stream.write(buf)

        return stream.tell() - start
    """
    assert cs.test._write.__source__ == dedent(expected).strip()


def test_write_not_compiled(cs: cstruct) -> None:
    """Test that anything that can't be written by packing it uses the interpreted writer for the entire structure."""
    cdef = """
    struct unsupported {
        uleb128 a;
    };

    union dynamic {
        struct {
            uint8 n;
            char  a[n];
        } b;
        uint8 c;
    };

    union empty_field {
        char a[0];
    };

    struct wchar_bits {
        wchar a : 4;
    };

    struct backwards {
        uint32 a;
    };

    struct bits_offset {
        uint16 a : 4;
    };
    """
    cs.load(cdef)
    cs.backwards.add_field("b", cs.uint8, offset=2)
    cs.bits_offset.add_field("b", cs.uint16, bits=4, offset=8)

    assert not hasattr(cs.unsupported._write, "__source__")
    assert not hasattr(cs.dynamic._write, "__source__")
    assert not hasattr(cs.empty_field._write, "__source__")
    assert not hasattr(cs.wchar_bits._write, "__source__")
    assert not hasattr(cs.backwards._write, "__source__")
    assert not hasattr(cs.bits_offset._write, "__source__")

    # Reading them is still compiled
    for type_ in (cs.wchar_bits, cs.backwards, cs.bits_offset):
        assert type_.__compiled__
        assert hasattr(type_._read, "__source__")


def test_write_after_add_field(cs: cstruct) -> None:
    """Test that adding a field to a compiled or inlined structure is noticed before and after the first write."""
    cdef = """
    struct nested {
        uint8   a;
    };

    struct test {
        uint8   b;
        nested  c;
        uint8   d;
    };
    """
    cs.load(cdef)

    # Before the first write
    cs.nested.add_field("e", cs.uint8)
    assert cs.test(b=1, c=cs.nested(a=2, e=3), d=4).dumps() == b"\x01\x02\x03\x04"

    # After the first write, in the structure that was compiled
    cs.test.add_field("f", cs.uint8)
    assert cs.test(b=1, c=cs.nested(a=2, e=3), d=4, f=5).dumps() == b"\x01\x02\x03\x04\x05"

    # After the first write, in the structure that was inlined
    cs.nested.add_field("g", cs.uint8)
    assert cs.test(b=1, c=cs.nested(a=2, e=3, g=6), d=4, f=5).dumps() == b"\x01\x02\x03\x06\x04\x05"

    # A field that isn't supported by the compiler
    cs.test.add_field("h", cs.uleb128)
    assert cs.test(b=1, c=cs.nested(a=2, e=3, g=6), d=4, f=5, h=7).dumps() == b"\x01\x02\x03\x06\x04\x05\x07"

    cdef = """
    struct nested_last {
        uint8   a;
    };

    struct test_last {
        uint8   b;
        nested_last c;
    };
    """
    cs.load(cdef)

    # After the first write, in a structure that was inlined without any fields after it
    assert cs.test_last(b=1, c=cs.nested_last(a=2)).dumps() == b"\x01\x02"
    cs.nested_last.add_field("d", cs.uint8)
    assert cs.test_last(b=1, c=cs.nested_last(a=2, d=3)).dumps() == b"\x01\x02\x03"


def test_write_generate_failure(cs: cstruct) -> None:
    """Test that a failure to compile ``_read`` also reverts ``_write`` to the interpreted version."""
    cdef = """
    struct test {
        uint8   a;
    };
    """
    cs.load(cdef)

    assert cs.test(a=1).dumps() == b"\x01"

    with patch.object(compiler._ReadSourceGenerator, "generate", side_effect=ValueError):
        assert cs.test(b"\x01").a == 1

    # Adding a field no longer recompiles the structure, so _write has to be the interpreted version too
    assert not cs.test.__compiled__
    cs.test.add_field("b", cs.uint8)
    assert cs.test(a=1, b=2).dumps() == b"\x01\x02"


def test_write_generate_failure_keeps_read(cs: cstruct) -> None:
    """Test that a failure to compile ``_write`` doesn't revert ``_read``."""
    cdef = """
    struct test {
        uint8   a;
    };
    """
    cs.load(cdef)

    with patch.object(compiler._WriteSourceGenerator, "generate", side_effect=ValueError):
        assert cs.test(a=1).dumps() == b"\x01"

    assert cs.test.__compiled__
    assert not hasattr(cs.test._write, "__source__")
    assert hasattr(cs.test._read, "__source__")


def test_write_custom_types(cs: cstruct) -> None:
    """Test that types with a custom ``_write`` or ``_write_array`` method aren't packed."""

    class CustomWrite(int, Packed):
        __fmt__ = "B"

        @classmethod
        def _write(cls, stream: BinaryIO, data: int, *, endian: Endianness) -> int:
            return stream.write(b"write")

    class CustomWriteArray(int, Packed):
        __fmt__ = "B"

        @classmethod
        def _write_array(cls, stream: BinaryIO, data: list, *, endian: Endianness) -> int:
            return stream.write(b"array")

    cs.add_custom_type("custom_write", CustomWrite, size=1)
    cs.add_custom_type("custom_write_array", CustomWriteArray, size=1)

    cdef = """
    struct test {
        uint8               a;
        custom_write        b;
        custom_write_array  c[2];
    };
    """
    cs.load(cdef)

    assert cs.test(a=1, b=2, c=[3, 4]).dumps() == b"\x01writearray"

    cdef = """
    struct test_bits {
        uint8           a;
        custom_write    b : 4;
    };
    """
    cs.load(cdef)

    assert cs.test_bits(a=1, b=2).dumps() == b"\x01write"


@pytest.mark.parametrize("endian", ["<", ">", "!", "@", "="])
def test_native_alignment(endian: Endianness, compiled: bool) -> None:
    """Test that the ``@`` endianness doesn't add native alignment padding between packed fields."""
    cdef = """
    struct test {
        uint8   a;
        uint32  b;
        uint16  c;
        uint64  d;
    };
    """
    cs = cstruct(endian=endian)
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert len(cs.test) == 15

    # Packing or unpacking multiple values at once shouldn't add padding to align them
    buf = cs.uint8.dumps(1) + cs.uint32.dumps(2) + cs.uint16.dumps(3) + cs.uint64.dumps(4)
    obj = cs.test(buf)
    assert obj.a == 1
    assert obj.b == 2
    assert obj.c == 3
    assert obj.d == 4
    assert obj.dumps() == buf


def test_read_offset_before_position(cs: cstruct, compiled: bool) -> None:
    """Test that compiled structures read a field with an offset before the current position from that offset."""
    cdef = """
    struct test {
        uint8   a;
        uint16  b;
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.test.add_field("c", cs.uint8, offset=2)
    cs.test.add_field("d", cs.uint8)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(bytes(range(16)))
    assert obj.b == 0x0201
    assert obj.c == 2
    assert obj.d == 3


def test_read_offset_before_position_after_gap(cs: cstruct, compiled: bool) -> None:
    """Test that an offset before the current position is also noticed after an earlier offset moved forward."""
    cdef = """
    struct test {
        uint8   a;
        uint16  b;
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.test.add_field("c", cs.uint8, offset=8)
    cs.test.add_field("d", cs.uint8, offset=4)
    cs.test.add_field("e", cs.uint8)

    assert verify_compiled(cs.test, compiled)

    obj = cs.test(bytes(range(16)))
    assert obj.c == 8
    assert obj.d == 4
    assert obj.e == 5


def test_read_offset_after_dynamic_field(cs: cstruct, compiled: bool) -> None:
    """Test that a field with an offset after a dynamic field doesn't prevent the structure from being compiled."""
    cdef = """
    struct test {
        uint8   n;
        uint8   a[n];
        uint8   b;
    };
    """
    cs.load(cdef, compiled=compiled)
    cs.test.add_field("c", cs.uint8, offset=6)
    cs.test.add_field("d", cs.uint8)

    obj = cs.test(bytes((1, *range(1, 16))))
    assert obj.a == [1]
    assert obj.b == 2
    assert obj.c == 6
    assert obj.d == 7

    assert verify_compiled(cs.test, compiled)
