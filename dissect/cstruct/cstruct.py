from __future__ import annotations

import copy
import ctypes as _ctypes
import struct
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, TypeVar, cast

from dissect.cstruct.exception import ResolveError
from dissect.cstruct.expression import Expression
from dissect.cstruct.parser import CStyleParser
from dissect.cstruct.types import (
    LEB128,
    BaseArray,
    BaseType,
    Char,
    Enum,
    Flag,
    Int,
    Packed,
    Pointer,
    Structure,
    Union,
    Void,
    Wchar,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import TypeAlias

    from dissect.cstruct.types import (
        Array,
        Field,
    )


T = TypeVar("T", bound=BaseType)


class cstruct:
    """Main class of cstruct. All types are registered in here.

    Args:
        endian: The endianness to use when parsing.
        pointer: The pointer type to use for pointers.
    """

    DEF_CSTYLE = 1
    DEF_LEGACY = 2

    def __init__(self, load: str = "", *, endian: str = "<", pointer: str | None = None):
        self.endian = endian

        self.consts: dict[str, int | str | bytes] = {}
        self.types: dict[str, type[BaseType]] = {}
        self.includes: list[str] = []

        # fmt: off
        initial_types = {
            # Internal types
            "int8": self._make_packed_type("int8", "b", int),
            "uint8": self._make_packed_type("uint8", "B", int),
            "int16": self._make_packed_type("int16", "h", int),
            "uint16": self._make_packed_type("uint16", "H", int),
            "int32": self._make_packed_type("int32", "i", int),
            "uint32": self._make_packed_type("uint32", "I", int),
            "int64": self._make_packed_type("int64", "q", int),
            "uint64": self._make_packed_type("uint64", "Q", int),
            "float16": self._make_packed_type("float16", "e", float),
            "float": self._make_packed_type("float", "f", float),
            "double": self._make_packed_type("double", "d", float),
            "char": self._make_type("char", (Char,), 1),
            "wchar": self._make_type("wchar", (Wchar,), 2),

            "int24": self._make_int_type("int24", 3, True, alignment=4),
            "uint24": self._make_int_type("uint24", 3, False, alignment=4),
            "int48": self._make_int_type("int48", 6, True, alignment=8),
            "uint48": self._make_int_type("int48", 6, False, alignment=8),
            "int128": self._make_int_type("int128", 16, True, alignment=16),
            "uint128": self._make_int_type("uint128", 16, False, alignment=16),

            "uleb128": self._make_type("uleb128", (LEB128,), None, attrs={"signed": False}),
            "ileb128": self._make_type("ileb128", (LEB128,), None, attrs={"signed": True}),

            "void": self._make_type("void", (Void,), 0),

            # Common C types not covered by internal types
            "signed char": "int8",
            "unsigned char": "char",
            "short": "int16",
            "signed short": "int16",
            "unsigned short": "uint16",
            "int": "int32",
            "signed int": "int32",
            "unsigned int": "uint32",
            "long": "int32",
            "signed long": "int32",
            "unsigned long": "uint32",
            "long long": "int64",
            "signed long long": "int64",
            "unsigned long long": "uint64",

            # Other convenience types
            "u8": "uint8",
            "u16": "uint16",
            "u32": "uint32",
            "u64": "uint64",
            "u128": "uint128",
            "__u8": "uint8",
            "__u16": "uint16",
            "__u32": "uint32",
            "__u64": "uint64",
            "__u128": "uint128",
            "uchar": "uint8",
            "ushort": "uint16",
            "uint": "uint32",
            "ulong": "uint32",

            # Windows types
            "BYTE": "uint8",
            "CHAR": "char",
            "SHORT": "int16",
            "WORD": "uint16",
            "DWORD": "uint32",
            "LONG": "int32",
            "LONG32": "int32",
            "LONG64": "int64",
            "LONGLONG": "int64",
            "QWORD": "uint64",
            "OWORD": "uint128",
            "WCHAR": "wchar",

            "UCHAR": "uint8",
            "USHORT": "uint16",
            "ULONG": "uint32",
            "ULONG64": "uint64",
            "ULONGLONG": "uint64",

            "INT": "int32",
            "INT8": "int8",
            "INT16": "int16",
            "INT32": "int32",
            "INT64": "int64",
            "INT128": "int128",

            "UINT": "uint32",
            "UINT8": "uint8",
            "UINT16": "uint16",
            "UINT32": "uint32",
            "UINT64": "uint64",
            "UINT128": "uint128",

            "__int8": "int8",
            "__int16": "int16",
            "__int32": "int32",
            "__int64": "int64",
            "__int128": "int128",

            "unsigned __int8": "uint8",
            "unsigned __int16": "uint16",
            "unsigned __int32": "uint32",
            "unsigned __int64": "uint64",
            "unsigned __int128": "uint128",

            "wchar_t": "wchar",

            # GNU C types
            "int8_t": "int8",
            "int16_t": "int16",
            "int32_t": "int32",
            "int64_t": "int64",
            "int128_t": "int128",

            "uint8_t": "uint8",
            "uint16_t": "uint16",
            "uint32_t": "uint32",
            "uint64_t": "uint64",
            "uint128_t": "uint128",

            # IDA types
            "_BYTE": "uint8",
            "_WORD": "uint16",
            "_DWORD": "uint32",
            "_QWORD": "uint64",
            "_OWORD": "uint128",
        }
        # fmt: on

        for name, type_ in initial_types.items():
            self.add_type(name, type_)

        pointer = pointer or ("uint64" if sys.maxsize > 2**32 else "uint32")
        self.pointer: type[BaseType] = self.resolve(pointer)
        self._anonymous_count = 0

        if load:
            self.load(load)

    def __getattr__(self, attr: str) -> Any:
        try:
            return self.consts[attr]
        except KeyError:
            pass

        try:
            return self.types[attr]
        except KeyError:
            pass

        raise AttributeError(f"'{type(self).__name__}' object has no attribute {attr!r}")

    def __copy__(self) -> cstruct:
        cs = cstruct(endian=self.endian, pointer=self.pointer.__name__)
        cs._anonymous_count = self._anonymous_count
        cs.includes = self.includes.copy()

        # Update types to point to the new cstruct instance
        for name, type_ in self.types.items():
            new_type = copy.copy(type_)
            new_type.cs = cs
            cs.add_type(name, new_type, replace=True)

        for name, value in self.consts.items():
            cs.add_const(name, value)

        return cs

    def _next_anonymous(self) -> str:
        name = f"__anonymous_{self._anonymous_count}__"
        self._anonymous_count += 1
        return name

    def _add_attr(self, name: str, value: Any) -> None:
        # Names that collide with the cstruct class (e.g. a struct named ``load``) are not set as attributes
        # to avoid breaking the instance. They remain accessible through ``resolve`` and the type dicts.
        if name in _RESERVED_NAMES:
            return
        setattr(self, name, value)

    def add_type(self, name: str, type_: type[BaseType] | str, replace: bool = False) -> None:
        """Add a type or type alias.

        Only use this method when creating type aliases or adding already bound types.
        All types will be resolved to their actual type objects prior to being added.

        Args:
            name: Name of the type to be added.
            type_: The type to be added. Can be a str reference to another type or a compatible type class.
                   If a str is given, it will be resolved to the actual type object.
            replace: Whether to replace the type if it already exists.

        Raises:
            ValueError: If the type already exists.
        """
        typeobj = self.resolve(type_)
        if not replace and (existing := self.types.get(name)) is not None and existing is not typeobj:
            raise ValueError(f"Duplicate type: {name}")

        self.types[name] = typeobj
        self._add_attr(name, typeobj)

    addtype = add_type

    def add_custom_type(
        self, name: str, type_: type[BaseType], size: int | None = None, alignment: int | None = None, **kwargs
    ) -> None:
        """Add a custom type.

        Use this method to add custom types to this cstruct instance. This is largely a convenience method for
        the internal :func:`_make_type` method, which binds a class to this cstruct instance.

        Args:
            name: Name of the type to be added.
            type_: The type to be added.
            size: The size of the type.
            alignment: The alignment of the type.
            **kwargs: Additional attributes to add to the type.
        """
        self.add_type(name, self._make_type(name, (type_,), size, alignment=alignment, attrs=kwargs))

    def add_const(self, name: str, value: Any) -> None:
        """Add a constant value.

        Args:
            name: Name of the constant to be added.
            value: The value of the constant.
        """
        self.consts[name] = value
        self._add_attr(name, value)

    def del_const(self, name: str) -> None:
        """Delete a constant value.

        Args:
            name: Name of the constant to be deleted.

        Raises:
            KeyError: If the constant does not exist.
        """
        del self.consts[name]
        self.__dict__.pop(name, None)

    def load(self, definition: str, deftype: int | None = None, **kwargs) -> cstruct:
        """Parse structures from the given definitions using the given definition type.

        Definitions can be parsed using different parsers. Currently, there's
        only one supported parser - DEF_CSTYLE. Parsers can add types and
        modify this cstruct instance. Arguments can be passed to parsers
        using ``kwargs``.

        Args:
            definition: The definition to parse.
            deftype: The definition type to parse the definitions with.
            **kwargs: Keyword arguments for parsers.
        """
        deftype = deftype or cstruct.DEF_CSTYLE

        if deftype == cstruct.DEF_CSTYLE:
            CStyleParser(self, **kwargs).parse(definition)
        else:
            raise ValueError(f"Unknown definition type: {deftype}")

        return self

    def loadfile(self, path: str, deftype: int | None = None, **kwargs) -> None:
        """Load structure definitions from a file.

        The given path will be read and parsed using the :meth:`~cstruct.load` function.

        Args:
            path: The path to load definitions from.
            deftype: The definition type to parse the definitions with.
            **kwargs: Keyword arguments for parsers.
        """
        with Path(path).open() as fh:
            self.load(fh.read(), deftype, **kwargs)

    def cdef(self) -> str:
        """Render all constants, structure, union, enum and flag definitions back to their C-style definitions.

        Note that the result is semantically equivalent to the original definitions, but not necessarily identical.

        Returns:
            The C-style definitions as a string.
        """
        empty = cstruct()

        blocks = []

        defines = []
        for name, value in self.consts.items():
            if name in empty.consts:
                continue

            defines.append(f"#define {name} {value!r}")

        if defines:
            blocks.append("\n".join(defines))

        for name, typedef in self.types.items():
            if name in empty.types or not isinstance(typedef, type):
                continue

            if not issubclass(typedef, (Structure, Enum, Flag)):
                continue

            if typedef.__name__ == name:
                blocks.append(typedef.cdef())
            else:
                blocks.append(f"typedef {typedef.__name__} {name};")

        return "\n\n".join(blocks)

    def read(self, name: str, stream: BinaryIO) -> Any:
        """Parse data using a given type.

        Args:
            name: Type name to read.
            stream: File-like object or byte string to parse.

        Returns:
            The parsed data.
        """
        return self.resolve(name).read(stream)

    def resolve(self, name: type[BaseType] | str) -> type[BaseType]:
        """Resolve a type name to get the actual type object.

        Types can be referenced using different names. When we want
        the actual type object, we need to resolve these references.

        Args:
            name: Type name to resolve.

        Returns:
            The resolved type object.

        Raises:
            ResolveError: If the type can't be resolved.
        """
        if not isinstance(name, str):
            return name

        try:
            return self.types[name]
        except KeyError:
            raise ResolveError(f"Unknown type {name}") from None

    def copy(self) -> cstruct:
        """Create a copy of this cstruct instance.

        Returns:
            A new cstruct instance with the same types and settings as this one.
        """
        return copy.copy(self)

    def _make_type(
        self,
        name: str,
        bases: Iterable[object],
        size: int | None,
        *,
        alignment: int | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> type[BaseType]:
        """Create a new type class bound to this cstruct instance.

        All types are created using this method. This method automatically binds the type to this cstruct instance.
        """
        attrs = attrs or {}
        attrs.update(
            {
                "cs": self,
                "size": size,
                "dynamic": size is None,
                "alignment": alignment or size,
            }
        )
        return types.new_class(name, bases, {}, lambda ns: ns.update(attrs))

    def _make_array(self, type_: T, num_entries: int | Expression | None) -> type[Array[T]]:
        null_terminated = False
        if num_entries is None:
            null_terminated = True
            size = None
        elif isinstance(num_entries, Expression) or type_.dynamic:
            size = None
        else:
            if type_.size is None:
                raise ValueError(f"Cannot create array of dynamic type: {type_.__name__}")
            size = num_entries * type_.size

        name = f"{type_.__name__}[]" if null_terminated else f"{type_.__name__}[{num_entries}]"

        bases = (type_.ArrayType,)

        attrs = {
            "type": type_,
            "num_entries": num_entries,
            "null_terminated": null_terminated,
        }

        return cast("type[Array]", self._make_type(name, bases, size, alignment=type_.alignment, attrs=attrs))

    def _make_int_type(self, name: str, size: int, signed: bool, *, alignment: int | None = None) -> type[Int]:
        return cast("type[Int]", self._make_type(name, (Int,), size, alignment=alignment, attrs={"signed": signed}))

    def _make_packed_type(self, name: str, packchar: str, base: type, *, alignment: int | None = None) -> type[Packed]:
        return cast(
            "type[Packed]",
            self._make_type(
                name,
                (base, Packed),
                struct.calcsize(packchar),
                alignment=alignment,
                attrs={"packchar": packchar},
            ),
        )

    def _make_enum(self, name: str, type_: type[BaseType], values: dict[str, int]) -> type[Enum]:
        return Enum(self, name, type_, values)

    def _make_flag(self, name: str, type_: type[BaseType], values: dict[str, int]) -> type[Flag]:
        return Flag(self, name, type_, values)

    def _make_pointer(self, target: type[BaseType]) -> type[Pointer]:
        return self._make_type(
            f"{target.__name__}*",
            (Pointer,),
            self.pointer.size,
            alignment=self.pointer.alignment,
            attrs={"type": target},
        )

    def _make_struct(
        self,
        name: str,
        fields: list[Field],
        *,
        align: bool = False,
        anonymous: bool = False,
        base: type[Structure] = Structure,
    ) -> type[Structure]:
        return self._make_type(
            name,
            (base,),
            None,
            attrs={
                "fields": fields,
                "__align__": align,
                "__anonymous__": anonymous,
            },
        )

    def _make_union(
        self, name: str, fields: list[Field], *, align: bool = False, anonymous: bool = False
    ) -> type[Structure]:
        return self._make_struct(name, fields, align=align, anonymous=anonymous, base=Union)

    if TYPE_CHECKING:
        # ruff: noqa: PYI042
        _int = int
        _float = float

        class int8(_int, Packed[_int]): ...

        class uint8(_int, Packed[_int]): ...

        class int16(_int, Packed[_int]): ...

        class uint16(_int, Packed[_int]): ...

        class int32(_int, Packed[_int]): ...

        class uint32(_int, Packed[_int]): ...

        class int64(_int, Packed[_int]): ...

        class uint64(_int, Packed[_int]): ...

        class float16(_float, Packed[_float]): ...

        class float(_float, Packed[_float]): ...

        class double(_float, Packed[_float]): ...

        class char(Char): ...

        class wchar(Wchar): ...

        class int24(Int): ...

        class uint24(Int): ...

        class int48(Int): ...

        class uint48(Int): ...

        class int128(Int): ...

        class uint128(Int): ...

        class uleb128(LEB128): ...

        class ileb128(LEB128): ...

        class void(Void): ...

        # signed char: TypeAlias = int8
        # signed char: TypeAlias = char
        short: TypeAlias = int16
        # signed short: TypeAlias = int16
        # unsigned short: TypeAlias = uint16
        int: TypeAlias = int32
        # signed int: TypeAlias = int32
        # unsigned int: TypeAlias = uint32
        long: TypeAlias = int32
        # signed long: TypeAlias = int32
        # unsigned long: TypeAlias = uint32
        # long long: TypeAlias = int64
        # signed long long: TypeAlias = int64
        # unsigned long long: TypeAlias = uint64

        u8: TypeAlias = uint8
        u16: TypeAlias = uint16
        u32: TypeAlias = uint32
        u64: TypeAlias = uint64
        u128: TypeAlias = uint128
        __u8: TypeAlias = uint8
        __u16: TypeAlias = uint16
        __u32: TypeAlias = uint32
        __u64: TypeAlias = uint64
        __u128: TypeAlias = uint128
        uchar: TypeAlias = uint8
        ushort: TypeAlias = uint16
        uint: TypeAlias = uint32
        ulong: TypeAlias = uint32

        BYTE: TypeAlias = uint8
        CHAR: TypeAlias = char
        SHORT: TypeAlias = int16
        WORD: TypeAlias = uint16
        DWORD: TypeAlias = uint32
        LONG: TypeAlias = int32
        LONG32: TypeAlias = int32
        LONG64: TypeAlias = int64
        LONGLONG: TypeAlias = int64
        QWORD: TypeAlias = uint64
        OWORD: TypeAlias = uint128
        WCHAR: TypeAlias = wchar

        UCHAR: TypeAlias = uint8
        USHORT: TypeAlias = uint16
        ULONG: TypeAlias = uint32
        ULONG64: TypeAlias = uint64
        ULONGLONG: TypeAlias = uint64

        INT: TypeAlias = int32
        INT8: TypeAlias = int8
        INT16: TypeAlias = int16
        INT32: TypeAlias = int32
        INT64: TypeAlias = int64
        INT128: TypeAlias = int128

        UINT: TypeAlias = uint32
        UINT8: TypeAlias = uint8
        UINT16: TypeAlias = uint16
        UINT32: TypeAlias = uint32
        UINT64: TypeAlias = uint64
        UINT128: TypeAlias = uint128

        __int8: TypeAlias = int8
        __int16: TypeAlias = int16
        __int32: TypeAlias = int32
        __int64: TypeAlias = int64
        __int128: TypeAlias = int128

        # unsigned __int8: TypeAlias = uint8
        # unsigned __int16: TypeAlias = uint16
        # unsigned __int32: TypeAlias = uint32
        # unsigned __int64: TypeAlias = uint64
        # unsigned __int128: TypeAlias = uint128

        wchar_t: TypeAlias = wchar

        int8_t: TypeAlias = int8
        int16_t: TypeAlias = int16
        int32_t: TypeAlias = int32
        int64_t: TypeAlias = int64
        int128_t: TypeAlias = int128

        uint8_t: TypeAlias = uint8
        uint16_t: TypeAlias = uint16
        uint32_t: TypeAlias = uint32
        uint64_t: TypeAlias = uint64
        uint128_t: TypeAlias = uint128

        _BYTE: TypeAlias = uint8
        _WORD: TypeAlias = uint16
        _DWORD: TypeAlias = uint32
        _QWORD: TypeAlias = uint64
        _OWORD: TypeAlias = uint128


# Attribute names that types and constants may never shadow: the public API and methods of the cstruct
# class itself, plus the instance attributes created in __init__.
_RESERVED_NAMES = frozenset(dir(cstruct)) | {
    "endian",
    "consts",
    "types",
    "includes",
    "pointer",
    "_anonymous_count",
}


def ctypes(structure: type[Structure]) -> type[_ctypes.Structure]:
    """Create ctypes structures from cstruct structures."""
    fields = []
    for field in structure.__fields__:
        t = ctypes_type(field.type)
        fields.append((field._name, t))

    return type(structure.__name__, (_ctypes.Structure,), {"_fields_": fields})


def ctypes_type(type_: type[BaseType]) -> Any:
    mapping = {
        "b": _ctypes.c_int8,
        "B": _ctypes.c_uint8,
        "h": _ctypes.c_int16,
        "H": _ctypes.c_uint16,
        "i": _ctypes.c_int32,
        "I": _ctypes.c_uint32,
        "q": _ctypes.c_int64,
        "Q": _ctypes.c_uint64,
        "f": _ctypes.c_float,
        "d": _ctypes.c_double,
    }

    if issubclass(type_, Packed) and type_.packchar in mapping:
        return mapping[type_.packchar]

    if issubclass(type_, Char):
        return _ctypes.c_char

    if issubclass(type_, Wchar):
        return _ctypes.c_wchar

    if issubclass(type_, BaseArray):
        subtype = ctypes_type(type_.type)
        return subtype * type_.num_entries

    if issubclass(type_, Pointer):
        subtype = ctypes_type(type_.type)
        return _ctypes.POINTER(subtype)

    if issubclass(type_, Structure):
        return ctypes(type_)

    raise NotImplementedError(f"Type not implemented: {type_.__class__.__name__}")
