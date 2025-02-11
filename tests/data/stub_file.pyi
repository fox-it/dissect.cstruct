from __future__ import annotations

from typing import overload, BinaryIO

from dissect.cstruct import cstruct
from dissect.cstruct.types import (Array, ArrayMetaType, BaseType, Char, CharArray, Enum, Field, Flag, Int, LEB128, MetaType, Packed, Pointer, Structure, Union, Void, Wchar, WcharArray)
from typing_extensions import TypeAlias

class c_structure(cstruct):
    int8: TypeAlias = Packed[int]
    uint8: TypeAlias = Packed[int]
    int16: TypeAlias = Packed[int]
    uint16: TypeAlias = Packed[int]
    int32: TypeAlias = Packed[int]
    uint32: TypeAlias = Packed[int]
    int64: TypeAlias = Packed[int]
    uint64: TypeAlias = Packed[int]
    float16: TypeAlias = Packed[float]
    float: TypeAlias = Packed[float]
    double: TypeAlias = Packed[float]
    class Test(Structure):
        a: c_structure.uint32
        b: c_structure.uint32
        @overload
        def __init__(self, a: c_structure.uint32 = ..., b: c_structure.uint32 = ...): ...
        @overload
        def __init__(self, fh: bytes | bytearray | BinaryIO, /): ...