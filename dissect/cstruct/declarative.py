"""Declarative syntax for defining cstruct structures.

This module is an optional convenience layer on top of the existing cstruct. It only offers an alternative,
Pythonic way to declare structures by subclassing a base class and using type annotations.

Easy usage (no cstruct instance needed):
    >>> from dissect.cstruct.declarative import Struct, uint8, uint32, uint64
    >>>
    >>> class Header(Struct):
    ...     magic: uint8[4]
    ...     version: uint32
    >>> class File(Struct):
    ...     header: Header  # structs can reference each other
    ...     size: uint64

Subclassing :class:`Struct` (or :class:`Union`) without any extra arguments gives each structure its own,
automatically created cstruct instance. A structure that references another (by annotation) is co-located
onto that structure's instance, so related types share a namespace while unrelated ones stay isolated.

Advanced usage (bind to your own cstruct instance):
    >>> from dissect.cstruct import cstruct
    >>> from dissect.cstruct.declarative import Struct
    >>>
    >>> cs = cstruct(endian=">")
    >>>
    >>> class Header(Struct, cs=cs):
    ...     magic: uint8[4]
    ...     version: uint32

The cstruct instance (and the ``align`` option) can be passed as class keyword arguments. To
reuse the same options for many structures, subclass a bare base that carries them::

    class Base(Struct, cs=cs):
        pass


    class Header(Base): ...

The annotations may be any of the following:

* A bound cstruct type, e.g. ``cs.uint32`` or ``cs.uint8[4]``.
* An (unbound) type reference from this module, e.g. ``uint32`` or ``uint8[4]``.
* Another declarative structure. It is embedded directly by reference, so it may belong to a different
  cstruct instance (a structure that references another is otherwise co-located onto that instance).
* A string containing a cstruct type name, e.g. ``"uint8[4]"``.
* A :func:`field` specification for advanced options such as bit fields or explicit offsets, either
  directly (``field(uint16, bits=4)``) or, for a type-checker-friendly spelling, as
  :data:`typing.Annotated` metadata (``Annotated[uint16, field(bits=4)]``).

A structure may reference itself through a pointer (``next: pointer["Node"]`` or ``next: "Node*"``);
directly embedding a structure in itself is an error. Subclassing a concrete structure extends it:
the subclass inherits the fields of its parent, followed by its own.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Annotated, Any, BinaryIO, ForwardRef

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.types.base import BaseArray, MetaType
from dissect.cstruct.types.structure import Field
from dissect.cstruct.types.structure import Structure as _Structure
from dissect.cstruct.types.structure import StructureMetaType as _StructureMetaType
from dissect.cstruct.types.structure import Union as _Union
from dissect.cstruct.types.structure import UnionMetaType as _UnionMetaType


class _Ref:
    """Base class for unbound, cstruct-instance-agnostic type references.

    A reference is resolved against a concrete :class:`~dissect.cstruct.cstruct.cstruct` instance at the
    moment a structure is declared. This allows references such as :data:`uint32` to be shared across cstruct
    instances instead of being bound to a single one.
    """

    __slots__ = ()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Unbound references cannot be instantiated.

        Defining ``__call__`` nevertheless makes references pass typing's ``callable()`` check, so that
        e.g. ``Annotated[uint16, ...]`` also works on Python 3.10.
        """
        raise TypeError(f"{self!r} is an unbound type reference and cannot be instantiated")

    def _resolve(self, cs: cstruct) -> type:
        raise NotImplementedError


class TypeRef(_Ref):
    """An unbound reference to a named cstruct type, e.g. :data:`uint32`."""

    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def __getitem__(self, count: int | str | None) -> ArrayRef:
        """Support ``uint8[4]`` array syntax."""
        return ArrayRef(self, count)

    def _resolve(self, cs: cstruct) -> type:
        return cs.resolve(self.name)

    def __repr__(self) -> str:
        return f"<TypeRef {self.name}>"


class ArrayRef(_Ref):
    """An unbound reference to an array of a (bound or unbound) type."""

    __slots__ = ("count", "type")

    def __init__(self, type_: Any, count: int | str | None):
        self.type = type_
        self.count = count

    def _resolve(self, cs: cstruct) -> type:
        inner = _resolve_type(self.type, cs)
        return inner[self.count]

    def __repr__(self) -> str:
        return f"<ArrayRef {self.type!r}[{self.count}]>"


class PointerRef(_Ref):
    """An unbound reference to a pointer to a (bound or unbound) type."""

    __slots__ = ("type",)

    def __init__(self, type_: Any):
        self.type = type_

    def _resolve(self, cs: cstruct) -> type:
        return cs._make_pointer(_resolve_type(self.type, cs))

    def __repr__(self) -> str:
        return f"<PointerRef {self.type!r}>"


class _PointerFactory:
    """Factory enabling the ``pointer[type]`` syntax."""

    def __getitem__(self, item: Any) -> PointerRef:
        return PointerRef(item)


class FieldSpec:
    """An advanced field specification, allowing bit fields and explicit offsets.

    See :func:`field`.
    """

    __slots__ = ("bits", "offset", "type")

    def __init__(self, type_: Any = None, bits: int | None = None, offset: int | None = None):
        self.type = type_
        self.bits = bits
        self.offset = offset


def field(type_: Any = None, *, bits: int | None = None, offset: int | None = None) -> FieldSpec:
    """Describe a structure field with advanced options.

    Use this in an annotation when a plain type is not enough, for example to define a bit field or to
    pin a field to a specific offset::

        class Example(Struct):
            flags: field(uint16, bits=4)
            tail: field(uint32, offset=0x10)

    For a fully type-checker-friendly spelling, omit the type here and attach the specification as
    :data:`typing.Annotated` metadata instead::

        class Example(Struct):
            flags: Annotated[uint16, field(bits=4)]
            tail: Annotated[uint32, field(offset=0x10)]

    Args:
        type_: The field type. May be omitted when used as :data:`typing.Annotated` metadata, in which
            case the type is taken from the annotation.
        bits: The amount of bits for a bit field.
        offset: The explicit offset of the field within the structure.
    """
    return FieldSpec(type_, bits=bits, offset=offset)


if TYPE_CHECKING:
    from typing import TypeVar

    _T = TypeVar("_T")

    # Static-only definitions. At runtime these names are bound to the reference objects that the metaclass resolves.
    # Here they are given plain, type-checker-friendly meanings so that annotations such as ``version: uint32`` or
    # ``magic: uint8[4]`` are valid type expressions and hover with a sensible type. The scalar types are
    # (subscriptable) subclasses of their Python counterpart so that both ``uint32`` and the array form ``uint8[4]``
    # type-check cleanly.
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


# Namespace used to evaluate stringified annotations
_EVAL_NS = {
    "pointer": pointer,
    "field": field,
    "Annotated": Annotated,
    "TypeRef": TypeRef,
    "uint8": uint8,
    "uint16": uint16,
    "uint24": uint24,
    "uint32": uint32,
    "uint48": uint48,
    "uint64": uint64,
    "uint128": uint128,
    "int8": int8,
    "int16": int16,
    "int24": int24,
    "int32": int32,
    "int48": int48,
    "int64": int64,
    "int128": int128,
    "float16": float16,
    "float": float,
    "double": double,
    "char": char,
    "wchar": wchar,
    "void": void,
    "uleb128": uleb128,
    "ileb128": ileb128,
}


def _resolve_string(text: str, cs: cstruct) -> type:
    """Resolve a C-style type expression such as ``uint8``, ``uint8[4]`` or ``char *``.

    Only the lightweight ``*`` pointer and ``[count]`` array suffixes are handled here.
    Anything more elaborate should use a bound cstruct type.
    """
    text = text.strip()

    # Peel off trailing array dimensions right-to-left (innermost first), e.g. ``uint8[4][2]``. They are
    # reapplied in the same order below, which reproduces the C-style nesting. An empty ``[]`` dimension
    # becomes a dynamic (null-terminated) array, matching cstruct's C-style parser.
    counts: list[str] = []
    while text.endswith("]"):
        start = text.rindex("[")
        counts.append(text[start + 1 : -1].strip())
        text = text[:start].strip()

    # Peel off pointer stars one at a time so ``uint8**`` counts as two pointers.
    pointers = 0
    while text[:1] == "*" or text[-1:] == "*":
        text = text[1:] if text.startswith("*") else text[:-1]
        text = text.strip()
        pointers += 1

    type_ = cs.resolve(text)
    for _ in range(pointers):
        type_ = cs._make_pointer(type_)
    for count in counts:
        type_ = type_[count or None]

    return type_


def _resolve_type(annotation: Any, cs: cstruct) -> type:
    if isinstance(annotation, MetaType):
        return annotation

    if isinstance(annotation, _Ref):
        return annotation._resolve(cs)

    if isinstance(annotation, str):
        return _resolve_string(annotation, cs)

    raise TypeError(f"Unsupported field annotation: {annotation!r}")


def _unwrap_annotated(annotation: Any) -> Any:
    """Turn a :data:`typing.Annotated` annotation into a :class:`FieldSpec` (or its bare type).

    ``Annotated[uint16, field(bits=4)]`` is the type-checker-friendly spelling of ``field(uint16, bits=4)``:
    the underlying type is the first argument and a :func:`field` specification may be attached as
    metadata. Annotations without a :func:`field` marker simply resolve to their underlying type.
    """
    metadata = getattr(annotation, "__metadata__", None)
    if metadata is None:
        return annotation

    underlying = annotation.__origin__
    if isinstance(underlying, ForwardRef):
        # A string inside Annotated (e.g. ``Annotated["uint16", ...]``) becomes a ForwardRef;
        # unwrap it back to the string so it is resolved like any other string annotation.
        underlying = underlying.__forward_arg__

    for meta in metadata:
        if isinstance(meta, FieldSpec):
            return FieldSpec(underlying, bits=meta.bits, offset=meta.offset)
    return underlying


def _maybe_eval(annotation: Any, globalns: dict[str, Any], localns: dict[str, Any]) -> Any:
    """Turn a stringified annotation back into an object, leaving it untouched on failure.

    Under ``from __future__ import annotations`` every annotation is a string, so a reference like
    ``uint8[4]`` arrives as ``"uint8[4]"``. This resolves it much like :func:`typing.get_type_hints` would,
    but per-annotation. Strings that are not valid Python expressions are left as-is; they are still resolved later as
    cstruct type names (e.g. a struct or typedef defined only in the cstruct instance).
    """
    if not isinstance(annotation, str):
        return annotation

    try:
        result = eval(annotation, globalns, localns)
    except Exception:
        return annotation

    if isinstance(result, type) and not isinstance(result, MetaType):
        # The annotation evaluated to a plain Python class, e.g. the builtin ``int`` for an ``int``
        # annotation. Keep the string so it is resolved as a cstruct type name instead (``int``,
        # for example, is a typedef for ``int32``).
        return annotation

    return result


def _infer_cs(annotation: Any) -> cstruct | None:
    if isinstance(annotation, (FieldSpec, ArrayRef, PointerRef)):
        return _infer_cs(annotation.type)
    if isinstance(annotation, MetaType):
        return annotation.cs
    return None


def _find_base_attr(bases: tuple[type, ...], attr: str, default: Any) -> Any:
    for base in bases:
        value = getattr(base, attr, None)
        if value is not None:
            return value
    return default


def _caller_locals() -> dict[str, Any]:
    """Return the local namespace of the scope that is defining the declarative class.

    Module globals already cover top-level structures, but a structure defined inside a function (or a
    forward reference to a sibling defined there) lives in that function's locals. Capturing them lets
    such references resolve to the actual class object.
    """
    frame = sys._getframe(1)
    while frame is not None and frame.f_globals.get("__name__") == __name__:
        frame = frame.f_back
    return dict(frame.f_locals) if frame is not None else {}


def _build_fields(
    classdict: dict[str, Any],
    bases: tuple[type, ...],
    *,
    cs: cstruct | None,
    align: bool | None,
) -> tuple[cstruct, list[tuple[str, Any]]] | None:
    """Evaluate the annotations of a declarative class and determine its cstruct instance.

    Returns the cstruct instance and the evaluated (but not yet resolved) annotations. Resolution into
    :class:`Field` objects is deferred to :meth:`_DeclarativeMeta.__new__`, after the class has been
    created and pre-registered, so that self-referential pointers can resolve.
    """
    annotations = classdict.get("__annotations__")
    if not annotations:
        # Bare base class; remember any explicit options so subclasses inherit them.
        if cs is not None:
            classdict["cs"] = cs
        if align is not None:
            classdict["__align__"] = align
        return None

    module = sys.modules.get(classdict.get("__module__", ""), None)
    # Builtins are deliberately excluded so that names such as ``int`` resolve to the cstruct typedef
    # instead of the Python builtin.
    globalns = {**_EVAL_NS, **getattr(module, "__dict__", {}), "__builtins__": {}}
    localns = {**_caller_locals(), **classdict}

    resolved: list[tuple[str, Any]] = []
    for name, annotation in annotations.items():
        if not isinstance(annotation, FieldSpec):
            annotation = _maybe_eval(annotation, globalns, localns)
            annotation = _unwrap_annotated(annotation)
            if isinstance(annotation, str):
                # E.g. a forward reference unwrapped from Annotated["uint16", ...]
                annotation = _maybe_eval(annotation, globalns, localns)
        if isinstance(annotation, FieldSpec) and isinstance(annotation.type, str):
            annotation = FieldSpec(
                _maybe_eval(annotation.type, globalns, localns), bits=annotation.bits, offset=annotation.offset
            )
        resolved.append((name, annotation))

    # Fields declared on a concrete base class are inherited and precede this class' own fields
    resolved = [*_find_base_attr(bases, "__declarative_fields__", []), *resolved]

    # cstruct resolution order: explicit keyword > bound base > inferred from annotations > new instance
    if cs is None:
        cs = _find_base_attr(bases, "cs", None)

    if cs is None:
        for _, annotation in resolved:
            if (found := _infer_cs(annotation)) is not None:
                cs = found
                break

    if cs is None:
        cs = cstruct()

    if align is None:
        align = classdict.get("__align__", _find_base_attr(bases, "__align__", False))

    classdict["cs"] = cs
    classdict["__align__"] = align
    classdict["__anonymous__"] = False
    classdict["__declarative_fields__"] = resolved

    return cs, resolved


def _resolve_fields(cls: type, annotations: list[tuple[str, Any]], cs: cstruct) -> list[Field]:
    """Resolve evaluated annotations into :class:`Field` objects for the (pre-registered) class."""
    fields = []
    for field_name, annotation in annotations:
        if isinstance(annotation, FieldSpec):
            type_ = _resolve_type(annotation.type, cs)
            bits, offset = annotation.bits, annotation.offset
        else:
            type_ = _resolve_type(annotation, cs)
            bits = offset = None

        # A structure cannot embed itself, self-references must go through a pointer
        embedded = type_
        while isinstance(embedded, MetaType) and issubclass(embedded, BaseArray):
            embedded = embedded.type
        if embedded is cls:
            raise TypeError(
                f"Field {field_name!r} embeds incomplete type {cls.__name__!r}; "
                "self-references must be pointers (e.g. pointer[...] or 'name*')"
            )

        fields.append(Field(field_name, type_, bits, offset))

    return fields


class _DeclarativeMeta:
    """Mixin that turns an annotated :class:`Struct` / :class:`Union` subclass into a cstruct type."""

    def __new__(  # type: ignore
        metacls,
        name: str,
        bases: tuple[type, ...],
        classdict: dict[str, Any],
        *,
        cs: cstruct | None = None,
        align: bool | None = None,
    ):
        prepared = _build_fields(classdict, bases, cs=cs, align=align)
        cls = super().__new__(metacls, name, bases, classdict)

        if prepared is not None:
            resolved_cs, annotations = prepared

            # Register the still-empty class first so that self-referential pointers can resolve
            cls.size = None
            cls.dynamic = True
            cls.alignment = None
            resolved_cs.add_type(name, cls)

            try:
                cls.__fields__ = _resolve_fields(cls, annotations, resolved_cs)
                cls.commit()
            except Exception:
                # Don't leave a half-built type registered
                if resolved_cs.types.get(name) is cls:
                    del resolved_cs.types[name]
                raise

        return cls

    def __init__(cls, name: str, bases: tuple[type, ...], classdict: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(name, bases, classdict)


class _DeclarativeStructMeta(_DeclarativeMeta, _StructureMetaType):
    """Metaclass turning an annotated :class:`Struct` subclass into a cstruct structure."""


class _DeclarativeUnionMeta(_DeclarativeMeta, _UnionMetaType):
    """Metaclass turning an annotated :class:`Union` subclass into a cstruct union."""


class Struct(_Structure, metaclass=_DeclarativeStructMeta):
    """Base class for declarative structures.

    Subclass this and annotate the fields with cstruct types to define a structure::

        class Header(Struct):
            magic: uint8[4]
            version: uint32

    Each structure that is not explicitly bound gets its own cstruct instance, but a structure that
    references another (by annotation) is co-located onto that structure's instance, so related types
    share a namespace while unrelated ones stay isolated. To bind to your own cstruct instance, pass it
    as a class keyword argument::

        class Header(Struct, cs=my_cs): ...

    Supported class keyword arguments are ``cs`` and ``align``.

    A structure may reference itself through a pointer (``next: pointer["Node"]``), and subclassing a
    concrete structure extends it with the parent's fields first.
    """

    if TYPE_CHECKING:

        def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO | None = ..., /, **kwargs: Any) -> None: ...


class Union(_Union, metaclass=_DeclarativeUnionMeta):
    """Base class for declarative unions. See :class:`Struct` for usage."""

    if TYPE_CHECKING:

        def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO | None = ..., /, **kwargs: Any) -> None: ...
