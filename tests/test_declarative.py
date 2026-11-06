from __future__ import annotations

from textwrap import dedent
from typing import Annotated

import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.declarative import (
    EOF,
    Struct,
    Union,
    char,
    double,
    field,
    float,
    float16,
    pointer,
    uint8,
    uint16,
    uint32,
    uint64,
)
from dissect.cstruct.types.pointer import Pointer
from dissect.cstruct.types.structure import Structure, StructureMetaType, UnionMetaType
from dissect.cstruct.types.structure import Union as CUnion

# Module level cstruct instance to exercise bound-type inference through stringified annotations
module_cs = cstruct()


def test_basic_struct() -> None:
    class Basic(Struct):
        magic: uint8[4]
        version: uint32

    assert issubclass(Basic, Structure)
    assert Basic.__size__ == 8
    assert list(Basic.__members__.keys()) == ["magic", "version"]

    obj = Basic(b"ABCD" + (2).to_bytes(4, "little"))
    assert bytes(obj.magic) == b"ABCD"
    assert obj.version == 2


@pytest.mark.parametrize(
    ("kwargs", "data"),
    [
        ({}, b"ABCD\x02\x00\x00\x00"),
        ({"cs": cstruct(endian=">")}, b"ABCD\x00\x00\x00\x02"),
    ],
    ids=["new-cstruct", "bound"],
)
def test_instances(kwargs: dict, data: bytes) -> None:
    """Test that instances can be created, written and printed like those of a regular structure."""

    class Instances(Struct, **kwargs):
        magic: uint8[4]
        version: uint32

    obj = Instances()
    assert obj.magic == [0, 0, 0, 0]
    assert obj.version == 0
    assert obj.dumps() == b"\x00" * 8
    assert repr(obj) == "<Instances magic=[0, 0, 0, 0] version=0x0>"

    obj = Instances(magic=list(b"ABCD"), version=2)
    assert obj.dumps() == data
    assert Instances(data) == obj
    assert bytes(Instances(data)) == data


def test_cross_reference() -> None:
    class CRHeader(Struct):
        magic: uint8[4]
        version: uint32

    class CRFile(Struct):
        header: CRHeader
        size: uint64

    assert CRFile.__size__ == 16
    assert CRFile.__members__["header"].type is CRHeader

    obj = CRFile(b"ABCD" + (1).to_bytes(4, "little") + (123).to_bytes(8, "little"))
    assert bytes(obj.header.magic) == b"ABCD"
    assert obj.header.version == 1
    assert obj.size == 123


def test_bound_keyword(cs: cstruct) -> None:
    class Bound(Struct, cs=cs):
        a: uint32
        b: uint8[4]

    assert Bound.__cs__ is cs
    assert cs.Bound is Bound
    assert Bound.__size__ == 8


def test_base_inheritance(cs: cstruct) -> None:
    class Base(Struct, cs=cs):
        pass

    class Child(Base):
        a: uint32

    assert Child.__cs__ is cs
    assert cs.Child is Child


def test_field_inheritance(cs: cstruct) -> None:
    class Header(Struct, cs=cs):
        magic: uint8[4]
        version: uint32

    class Extended(Header):
        flags: uint16

    assert list(Extended.__members__.keys()) == ["magic", "version", "flags"]
    assert Extended.__size__ == Header.__size__ + 2
    # The parent is unchanged
    assert list(Header.__members__.keys()) == ["magic", "version"]
    assert Header.__size__ == 8

    # Without fields of its own, a subclass is a copy of its parent
    class Alias(Header):
        pass

    assert list(Alias.__members__.keys()) == ["magic", "version"]
    assert cs.Alias is Alias

    obj = Extended(b"ABCD" + (1).to_bytes(4, "little") + (2).to_bytes(2, "little"))
    assert bytes(obj.magic) == b"ABCD"
    assert obj.version == 1
    assert obj.flags == 2


def test_field_inheritance_duplicate(cs: cstruct) -> None:
    class DupBase(Struct, cs=cs):
        a: uint32

    with pytest.raises(ValueError, match="Duplicate field name: a"):

        class DupChild(DupBase):
            a: uint16

    assert "DupChild" not in cs.types


def test_self_referential_pointer(cs: cstruct) -> None:
    class Node(Struct, cs=cs):
        data: uint32
        next: pointer["Node"]

    assert issubclass(Node.__members__["next"].type, Pointer)
    assert Node.__members__["next"].type.__type__ is Node
    assert Node.__size__ == 4 + cs.pointer.__size__


def test_self_referential_pointer_string(cs: cstruct) -> None:
    class Node(Struct, cs=cs):
        data: uint32
        next: "Node*"  # noqa: F722

    assert issubclass(Node.__members__["next"].type, Pointer)
    assert Node.__members__["next"].type.__type__ is Node


def test_self_referential_embed(cs: cstruct) -> None:
    with pytest.raises(TypeError, match=r"^Field 'inner' embeds 'Recursive' in itself, use a pointer instead$"):

        class Recursive(Struct, cs=cs):
            inner: Recursive

    # The failed class must not remain registered
    assert "Recursive" not in cs.types
    assert not hasattr(cs, "Recursive")

    with pytest.raises(TypeError, match=r"^Field 'inner' embeds 'RecursiveArray' in itself, use a pointer instead$"):

        class RecursiveArray(Struct, cs=cs):
            inner: "RecursiveArray[2]"

    assert "RecursiveArray" not in cs.types
    assert not hasattr(cs, "RecursiveArray")


def test_inferred_cstruct() -> None:
    class Inferred(Struct):
        a: module_cs.uint32
        b: module_cs.uint8[4]

    assert Inferred.__cs__ is module_cs


def test_align_keyword(cs: cstruct) -> None:
    class Packed(Struct, cs=cs):
        a: uint8
        b: uint32

    class Aligned(Struct, cs=cs, align=True):
        a: uint8
        b: uint32

    assert Packed.__size__ == 5
    assert Aligned.__size__ == 8
    assert Aligned.__members__["b"].offset == 4


def test_align_attribute(cs: cstruct) -> None:
    class Aligned(Struct, cs=cs):
        __align__ = True

        a: uint8
        b: uint32

    assert Aligned.__size__ == 8


def test_field_bits(cs: cstruct) -> None:
    class Bits(Struct, cs=cs):
        a: field(uint16, bits=4)
        b: field(uint16, bits=4)

    assert Bits.__size__ == 2
    assert Bits.__members__["a"].bits == 4


def test_field_offset(cs: cstruct) -> None:
    class Offset(Struct, cs=cs):
        a: uint32
        b: field(uint32, offset=0x10)

    assert Offset.__size__ == 0x14
    assert Offset.__members__["b"].offset == 0x10


def test_field_annotated_bits(cs: cstruct) -> None:
    class Bits(Struct, cs=cs):
        a: Annotated[uint16, field(bits=4)]
        b: Annotated[uint16, field(bits=4)]

    assert Bits.__size__ == 2
    assert Bits.__members__["a"].bits == 4
    assert Bits.__members__["b"].bits == 4


def test_field_annotated_offset(cs: cstruct) -> None:
    class Offset(Struct, cs=cs):
        a: uint32
        b: Annotated[uint32, field(offset=0x10)]

    assert Offset.__size__ == 0x14
    assert Offset.__members__["b"].offset == 0x10


def test_field_annotated_forward_ref(cs: cstruct) -> None:
    class Fwd(Struct, cs=cs):
        a: Annotated["uint16", field(bits=4)]
        b: Annotated["uint16", "some metadata"]

    assert Fwd.__size__ == 2 + 2
    assert Fwd.__members__["a"].bits == 4
    assert Fwd.__members__["b"].type is cs.uint16


def test_annotated_without_field(cs: cstruct) -> None:
    class Plain(Struct, cs=cs):
        a: Annotated[uint32, "some metadata"]

    assert Plain.__size__ == 4
    assert Plain.__members__["a"].type is cs.uint32


def test_union(cs: cstruct) -> None:
    class Value(Union, cs=cs):
        as_u32: uint32
        as_bytes: uint8[4]

    assert Value.__size__ == 4
    assert cs.Value is Value

    obj = Value(b"\x01\x00\x00\x00")
    assert obj.as_u32 == 1
    assert bytes(obj.as_bytes) == b"\x01\x00\x00\x00"


def test_pointer(cs: cstruct) -> None:
    class WithPointer(Struct, cs=cs):
        ptr: pointer[uint32]

    assert issubclass(WithPointer.__members__["ptr"].type, Pointer)
    assert WithPointer.__members__["ptr"].type.__type__ is cs.uint32


def test_pointer_inferred_cstruct() -> None:
    class InferredPointer(Struct):
        ptr: pointer[module_cs.uint32]

    assert InferredPointer.__cs__ is module_cs
    assert InferredPointer.__members__["ptr"].type.__type__ is module_cs.uint32


def test_field_spec_reuse(cs: cstruct) -> None:
    spec = field("uint16", bits=4)

    class First(Struct, cs=cs):
        a: spec

    class Second(Struct, cs=cs):
        a: spec

    # The shared FieldSpec must not be mutated by class creation
    assert spec.type == "uint16"
    assert First.__members__["a"].bits == Second.__members__["a"].bits == 4


def test_string_annotation(cs: cstruct) -> None:
    class FromString(Struct, cs=cs):
        a: "uint8[4]"
        b: "uint32"

    assert FromString.__size__ == 8
    assert FromString.__members__["b"].type is cs.uint32


def test_builtin_shadowed_typedef(cs: cstruct) -> None:
    class Shadowed(Struct, cs=cs):
        a: int  # Evaluates to the Python builtin, but must resolve to the cstruct "int" typedef
        b: "int[2]"

    assert Shadowed.__members__["a"].type is cs.resolve("int")
    assert Shadowed.__size__ == 4 + 8


def test_multi_word_typedef(cs: cstruct) -> None:
    class MultiWord(Struct, cs=cs):
        a: "unsigned short"  # noqa: F722
        b: "unsigned long long[2]"  # noqa: F722

    assert MultiWord.__members__["a"].type is cs.uint16
    assert MultiWord.__size__ == 2 + 16


def test_array_syntax_equivalence(cs: cstruct) -> None:
    class ArraySubscript(Struct, cs=cs):
        a: uint8[4]

    class ArrayString(Struct, cs=cs):
        a: "uint8[4]"

    assert ArraySubscript.__size__ == ArrayString.__size__ == 4


def test_multidimensional_array(cs: cstruct) -> None:
    """Test that array dimensions apply from left to right in every syntax, like they do for bound types."""

    class Multi(Struct, cs=cs):
        subscript: uint8[4][2]
        string: "uint8[4][2]"
        name: "DWORD[4][2]"
        bound: cs.uint8[4][2]
        pointers: pointer[uint8][2]
        pointers_string: "DWORD*[2]"

    assert Multi.__members__["subscript"].type is cs.uint8[4][2]
    assert Multi.__members__["string"].type is cs.uint8[4][2]
    assert Multi.__members__["name"].type is cs.uint32[4][2]
    assert Multi.__members__["bound"].type is cs.uint8[4][2]
    assert Multi.__members__["pointers"].type.__num_entries__ == 2
    assert Multi.__members__["pointers"].type.__type__.__type__ is cs.uint8
    assert Multi.__members__["pointers_string"].type.__num_entries__ == 2
    assert Multi.__members__["pointers_string"].type.__type__.__type__ is cs.uint32


def test_dynamic_array(cs: cstruct) -> None:
    """Test arrays with a size that refers to another field, null-terminated arrays and arrays up to the end."""

    class Dynamic(Struct, cs=cs):
        size: uint8
        data: uint8["size"]
        string: "uint8[size]"
        text: "char[]"  # noqa: F722
        rest: char[EOF]

    data = b"\x02ab" + b"cd" + b"hi\x00" + b"KUSJESVANSRT <3"
    obj = Dynamic(data)
    assert obj.data == [0x61, 0x62]
    assert obj.string == [0x63, 0x64]
    assert obj.text == b"hi"
    assert obj.rest == b"KUSJESVANSRT <3"
    assert obj.dumps() == data


def test_float_types(cs: cstruct) -> None:
    class Floats(Struct, cs=cs):
        half: float16
        single: float
        precise: double
        samples: float[4]

    assert Floats.__members__["half"].type is cs.float16
    assert Floats.__members__["single"].type is cs.float
    assert Floats.__members__["precise"].type is cs.double
    assert Floats.__size__ == 2 + 4 + 8 + (4 * 4)


def test_char_and_bytes(cs: cstruct) -> None:
    class Named(Struct, cs=cs):
        name: char[8]
        value: uint32

    assert Named.__size__ == 12

    obj = Named(b"hello\x00\x00\x00" + (1).to_bytes(4, "little"))
    assert obj.name == b"hello\x00\x00\x00"
    assert obj.value == 1


def test_endian(cs: cstruct) -> None:
    big = cstruct(endian=">")

    class BigEndian(Struct, cs=big):
        a: uint32

    obj = BigEndian((1).to_bytes(4, "big"))
    assert obj.a == 1


def test_annotations_without_future_import(cs: cstruct) -> None:
    """Test annotations that Python evaluates itself, eagerly or (since Python 3.14) lazily."""
    source = """
    class Plain(Struct, cs=cs):
        a: uint8[4]
        b: pointer["Plain"]
    """
    namespace = {"Struct": Struct, "uint8": uint8, "pointer": pointer, "cs": cs}
    exec(compile(dedent(source), "<test>", "exec", dont_inherit=True), namespace)

    assert list(namespace["Plain"].__members__.keys()) == ["a", "b"]
    assert namespace["Plain"].__size__ == 4 + cs.pointer.__size__


def test_unsupported_annotation(cs: cstruct) -> None:
    with pytest.raises(TypeError, match="Unsupported field annotation"):

        class Invalid(Struct, cs=cs):
            a: 1234


def test_isinstance_parity_struct(cs: cstruct) -> None:
    class Declarative(Struct, cs=cs):
        magic: uint8[4]
        version: uint32

    cs.load("struct Normal { uint8 magic[4]; uint32 version; };")
    Normal = cs.Normal

    # Declarative structures use the regular metaclass, so all type checks behave identically.
    assert isinstance(Declarative, StructureMetaType)
    assert isinstance(Normal, StructureMetaType)
    assert issubclass(Declarative, Structure)
    assert issubclass(Normal, Structure)
    assert type(Declarative) is type(Normal)

    # Compiled like structures in a definition
    assert Declarative.__compiled__
    assert Normal.__compiled__

    data = b"ABCD" + (1).to_bytes(4, "little")
    declarative_obj = Declarative(data)
    normal_obj = Normal(data)

    assert isinstance(declarative_obj, Structure)
    assert isinstance(normal_obj, Structure)
    assert isinstance(declarative_obj, Declarative)


def test_isinstance_parity_union(cs: cstruct) -> None:
    class DeclarativeUnion(Union, cs=cs):
        as_u32: uint32
        as_bytes: uint8[4]

    assert isinstance(DeclarativeUnion, UnionMetaType)
    assert isinstance(DeclarativeUnion, StructureMetaType)
    assert issubclass(DeclarativeUnion, CUnion)
    assert issubclass(DeclarativeUnion, Structure)

    obj = DeclarativeUnion(b"\x01\x00\x00\x00")
    assert isinstance(obj, CUnion)
    assert isinstance(obj, DeclarativeUnion)


def test_declarative_usable_in_c_definition(cs: cstruct) -> None:
    class Inner(Struct, cs=cs):
        magic: uint8[4]
        version: uint32

    # A declarative struct can be referenced from a regular C-style definition and read back.
    cs.load("struct Outer { Inner inner; uint32 tail; };")

    obj = cs.Outer(b"ABCD" + (7).to_bytes(4, "little") + (9).to_bytes(4, "little"))
    assert isinstance(obj.inner, Inner)
    assert obj.inner.version == 7
    assert obj.tail == 9
