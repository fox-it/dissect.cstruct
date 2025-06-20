from __future__ import annotations

from operator import itemgetter
from textwrap import dedent
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from dissect.cstruct import compiler
from dissect.cstruct.expression import Expression
from dissect.cstruct.types.structure import Field

if TYPE_CHECKING:
    from collections.abc import Iterator

    from dissect.cstruct.cstruct import cstruct
    from dissect.cstruct.types.base import BaseType
    from dissect.cstruct.types.enum import Enum


def f(field_type: type[BaseType], offset: int | None = 0, name: str = "") -> Field:
    return Field(name, field_type, offset=offset)


def strip_fields(info: Iterator[tuple[Field, int, str]]) -> list[tuple[int, str]]:
    return list(map(itemgetter(1, 2), info))


def mkfmt(info: Iterator[tuple[Field, int, str]]) -> str:
    return "".join(f"{count}{char}" for _, count, char in info)


@pytest.fixture
def TestEnum(cs: cstruct) -> type[Enum]:
    return cs._make_enum("Test", cs.uint8, {"a": 1})


def test_generate_struct_info(cs: cstruct, TestEnum: type[Enum]) -> None:
    fields = [f(cs.uint8), f(cs.int16), f(cs.uint32), f(cs.int64)]
    fmt = strip_fields(compiler._generate_struct_info(cs, fields))
    assert fmt == [(1, "B"), (1, "h"), (1, "I"), (1, "q")]

    fields = [f(cs.uint8[4]), f(cs.int16[4]), f(cs.uint32[4]), f(cs.int64[4])]
    fmt = strip_fields(compiler._generate_struct_info(cs, fields))
    assert fmt == [(4, "B"), (4, "h"), (4, "I"), (4, "q")]

    fields = [f(cs.char), f(cs.wchar), f(cs.uint24), f(cs.int128)]
    fmt = strip_fields(compiler._generate_struct_info(cs, fields))
    assert fmt == [(1, "x"), (2, "x"), (3, "x"), (16, "x")]

    fields = [f(cs.char[2]), f(cs.wchar[2]), f(cs.uint24[2]), f(cs.int128[2])]
    fmt = strip_fields(compiler._generate_struct_info(cs, fields))
    assert fmt == [(2, "x"), (4, "x"), (6, "x"), (32, "x")]

    fields = [f(cs.char), f(cs.char[2]), f(cs.char)]
    fmt = strip_fields(compiler._generate_struct_info(cs, fields))
    assert fmt == [(1, "x"), (2, "x"), (1, "x")]

    fields = [f(cs.uint8), f(cs.void), f(cs.int16)]
    fmt = strip_fields(compiler._generate_struct_info(cs, fields))
    assert fmt == [(1, "B"), (1, "h")]

    fields = [f(cs.uint8), f(cs.uint16), f(cs.char[0])]
    fmt = strip_fields(compiler._generate_struct_info(cs, fields))
    assert fmt == [(1, "B"), (1, "H"), (0, "x")]

    cs.pointer = cs.uint64
    TestPointer = cs._make_pointer(TestEnum)
    fields = [f(TestEnum), f(TestPointer)]
    fmt = strip_fields(compiler._generate_struct_info(cs, fields))
    assert fmt == [(1, "B"), (1, "Q")]


def test_generate_struct_info_offsets(cs: cstruct) -> None:
    fields = [f(cs.uint8, 0), f(cs.uint8, 4), f(cs.uint8[2], 5), f(cs.uint8, 8)]
    fmt = strip_fields(compiler._generate_struct_info(cs, fields))
    assert fmt == [(1, "B"), (3, "x"), (1, "B"), (2, "B"), (1, "x"), (1, "B")]

    # Different starting offsets are handled in the field reading loop of the compilation
    fields = [f(cs.uint8, 4)]
    fmt = strip_fields(compiler._generate_struct_info(cs, fields))
    assert fmt == [(1, "B")]


@pytest.mark.parametrize(
    ("fields", "fmt"),
    [
        ([(None, 1, "B"), (None, 3, "B")], "4B"),
        ([(None, 1, "B"), (None, 3, "B"), (None, 2, "H")], "4B2H"),
        ([(None, 1, "B"), (None, 0, "x")], "B"),
        ([(None, 1, "B"), (None, 0, "x"), (None, 2, "H")], "B2H"),
        ([(None, 1, "B"), (None, 0, "x"), (None, 2, "x"), (None, 1, "H")], "B2xH"),
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
    code = next(compiler._ReadSourceGenerator(cs, fields)._generate_packed(fields))

    expected = """
    buf = stream.read(15)
    if len(buf) != 15: raise EOFError()
    data = _struct(cls.cs.endian, "BhIq").unpack(buf)

    r["a"] = type.__call__(_0, data[0])

    r["b"] = type.__call__(_1, data[1])

    r["c"] = type.__call__(_2, data[2])

    r["d"] = type.__call__(_3, data[3])
    """

    assert code == dedent(expected)


def test_generate_packed_read_array(cs: cstruct) -> None:
    fields = [
        f(cs.uint8[2], name="a"),
        f(cs.int16[3], name="b"),
        f(cs.uint32[4], name="c"),
        f(cs.int64[5], name="d"),
    ]
    code = next(compiler._ReadSourceGenerator(cs, fields)._generate_packed(fields))

    expected = """
    buf = stream.read(64)
    if len(buf) != 64: raise EOFError()
    data = _struct(cls.cs.endian, "2B3h4I5q").unpack(buf)

    _t = _0
    _et = _t.type
    r["a"] = type.__call__(_t, [type.__call__(_et, e) for e in data[0:2]])

    _t = _1
    _et = _t.type
    r["b"] = type.__call__(_t, [type.__call__(_et, e) for e in data[2:5]])

    _t = _2
    _et = _t.type
    r["c"] = type.__call__(_t, [type.__call__(_et, e) for e in data[5:9]])

    _t = _3
    _et = _t.type
    r["d"] = type.__call__(_t, [type.__call__(_et, e) for e in data[9:14]])
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
    code = next(compiler._ReadSourceGenerator(cs, fields)._generate_packed(fields))

    expected = """
    buf = stream.read(18)
    if len(buf) != 18: raise EOFError()
    data = _struct(cls.cs.endian, "18x").unpack(buf)

    r["a"] = type.__call__(_0, buf[0:1])

    r["b"] = type.__call__(_1, buf[1:3])

    r["c"] = _2(buf[3:5])

    r["d"] = _3(buf[5:9])

    r["e"] = _4(buf[9:12])

    _t = _5
    _et = _t.type
    _b = buf[12:18]
    r["f"] = type.__call__(_t, [_et(_b[i:i + 3]) for i in range(0, 6, 3)])
    """

    assert code == dedent(expected)


def test_generate_packed_read_composite_types(cs: cstruct, TestEnum: type[Enum]) -> None:
    cs.pointer = cs.uint64
    TestPointer = cs._make_pointer(TestEnum)

    fields = [
        f(TestEnum, name="a"),
        f(TestPointer, name="b"),
        f(cs.void),
        f(TestEnum[2], name="c"),
    ]
    code = next(compiler._ReadSourceGenerator(cs, fields)._generate_packed(fields))

    expected = """
    buf = stream.read(11)
    if len(buf) != 11: raise EOFError()
    data = _struct(cls.cs.endian, "BQ2B").unpack(buf)

    r["a"] = type.__call__(_0, data[0])

    _pt = _1
    r["b"] = _pt.__new__(_pt, data[1], stream, r)

    _t = _2
    _et = _t.type
    r["c"] = type.__call__(_t, [type.__call__(_et, e) for e in data[2:4]])
    """

    assert code == dedent(expected)


def test_generate_packed_read_offsets(cs: cstruct) -> None:
    fields = [
        f(cs.uint8, name="a"),
        f(cs.uint8, 8, name="b"),
    ]
    code = next(compiler._ReadSourceGenerator(cs, fields)._generate_packed(fields))

    expected = """
    buf = stream.read(9)
    if len(buf) != 9: raise EOFError()
    data = _struct(cls.cs.endian, "B7xB").unpack(buf)

    r["a"] = type.__call__(_0, data[0])

    r["b"] = type.__call__(_1, data[1])
    """

    assert code == dedent(expected)


def test_generate_structure_read(cs: cstruct) -> None:
    mock_type = Mock()
    mock_type.__anonymous__ = False

    field = Field("a", mock_type)
    code = next(compiler._ReadSourceGenerator(cs, [field])._generate_structure(field))

    expected = """
    _s = stream.tell()
    r["a"] = _0._read(stream, context=r)
    s["a"] = stream.tell() - _s
    """

    assert code == dedent(expected)


def test_generate_structure_read_anonymous(cs: cstruct) -> None:
    mock_type = Mock()
    mock_type.__anonymous__ = True

    field = Field("a", mock_type)
    code = next(compiler._ReadSourceGenerator(cs, [field])._generate_structure(field))

    expected = """
    _s = stream.tell()
    r["a"] = _0._read(stream, context=r)
    s["a"] = stream.tell() - _s
    """

    assert code == dedent(expected)


def test_generate_array_read(cs: cstruct) -> None:
    field = Field("a", Mock())
    code = next(compiler._ReadSourceGenerator(cs, [field])._generate_array(field))

    expected = """
    _s = stream.tell()
    r["a"] = _0._read(stream, context=r)
    s["a"] = stream.tell() - _s
    """

    assert code == dedent(expected)


def test_generate_bits_read(cs: cstruct, TestEnum: type[Enum]) -> None:
    field = Field("a", cs.int8, 2)
    code = next(compiler._ReadSourceGenerator(cs, [field])._generate_bits(field))

    expected = """
    _t = _0
    r["a"] = type.__call__(_t, bit_reader.read(_t, 2))
    """

    assert code == dedent(expected)

    field = Field("b", TestEnum, 2)
    code = next(compiler._ReadSourceGenerator(cs, [field])._generate_bits(field))

    expected = """
    _t = _0
    r["b"] = type.__call__(_t, bit_reader.read(_t.type, 2))
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

    output = "\n".join(compiler._ReadSourceGenerator(cs, fields)._generate_fields())

    expected = """
    buf = stream.read(2)
    if len(buf) != 2: raise EOFError()
    data = _struct(cls.cs.endian, "H").unpack(buf)

    r["size"] = type.__call__(_0, data[0])


    _t = _1
    r["a"] = type.__call__(_t, bit_reader.read(_t.type, 4))


    _t = _2
    r["b"] = type.__call__(_t, bit_reader.read(_t, 4))

    bit_reader.reset()
    stream.seek(o + 3)

    _s = stream.tell()
    r["c"] = _3._read(stream, context=r)
    s["c"] = stream.tell() - _s
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

    output = "\n".join(compiler._ReadSourceGenerator(cs, fields)._generate_fields())

    expected = """
    buf = stream.read(2)
    if len(buf) != 2: raise EOFError()
    data = _struct(cls.cs.endian, "H").unpack(buf)

    r["size"] = type.__call__(_0, data[0])


    _t = _1
    r["a"] = type.__call__(_t, bit_reader.read(_t, 4))


    _t = _2
    r["b"] = type.__call__(_t, bit_reader.read(_t.type, 4))

    bit_reader.reset()
    stream.seek(o + 3)

    _s = stream.tell()
    r["c"] = _3._read(stream, context=r)
    s["c"] = stream.tell() - _s
    """

    assert output.strip() == dedent(expected).strip()
