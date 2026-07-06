"""Declarative syntax for defining cstruct structures.

This module is an optional convenience layer on top of cstruct. It offers a Pythonic way to declare structures by
subclassing :class:`Struct` (or :class:`Union`) and annotating the fields::

    from dissect.cstruct.declarative import Struct, uint8, uint32, uint64


    class Header(Struct):
        magic: uint8[4]
        version: uint32


    class File(Struct):
        header: Header  # structures can reference each other
        size: uint64

The resulting classes are regular cstruct structures. Each structure is registered in a cstruct instance, which can
be passed as a class keyword argument, together with ``align``::

    cs = cstruct(endian=">")


    class Header(Struct, cs=cs, align=True): ...

Without one, a structure uses the cstruct instance of the first bound type or structure in its annotations, or a new
cstruct instance. To reuse the same options for many structures, subclass a base class without fields that has them::

    class Base(Struct, cs=cs):
        pass


    class Header(Base): ...

A field annotation can be any of the following:

* A type of this module, e.g. ``uint32``, ``uint8[4]``, ``uint8["size"]``, ``char[EOF]`` or ``pointer[uint32]``.
* A bound cstruct type, e.g. ``cs.uint32`` or ``cs.uint8[4]``.
* Another structure, e.g. ``Header``.
* The name of a cstruct type as a string, optionally followed by pointers and array dimensions, e.g. ``"DWORD*[4]"``.
* A :func:`field` for bit fields and explicit offsets, e.g. ``field(uint16, bits=4)``. For type checkers, use it
  as :data:`typing.Annotated` metadata instead, e.g. ``Annotated[uint16, field(bits=4)]``.

A structure can point to itself (``next: pointer["Node"]``), but not embed itself. A subclass of a structure starts
with the fields of its parent.

Field annotations are evaluated at runtime. Projects using Ruff's ``flake8-type-checking`` (``TC``) rules should add
:class:`Struct` and :class:`Union` to the runtime-evaluated base classes, so that imports only used in field
annotations are not moved into a ``TYPE_CHECKING`` block::

    [tool.ruff.lint.flake8-type-checking]
    runtime-evaluated-base-classes = ["dissect.cstruct.declarative.Struct", "dissect.cstruct.declarative.Union"]
"""

from __future__ import annotations

import ast
import sys
from typing import TYPE_CHECKING, Annotated, Any, BinaryIO, ForwardRef, get_args, get_origin

from dissect.cstruct import compiler
from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.types.base import BaseArray, MetaType
from dissect.cstruct.types.structure import Field
from dissect.cstruct.types.structure import Structure as _Structure
from dissect.cstruct.types.structure import Union as _Union


class _Ref:
    """Base class for type references, which are resolved against the cstruct instance of a structure."""

    __slots__ = ()

    def __call__(self, *args, **kwargs) -> Any:
        # Python 3.10 only allows callables as the type of typing.Annotated
        raise TypeError(f"{self!r} is a type reference and cannot be instantiated")

    def __getitem__(self, count: int | str | None) -> ArrayRef:
        """Support the ``uint8[4]`` array syntax."""
        return ArrayRef(self, count)

    def _resolve(self, cs: cstruct) -> type:
        raise NotImplementedError


class TypeRef(_Ref):
    """A reference to a cstruct type by name, e.g. :data:`uint32`."""

    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def _resolve(self, cs: cstruct) -> type:
        return cs.resolve(self.name)

    def __repr__(self) -> str:
        return f"<TypeRef {self.name}>"


class ArrayRef(_Ref):
    """A reference to an array of a type."""

    __slots__ = ("count", "type")

    def __init__(self, type_: Any, count: int | str | None):
        self.type = type_
        self.count = count

    def _resolve(self, cs: cstruct) -> type:
        return _resolve_type(self.type, cs)[self.count]

    def __repr__(self) -> str:
        return f"<ArrayRef {self.type!r}[{self.count}]>"


class PointerRef(_Ref):
    """A reference to a pointer to a type."""

    __slots__ = ("type",)

    def __init__(self, type_: Any):
        self.type = type_

    def _resolve(self, cs: cstruct) -> type:
        return cs._make_pointer(_resolve_type(self.type, cs))

    def __repr__(self) -> str:
        return f"<PointerRef {self.type!r}>"


class _PointerFactory:
    """Factory for the ``pointer[type]`` syntax."""

    def __getitem__(self, item: Any) -> PointerRef:
        return PointerRef(item)


class FieldSpec:
    """A field with a bit size or explicit offset. See :func:`field`."""

    __slots__ = ("bits", "offset", "type")

    def __init__(self, type_: Any = None, bits: int | None = None, offset: int | None = None):
        self.type = type_
        self.bits = bits
        self.offset = offset


def field(type_: Any = None, *, bits: int | None = None, offset: int | None = None) -> FieldSpec:
    """Describe a bit field or a field at an explicit offset.

    For example::

        class Example(Struct):
            flags: field(uint16, bits=4)
            tail: field(uint32, offset=0x10)

    For type checkers, omit the type and use it as :data:`typing.Annotated` metadata instead::

        class Example(Struct):
            flags: Annotated[uint16, field(bits=4)]
            tail: Annotated[uint32, field(offset=0x10)]

    Args:
        type_: The field type. Omitted when used as :data:`typing.Annotated` metadata.
        bits: The amount of bits for a bit field.
        offset: The offset of the field within the structure.
    """
    return FieldSpec(type_, bits=bits, offset=offset)


if TYPE_CHECKING:
    from typing import TypeVar

    _T = TypeVar("_T")

    # For type checkers, the types are subclasses of their Python counterpart, so that ``version: uint32`` and
    # ``magic: uint8[4]`` are valid type expressions. At runtime they are type references.
    class _int(int):
        __slots__ = ()

        def __class_getitem__(cls, count: Any) -> type[list[int]]: ...

    class _bytes(bytes):
        __slots__ = ()

        def __class_getitem__(cls, count: Any) -> type[bytes]: ...

    class _str(str):
        __slots__ = ()

        def __class_getitem__(cls, count: Any) -> type[str]: ...

    _builtin_float = float

    class _float(_builtin_float):
        __slots__ = ()

        def __class_getitem__(cls, count: Any) -> type[list[_builtin_float]]: ...

    class uint8(_int): ...

    class uint16(_int): ...

    class uint24(_int): ...

    class uint32(_int): ...

    class uint48(_int): ...

    class uint64(_int): ...

    class uint128(_int): ...

    class int8(_int): ...

    class int16(_int): ...

    class int24(_int): ...

    class int32(_int): ...

    class int48(_int): ...

    class int64(_int): ...

    class int128(_int): ...

    class uleb128(_int): ...

    class ileb128(_int): ...

    class float16(_float): ...

    class float(_float): ...

    class double(_float): ...

    class char(_bytes): ...

    class wchar(_str): ...

    void = None

    class pointer:
        def __class_getitem__(cls, item: type[_T]) -> type[_T]: ...
else:
    pointer = _PointerFactory()

    uint8 = TypeRef("uint8")
    uint16 = TypeRef("uint16")
    uint24 = TypeRef("uint24")
    uint32 = TypeRef("uint32")
    uint48 = TypeRef("uint48")
    uint64 = TypeRef("uint64")
    uint128 = TypeRef("uint128")

    int8 = TypeRef("int8")
    int16 = TypeRef("int16")
    int24 = TypeRef("int24")
    int32 = TypeRef("int32")
    int48 = TypeRef("int48")
    int64 = TypeRef("int64")
    int128 = TypeRef("int128")

    uleb128 = TypeRef("uleb128")
    ileb128 = TypeRef("ileb128")

    float16 = TypeRef("float16")
    float = TypeRef("float")
    double = TypeRef("double")

    char = TypeRef("char")
    wchar = TypeRef("wchar")
    void = TypeRef("void")

# An array count that reads until the end of the stream, like ``char data[EOF]`` in a definition
EOF = "EOF"


def _get_annotations(cls: type) -> dict[str, Any]:
    """Return the annotations defined on the class itself, as strings or (with Python < 3.14) objects."""
    if sys.version_info >= (3, 14):
        import annotationlib  # novermin

        # The string format doesn't fail on forward references. They are evaluated like the strings of
        # ``from __future__ import annotations``.
        return annotationlib.get_annotations(cls, format=annotationlib.Format.STRING)  # novermin
    return cls.__dict__.get("__annotations__", {})


def _eval(annotation: Any, globalns: dict[str, Any], localns: dict[str, Any]) -> Any:
    """Evaluate a string annotation.

    A string that isn't valid Python or uses names that aren't defined in the scope of the structure, such as
    ``"unsigned short"``, ``"DWORD"`` or ``"int"``, is returned as is, to be resolved as the name of a cstruct type.
    """
    if not isinstance(annotation, str):
        return annotation

    try:
        expression = ast.parse(annotation, mode="eval")
    except SyntaxError:
        return annotation

    # Checked instead of catching a NameError, because the builtins (e.g. ``int``) must not be used
    names = (node.id for node in ast.walk(expression) if isinstance(node, ast.Name))
    if any(name not in localns and name not in globalns for name in names):
        return annotation

    return eval(compile(expression, "<annotation>", "eval"), globalns, localns)


def _parse_annotation(annotation: Any, globalns: dict[str, Any], localns: dict[str, Any]) -> FieldSpec:
    annotation = _eval(annotation, globalns, localns)

    if isinstance(annotation, FieldSpec):
        spec = annotation
    elif get_origin(annotation) is Annotated:
        type_, *metadata = get_args(annotation)
        if isinstance(type_, ForwardRef):
            # E.g. Annotated["uint16", ...]
            type_ = type_.__forward_arg__
        spec = next((meta for meta in metadata if isinstance(meta, FieldSpec)), FieldSpec())
        spec = FieldSpec(type_, bits=spec.bits, offset=spec.offset)
    else:
        spec = FieldSpec(annotation)

    # A new FieldSpec, because a field() can be shared between structures
    return FieldSpec(_eval(spec.type, globalns, localns), bits=spec.bits, offset=spec.offset)


def _bound_cs(type_: Any) -> cstruct | None:
    while isinstance(type_, (ArrayRef, PointerRef)):
        type_ = type_.type
    return type_.__cs__ if isinstance(type_, MetaType) else None


def _resolve_string(text: str, cs: cstruct) -> type:
    """Resolve the name of a cstruct type, optionally followed by pointers and array dimensions.

    Array dimensions are applied from left to right, like the subscript syntax. So ``"uint8[4][2]"`` is the same as
    ``cs.uint8[4][2]``: two arrays of four ``uint8``. An empty dimension is a null-terminated array.
    """
    text = text.strip()

    counts = []
    while text.endswith("]"):
        text, _, count = text[:-1].rpartition("[")
        counts.insert(0, count.strip() or None)
        text = text.rstrip()

    type_ = cs.resolve(text.rstrip("* "))
    for _ in range(text.count("*")):
        type_ = cs._make_pointer(type_)
    for count in counts:
        type_ = type_[count]

    return type_


def _resolve_type(type_: Any, cs: cstruct) -> type:
    if isinstance(type_, MetaType):
        return type_

    if isinstance(type_, _Ref):
        return type_._resolve(cs)

    if isinstance(type_, str):
        return _resolve_string(type_, cs)

    raise TypeError(f"Unsupported field annotation: {type_!r}")


def _resolve_field(cls: type, name: str, spec: FieldSpec) -> Field:
    type_ = _resolve_type(spec.type, cls.__cs__)

    embedded = type_
    while issubclass(embedded, BaseArray):
        embedded = embedded.__type__
    if embedded is cls:
        raise TypeError(f"Field {name!r} embeds {cls.__name__!r} in itself, use a pointer instead")

    return Field(name, type_, spec.bits, spec.offset)


class _Declarative:
    """Turns an annotated subclass of :class:`Struct` or :class:`Union` into a cstruct structure."""

    __align__ = False
    __anonymous__ = False

    def __init_subclass__(cls, *, cs: cstruct | None = None, align: bool | None = None, **kwargs):
        super().__init_subclass__(**kwargs)

        if cs is not None:
            cls.__cs__ = cs
        if align is not None:
            cls.__align__ = align

        # The scope of the class statement, skipping StructureMetaType.__new__. Its locals are needed to evaluate
        # annotations that refer to other structures defined in a function.
        frame = sys._getframe(2)
        localns = {**frame.f_locals, **vars(cls)}
        specs = {
            name: _parse_annotation(annotation, frame.f_globals, localns)
            for name, annotation in _get_annotations(cls).items()
        }

        fields = [
            Field(inherited.name, inherited.type, inherited.bits, inherited.offset)
            for base in cls.__bases__
            for inherited in getattr(base, "__fields__", [])
        ]
        if not specs and not fields:
            # A base class that only has options for its subclasses
            return

        if (cs := getattr(cls, "__cs__", None)) is None:
            cs = cls.__cs__ = next(filter(None, map(_bound_cs, (spec.type for spec in specs.values()))), None)
        if cs is None:
            cs = cls.__cs__ = cstruct()

        # Register the class without fields first, so that it can point to itself
        cls.__fields__ = []
        cls.commit()
        cs.add_type(cls.__name__, cls)

        try:
            cls.__fields__ = fields + [_resolve_field(cls, name, spec) for name, spec in specs.items()]
            cls.commit()
        except Exception:
            # Don't leave a structure without its fields registered
            del cs.types[cls.__name__]
            vars(cs).pop(cls.__name__, None)
            raise

        compiler.compile_structure(cls)

    if TYPE_CHECKING:

        def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO | None = ..., /, **kwargs) -> None: ...


class Struct(_Declarative, _Structure):
    """Base class for declarative structures.

    For example::

        class Header(Struct):
            magic: uint8[4]
            version: uint32

    The class keyword arguments are ``cs`` and ``align``. See :mod:`dissect.cstruct.declarative`.
    """


class Union(_Declarative, _Union):
    """Base class for declarative unions. See :class:`Struct`."""
