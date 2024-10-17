from __future__ import annotations

import ctypes as _ctypes
import struct
import sys
import types
from typing import Any, BinaryIO, Iterator

from dissect.cstruct.exceptions import ResolveError
from dissect.cstruct.expression import Expression
from dissect.cstruct.parser import CStyleParser, TokenParser
from dissect.cstruct.types import (
    LEB128,
    ArrayMetaType,
    BaseType,
    Char,
    Enum,
    Field,
    Flag,
    Int,
    MetaType,
    Packed,
    Pointer,
    Structure,
    Union,
    Void,
    Wchar,
)


class cstruct:
    """Main class of cstruct. All types are registered in here.

    Args:
        endian: The endianness to use when parsing.
        pointer: The pointer type to use for Pointers.
    """

    DEF_CSTYLE = 1
    DEF_LEGACY = 2

    def __init__(self, endian: str = "<", pointer: str | None = None):
        self.endian = endian

        self.consts = {}
        self.lookups = {}
        # fmt: off
        self.typedefs = {
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
            "signed short": "short",
            "unsigned short": "uint16",
            "int": "int32",
            "signed int": "int",
            "unsigned int": "uint32",
            "long": "int32",
            "signed long": "long",
            "unsigned long": "uint32",
            "long long": "int64",
            "signed long long": "long long",
            "unsigned long long": "uint64",

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

            "INT": "int",
            "INT8": "int8",
            "INT16": "int16",
            "INT32": "int32",
            "INT64": "int64",
            "INT128": "int128",

            "UINT": "uint",
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

            # Other convenience types
            "u1": "uint8",
            "u2": "uint16",
            "u4": "uint32",
            "u8": "uint64",
            "u16": "uint128",
            "__u8": "uint8",
            "__u16": "uint16",
            "__u32": "uint32",
            "__u64": "uint64",
            "uchar": "uint8",
            "ushort": "unsigned short",
            "uint": "unsigned int",
            "ulong": "unsigned long",
        }
        # fmt: on

        pointer = pointer or ("uint64" if sys.maxsize > 2**32 else "uint32")
        self.pointer = self.resolve(pointer)
        self._anonymous_count = 0

    def __getattr__(self, attr: str) -> Any:
        try:
            return self.consts[attr]
        except KeyError:
            pass

        try:
            return self.resolve(self.typedefs[attr])
        except KeyError:
            pass

        raise AttributeError(f"Invalid attribute: {attr}")

    def _next_anonymous(self) -> str:
        name = f"__anonymous_{self._anonymous_count}__"
        self._anonymous_count += 1
        return name

    def add_type(self, name: str, type_: MetaType | str, replace: bool = False) -> None:
        """Add a type or type reference.

        Only use this method when creating type aliases or adding already bound types.

        Args:
            name: Name of the type to be added.
            type_: The type to be added. Can be a str reference to another type or a compatible type class.

        Raises:
            ValueError: If the type already exists.
        """
        if not replace and (name in self.typedefs and self.resolve(self.typedefs[name]) != self.resolve(type_)):
            raise ValueError(f"Duplicate type: {name}")

        self.typedefs[name] = type_

    addtype = add_type

    def add_custom_type(
        self, name: str, type_: MetaType, size: int | None = None, alignment: int | None = None, **kwargs
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

    def load(self, definition: str, deftype: int = None, **kwargs) -> cstruct:
        """Parse structures from the given definitions using the given definition type.

        Definitions can be parsed using different parsers. Currently, there's
        only one supported parser - DEF_CSTYLE. Parsers can add types and
        modify this cstruct instance. Arguments can be passed to parsers
        using kwargs.

        The CSTYLE parser was recently replaced with token based parser,
        instead of a strictly regex based one. The old parser is still available
        by using DEF_LEGACY.

        Args:
            definition: The definition to parse.
            deftype: The definition type to parse the definitions with.
            **kwargs: Keyword arguments for parsers.
        """
        deftype = deftype or cstruct.DEF_CSTYLE

        if deftype == cstruct.DEF_CSTYLE:
            TokenParser(self, **kwargs).parse(definition)
        elif deftype == cstruct.DEF_LEGACY:
            CStyleParser(self, **kwargs).parse(definition)

        return self

    def loadfile(self, path: str, deftype: int = None, **kwargs) -> None:
        """Load structure definitions from a file.

        The given path will be read and parsed using the .load() function.

        Args:
            path: The path to load definitions from.
            deftype: The definition type to parse the definitions with.
            **kwargs: Keyword arguments for parsers.
        """
        with open(path) as fh:
            self.load(fh.read(), deftype, **kwargs)

    def read(self, name: str, stream: BinaryIO) -> Any:
        """Parse data using a given type.

        Args:
            name: Type name to read.
            stream: File-like object or byte string to parse.

        Returns:
            The parsed data.
        """
        return self.resolve(name).read(stream)

    def resolve(self, name: str) -> MetaType:
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
        type_name = name
        if not isinstance(type_name, str):
            return type_name

        for _ in range(10):
            if type_name not in self.typedefs:
                raise ResolveError(f"Unknown type {name}")

            type_name = self.typedefs[type_name]

            if not isinstance(type_name, str):
                return type_name

        raise ResolveError(f"Recursion limit exceeded while resolving type {name}")

    def _make_type(
        self,
        name: str,
        bases: Iterator[object],
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

    def _make_array(self, type_: MetaType, num_entries: int | Expression | None) -> ArrayMetaType:
        null_terminated = num_entries is None
        dynamic = isinstance(num_entries, Expression) or type_.dynamic
        size = None if (null_terminated or dynamic) else (num_entries * type_.size)
        name = f"{type_.__name__}[]" if null_terminated else f"{type_.__name__}[{num_entries}]"

        bases = (type_.ArrayType,)

        attrs = {
            "type": type_,
            "num_entries": num_entries,
            "null_terminated": null_terminated,
        }

        return self._make_type(name, bases, size, alignment=type_.alignment, attrs=attrs)

    def _make_int_type(self, name: str, size: int, signed: bool, *, alignment: int = None) -> type[Int]:
        return self._make_type(name, (Int,), size, alignment=alignment, attrs={"signed": signed})

    def _make_packed_type(self, name: str, packchar: str, base: type, *, alignment: int = None) -> type[Packed]:
        return self._make_type(
            name,
            (base, Packed),
            struct.calcsize(packchar),
            alignment=alignment,
            attrs={"packchar": packchar},
        )

    def _make_enum(self, name: str, type_: MetaType, values: dict[str, int]) -> type[Enum]:
        return Enum(self, name, type_, values)

    def _make_flag(self, name: str, type_: MetaType, values: dict[str, int]) -> type[Flag]:
        return Flag(self, name, type_, values)

    def _make_pointer(self, target: MetaType) -> type[Pointer]:
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


def ctypes(structure: Structure) -> _ctypes.Structure:
    """Create ctypes structures from cstruct structures."""
    fields = []
    for field in structure.__fields__:
        t = ctypes_type(field.type)
        fields.append((field.name, t))

    tt = type(structure.name, (_ctypes.Structure,), {"_fields_": fields})
    return tt


def ctypes_type(type_: MetaType) -> Any:
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

    if isinstance(type_, ArrayMetaType):
        subtype = ctypes_type(type_.type)
        return subtype * type_.num_entries

    if issubclass(type_, Pointer):
        subtype = ctypes_type(type_.type)
        return _ctypes.POINTER(subtype)

    if issubclass(type_, Structure):
        return ctypes(type_)

    raise NotImplementedError(f"Type not implemented: {type_.__class__.__name__}")
