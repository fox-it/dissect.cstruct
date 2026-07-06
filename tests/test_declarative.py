from __future__ import annotations

from typing import Annotated

import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.declarative import (
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
    assert Basic.size == 8
    assert list(Basic.fields) == ["magic", "version"]

    obj = Basic(b"ABCD" + (2).to_bytes(4, "little"))
    assert bytes(obj.magic) == b"ABCD"
    assert obj.version == 2


def test_cross_reference() -> None:
    class CRHeader(Struct):
        magic: uint8[4]
        version: uint32

    class CRFile(Struct):
        header: CRHeader
        size: uint64

    assert CRFile.size == 16
    assert CRFile.fields["header"].type is CRHeader

    obj = CRFile(b"ABCD" + (1).to_bytes(4, "little") + (123).to_bytes(8, "little"))
    assert bytes(obj.header.magic) == b"ABCD"
    assert obj.header.version == 1
    assert obj.size == 123


def test_bound_keyword(cs: cstruct) -> None:
    class Bound(Struct, cs=cs):
        a: uint32
        b: uint8[4]

    assert Bound.cs is cs
    assert cs.Bound is Bound
    assert Bound.size == 8


def test_base_inheritance(cs: cstruct) -> None:
    class Base(Struct, cs=cs):
        pass

    class Child(Base):
        a: uint32

    assert Child.cs is cs
    assert cs.Child is Child


def test_field_inheritance(cs: cstruct) -> None:
    class Header(Struct, cs=cs):
        magic: uint8[4]
        version: uint32

    class Extended(Header):
        flags: uint16

    assert list(Extended.fields) == ["magic", "version", "flags"]
    assert Extended.size == Header.size + 2
    # The parent is unchanged
    assert list(Header.fields) == ["magic", "version"]
    assert Header.size == 8

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


def test_self_referential_pointer(cs: cstruct) -> None:
    class Node(Struct, cs=cs):
        data: uint32
        next: pointer["Node"]

    assert issubclass(Node.fields["next"].type, Pointer)
    assert Node.fields["next"].type.type is Node
    assert Node.size == 4 + cs.pointer.size


def test_self_referential_pointer_string(cs: cstruct) -> None:
    class Node(Struct, cs=cs):
        data: uint32
        next: "Node*"  # noqa: F722

    assert issubclass(Node.fields["next"].type, Pointer)
    assert Node.fields["next"].type.type is Node


def test_self_referential_embed(cs: cstruct) -> None:
    with pytest.raises(TypeError, match="embeds incomplete type 'Recursive'"):

        class Recursive(Struct, cs=cs):
            inner: Recursive

    # The failed class must not remain registered
    assert "Recursive" not in cs.types

    with pytest.raises(TypeError, match="embeds incomplete type 'RecursiveArray'"):

        class RecursiveArray(Struct, cs=cs):
            inner: "RecursiveArray[2]"

    assert "RecursiveArray" not in cs.types


def test_inferred_cstruct() -> None:
    class Inferred(Struct):
        a: module_cs.uint32
        b: module_cs.uint8[4]

    assert Inferred.cs is module_cs


def test_align_keyword(cs: cstruct) -> None:
    class Packed(Struct, cs=cs):
        a: uint8
        b: uint32

    class Aligned(Struct, cs=cs, align=True):
        a: uint8
        b: uint32

    assert Packed.size == 5
    assert Aligned.size == 8
    assert Aligned.fields["b"].offset == 4


def test_align_attribute(cs: cstruct) -> None:
    class Aligned(Struct, cs=cs):
        __align__ = True

        a: uint8
        b: uint32

    assert Aligned.size == 8


def test_field_bits(cs: cstruct) -> None:
    class Bits(Struct, cs=cs):
        a: field(uint16, bits=4)
        b: field(uint16, bits=4)

    assert Bits.size == 2
    assert Bits.fields["a"].bits == 4


def test_field_offset(cs: cstruct) -> None:
    class Offset(Struct, cs=cs):
        a: uint32
        b: field(uint32, offset=0x10)

    assert Offset.size == 0x14
    assert Offset.fields["b"].offset == 0x10


def test_field_annotated_bits(cs: cstruct) -> None:
    class Bits(Struct, cs=cs):
        a: Annotated[uint16, field(bits=4)]
        b: Annotated[uint16, field(bits=4)]

    assert Bits.size == 2
    assert Bits.fields["a"].bits == 4
    assert Bits.fields["b"].bits == 4


def test_field_annotated_offset(cs: cstruct) -> None:
    class Offset(Struct, cs=cs):
        a: uint32
        b: Annotated[uint32, field(offset=0x10)]

    assert Offset.size == 0x14
    assert Offset.fields["b"].offset == 0x10


def test_field_annotated_forward_ref(cs: cstruct) -> None:
    class Fwd(Struct, cs=cs):
        a: Annotated["uint16", field(bits=4)]
        b: Annotated["uint16", "some metadata"]

    assert Fwd.size == 2 + 2
    assert Fwd.fields["a"].bits == 4
    assert Fwd.fields["b"].type is cs.uint16


def test_annotated_without_field(cs: cstruct) -> None:
    class Plain(Struct, cs=cs):
        a: Annotated[uint32, "some metadata"]

    assert Plain.size == 4
    assert Plain.fields["a"].type is cs.uint32


def test_union(cs: cstruct) -> None:
    class Value(Union, cs=cs):
        as_u32: uint32
        as_bytes: uint8[4]

    assert Value.size == 4
    assert cs.Value is Value

    obj = Value(b"\x01\x00\x00\x00")
    assert obj.as_u32 == 1
    assert bytes(obj.as_bytes) == b"\x01\x00\x00\x00"


def test_pointer(cs: cstruct) -> None:
    class WithPointer(Struct, cs=cs):
        ptr: pointer[uint32]

    assert issubclass(WithPointer.fields["ptr"].type, Pointer)
    assert WithPointer.fields["ptr"].type.type is cs.uint32


def test_pointer_inferred_cstruct() -> None:
    class InferredPointer(Struct):
        ptr: pointer[module_cs.uint32]

    assert InferredPointer.cs is module_cs
    assert InferredPointer.fields["ptr"].type.type is module_cs.uint32


def test_field_spec_reuse(cs: cstruct) -> None:
    spec = field("uint16", bits=4)

    class First(Struct, cs=cs):
        a: spec

    class Second(Struct, cs=cs):
        a: spec

    # The shared FieldSpec must not be mutated by class creation
    assert spec.type == "uint16"
    assert First.fields["a"].bits == Second.fields["a"].bits == 4


def test_string_annotation(cs: cstruct) -> None:
    class FromString(Struct, cs=cs):
        a: "uint8[4]"
        b: "uint32"

    assert FromString.size == 8
    assert FromString.fields["b"].type is cs.uint32


def test_builtin_shadowed_typedef(cs: cstruct) -> None:
    class Shadowed(Struct, cs=cs):
        a: int  # Evaluates to the Python builtin, but must resolve to the cstruct "int" typedef
        b: "int[2]"

    assert Shadowed.fields["a"].type is cs.resolve("int")
    assert Shadowed.size == 4 + 8


def test_multi_word_typedef(cs: cstruct) -> None:
    class MultiWord(Struct, cs=cs):
        a: "unsigned short"  # noqa: F722
        b: "unsigned long long[2]"  # noqa: F722

    assert MultiWord.fields["a"].type is cs.uint16
    assert MultiWord.size == 2 + 16


def test_array_syntax_equivalence(cs: cstruct) -> None:
    class ArraySubscript(Struct, cs=cs):
        a: uint8[4]

    class ArrayString(Struct, cs=cs):
        a: "uint8[4]"

    assert ArraySubscript.size == ArrayString.size == 4


def test_float_types(cs: cstruct) -> None:
    class Floats(Struct, cs=cs):
        half: float16
        single: float
        precise: double
        samples: float[4]

    assert Floats.fields["half"].type is cs.float16
    assert Floats.fields["single"].type is cs.float
    assert Floats.fields["precise"].type is cs.double
    assert Floats.size == 2 + 4 + 8 + (4 * 4)


def test_char_and_bytes(cs: cstruct) -> None:
    class Named(Struct, cs=cs):
        name: char[8]
        value: uint32

    assert Named.size == 12

    obj = Named(b"hello\x00\x00\x00" + (1).to_bytes(4, "little"))
    assert obj.name == b"hello\x00\x00\x00"
    assert obj.value == 1


def test_endian(cs: cstruct) -> None:
    big = cstruct(endian=">")

    class BigEndian(Struct, cs=big):
        a: uint32

    obj = BigEndian((1).to_bytes(4, "big"))
    assert obj.a == 1


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

    # The declarative metaclass subclasses the regular one, so all type checks behave identically.
    assert isinstance(Declarative, StructureMetaType)
    assert isinstance(Normal, StructureMetaType)
    assert issubclass(Declarative, Structure)
    assert issubclass(Normal, Structure)
    assert issubclass(type(Declarative), type(Normal))

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
