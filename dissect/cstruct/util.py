from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal

    from dissect.cstruct.cstruct import AllowedEndianness
    from dissect.cstruct.types.base import BaseType
    from dissect.cstruct.types.structure import Structure


ENDIANNESS_TO_BYTEORDER_MAP: dict[AllowedEndianness, Literal["big", "little"]] = {
    "<": "little",
    ">": "big",
    "!": "big",
    "@": sys.byteorder,
    "=": sys.byteorder,
    "network": "big",
    "little": "little",
    "big": "big",
}


def pack(value: int, size: int | None = None, endian: AllowedEndianness = "little") -> bytes:
    """Pack an integer value to a given bit size, endianness.

    Arguments:
        value: Value to pack.
        size: Integer size in bits.
        endian: Endianness to use (little, big, network, <, >, !, @ or =).
    """
    if endian not in ENDIANNESS_TO_BYTEORDER_MAP:
        raise ValueError(f"Invalid endianness: {endian!r} (should be little, big, network, <, >, !, @ or =)")

    size = ((size or value.bit_length()) + 7) // 8
    return value.to_bytes(size, ENDIANNESS_TO_BYTEORDER_MAP[endian], signed=value < 0)


def unpack(value: bytes, size: int | None = None, endian: AllowedEndianness = "little", sign: bool = False) -> int:
    """Unpack an integer value from a given bit size, endianness and sign.

    Arguments:
        value: Value to unpack.
        size: Integer size in bits.
        endian: Endianness to use (little, big, network, <, >, !, @ or =).
        sign: Signedness of the integer.
    """
    if size and len(value) != size // 8:
        raise ValueError(f"Invalid byte value, expected {size // 8} bytes, got {len(value)} bytes")

    if endian not in ENDIANNESS_TO_BYTEORDER_MAP:
        raise ValueError(f"Invalid endianness: {endian!r} (should be little, big, network, <, >, !, @ or =)")

    return int.from_bytes(value, ENDIANNESS_TO_BYTEORDER_MAP[endian], signed=sign)


def p8(value: int, endian: AllowedEndianness = "little") -> bytes:
    """Pack an 8 bit integer.

    Arguments:
        value: Value to pack.
        endian: Endianness to use (little, big, network, <, >, !, @ or =).
    """
    return pack(value, 8, endian)


def p16(value: int, endian: AllowedEndianness = "little") -> bytes:
    """Pack a 16 bit integer.

    Arguments:
        value: Value to pack.
        endian: Endianness to use (little, big, network, <, >, !, @ or =).
    """
    return pack(value, 16, endian)


def p32(value: int, endian: AllowedEndianness = "little") -> bytes:
    """Pack a 32 bit integer.

    Arguments:
        value: Value to pack.
        endian: Endianness to use (little, big, network, <, >, !, @ or =).
    """
    return pack(value, 32, endian)


def p64(value: int, endian: AllowedEndianness = "little") -> bytes:
    """Pack a 64 bit integer.

    Arguments:
        value: Value to pack.
        endian: Endianness to use (little, big, network, <, >, !, @ or =).
    """
    return pack(value, 64, endian)


def u8(value: bytes, endian: AllowedEndianness = "little", sign: bool = False) -> int:
    """Unpack an 8 bit integer.

    Arguments:
        value: Value to unpack.
        endian: Endianness to use (little, big, network, <, >, !, @ or =).
        sign: Signedness of the integer.
    """
    return unpack(value, 8, endian, sign)


def u16(value: bytes, endian: AllowedEndianness = "little", sign: bool = False) -> int:
    """Unpack a 16 bit integer.

    Arguments:
        value: Value to unpack.
        endian: Endianness to use (little, big, network, <, >, !, @ or =).
        sign: Signedness of the integer.
    """
    return unpack(value, 16, endian, sign)


def u32(value: bytes, endian: AllowedEndianness = "little", sign: bool = False) -> int:
    """Unpack a 32 bit integer.

    Arguments:
        value: Value to unpack.
        endian: Endianness to use (little, big, network, <, >, !, @ or =).
        sign: Signedness of the integer.
    """
    return unpack(value, 32, endian, sign)


def u64(value: bytes, endian: AllowedEndianness = "little", sign: bool = False) -> int:
    """Unpack a 64 bit integer.

    Arguments:
        value: Value to unpack.
        endian: Endianness to use (little, big, network, <, >, !, @ or =).
        sign: Signedness of the integer.
    """
    return unpack(value, 64, endian, sign)


def swap(value: int, size: int) -> int:
    """Swap the endianness of an integer with a given bit size.

    Arguments:
        value: Integer to swap.
        size: Integer size in bits.
    """
    return unpack(pack(value, size, ">"), size, "<")


def swap16(value: int) -> int:
    """Swap the endianness of a 16 bit integer.

    Arguments:
        value: Integer to swap.
    """
    return swap(value, 16)


def swap32(value: int) -> int:
    """Swap the endianness of a 32 bit integer.

    Arguments:
        value: Integer to swap.
    """
    return swap(value, 32)


def swap64(value: int) -> int:
    """Swap the endianness of a 64 bit integer.

    Arguments:
        value: Integer to swap.
    """
    return swap(value, 64)


def sizeof(type_: type[BaseType] | BaseType) -> int:
    """Get the size of a type in bytes."""
    return len(type_)


def offsetof(type_: type[Structure], name: str) -> int:
    """Get the offset of a field in a structure."""
    if (field := type_.fields.get(name)) is None:
        raise ValueError(f"Structure '{type_.__name__}' does not have a field named '{name}'")
    if (offset := field.offset) is None:
        raise ValueError(f"Field '{field._name}' of structure '{type_.__name__}' does not have a known offset")
    return offset
