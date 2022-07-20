from __future__ import print_function

import ctypes as _ctypes
import sys
from typing import Any, BinaryIO

from dissect.cstruct.exceptions import ResolveError
from dissect.cstruct.parser import CStyleParser, TokenParser
from dissect.cstruct.types import (
    Array,
    BaseType,
    BytesInteger,
    CharType,
    Structure,
    PackedType,
    Pointer,
    VoidType,
    WcharType,
)


class cstruct:
    """Main class of cstruct. All types are registered in here.

    Args:
        endian: The endianness to use when parsing.
        pointer: The pointer type to use for Pointers.
    """

    DEF_CSTYLE = 1
    DEF_LEGACY = 2

    def __init__(self, endian: str = "<", pointer: str = None):
        self.endian = endian

        self.consts = {}
        self.lookups = {}
        # fmt: off
        self.typedefs = {
            # Internal types
            "int8": PackedType(self, "int8", 1, "b"),
            "uint8": PackedType(self, "uint8", 1, "B"),
            "int16": PackedType(self, "int16", 2, "h"),
            "uint16": PackedType(self, "uint16", 2, "H"),
            "int32": PackedType(self, "int32", 4, "i"),
            "uint32": PackedType(self, "uint32", 4, "I"),
            "int64": PackedType(self, "int64", 8, "q"),
            "uint64": PackedType(self, "uint64", 8, "Q"),
            "float": PackedType(self, "float", 4, "f"),
            "double": PackedType(self, "double", 8, "d"),
            "char": CharType(self),
            "wchar": WcharType(self),

            "int24": BytesInteger(self, "int24", 3, True, alignment=4),
            "uint24": BytesInteger(self, "uint24", 3, False, alignment=4),
            "int48": BytesInteger(self, "int48", 6, True, alignment=8),
            "uint48": BytesInteger(self, "uint48", 6, False, alignment=8),

            "void": VoidType(),

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

            "UINT": "uint",
            "UINT8": "uint8",
            "UINT16": "uint16",
            "UINT32": "uint32",
            "UINT64": "uint64",

            "__int8": "int8",
            "__int16": "int16",
            "__int32": "int32",
            "__int64": "int64",

            "wchar_t": "wchar",

            # GNU C types
            "int8_t": "int8",
            "int16_t": "int16",
            "int32_t": "int32",
            "int64_t": "int64",

            "uint8_t": "uint8",
            "uint16_t": "uint16",
            "uint32_t": "uint32",
            "uint64_t": "uint64",

            # Other convenience types
            "u1": "uint8",
            "u2": "uint16",
            "u4": "uint32",
            "u8": "uint64",
            "uchar": "uint8",
            "ushort": "unsigned short",
            "uint": "unsigned int",
            "ulong": "unsigned long",
        }
        # fmt: on

        pointer = pointer or "uint64" if sys.maxsize > 2**32 else "uint32"
        self.pointer = self.resolve(pointer)
        self._anonymous_count = 0

    def __getattr__(self, attr: str) -> Any:
        try:
            return self.resolve(self.typedefs[attr])
        except KeyError:
            pass

        try:
            return self.consts[attr]
        except KeyError:
            pass

        raise AttributeError(f"Invalid attribute: {attr}")

    def _next_anonymous(self) -> str:
        name = f"anonymous_{self._anonymous_count}"
        self._anonymous_count += 1
        return name

    def addtype(self, name: str, type_: BaseType, replace: bool = False) -> None:
        """Add a type or type reference.

        Args:
            name: Name of the type to be added.
            type_: The type to be added. Can be a str reference to another type
                or a compatible type class.

        Raises:
            ValueError: If the type already exists.
        """
        if not replace and (name in self.typedefs and self.resolve(self.typedefs[name]) != self.resolve(type_)):
            raise ValueError(f"Duplicate type: {name}")

        self.typedefs[name] = type_

    def load(self, definition: str, deftype: int = None, **kwargs) -> None:
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

    def resolve(self, name: str) -> BaseType:
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


def ctypes(structure: Structure) -> _ctypes.Structure:
    """Create ctypes structures from cstruct structures."""
    fields = []
    for field in structure.fields:
        t = ctypes_type(field.type)
        fields.append((field.name, t))

    tt = type(structure.name, (_ctypes.Structure,), {"_fields_": fields})
    return tt


def ctypes_type(type_: BaseType) -> Any:
    mapping = {
        "I": _ctypes.c_ulong,
        "i": _ctypes.c_long,
        "b": _ctypes.c_int8,
    }

    if isinstance(type_, PackedType):
        return mapping[type_.packchar]

    if isinstance(type_, CharType):
        return _ctypes.c_char

    if isinstance(type_, Array):
        subtype = ctypes_type(type_.type)
        return subtype * type_.count

    if isinstance(type_, Pointer):
        subtype = ctypes_type(type_.type)
        return _ctypes.POINTER(subtype)

    raise NotImplementedError(f"Type not implemented: {type_.__class__.__name__}")
