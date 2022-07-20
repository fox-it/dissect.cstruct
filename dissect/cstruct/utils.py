import string
import pprint
from typing import List, Tuple

from dissect.cstruct.types import Instance, Structure

COLOR_RED = "\033[1;31m"
COLOR_GREEN = "\033[1;32m"
COLOR_YELLOW = "\033[1;33m"
COLOR_BLUE = "\033[1;34m"
COLOR_PURPLE = "\033[1;35m"
COLOR_CYAN = "\033[1;36m"
COLOR_WHITE = "\033[1;37m"
COLOR_NORMAL = "\033[1;0m"

COLOR_BG_RED = "\033[1;41m\033[1;37m"
COLOR_BG_GREEN = "\033[1;42m\033[1;37m"
COLOR_BG_YELLOW = "\033[1;43m\033[1;37m"
COLOR_BG_BLUE = "\033[1;44m\033[1;37m"
COLOR_BG_PURPLE = "\033[1;45m\033[1;37m"
COLOR_BG_CYAN = "\033[1;46m\033[1;37m"
COLOR_BG_WHITE = "\033[1;47m\033[1;30m"

PRINTABLE = string.digits + string.ascii_letters + string.punctuation + " "

ENDIANNESS_MAP = {
    "network": "big",
    "<": "little",
    ">": "big",
    "!": "big",
}

Palette = List[Tuple[str, str]]


def _hexdump(data: bytes, palette: Palette = None, offset: int = 0, prefix: str = ""):
    """Hexdump some data.

    Args:
        data: Bytes to hexdump.
        offset: Byte offset of the hexdump.
        prefix: Optional prefix.
        palette: Colorize the hexdump using this color pattern.
    """
    if palette:
        palette = palette[::-1]

    remaining = 0
    active = None

    for i in range(0, len(data), 16):
        values = ""
        chars = []

        for j in range(16):
            if not active and palette:
                remaining, active = palette.pop()
                values += active
            elif active and j == 0:
                values += active

            if i + j >= len(data):
                values += "  "
            else:
                char = data[i + j]
                char = chr(char)

                print_char = char if char in PRINTABLE else "."

                if active:
                    values += f"{ord(char):02x}"
                    chars.append(active + print_char + COLOR_NORMAL)
                else:
                    values += f"{ord(char):02x}"
                    chars.append(print_char)

                remaining -= 1
                if remaining == 0:
                    active = None

                    if palette is not None:
                        values += COLOR_NORMAL

                if j == 15:
                    if palette is not None:
                        values += COLOR_NORMAL

            values += " "
            if j == 7:
                values += " "

        chars = "".join(chars)
        yield f"{prefix}{offset + i:08x}  {values:48s}  {chars}"


def hexdump(data: bytes, palette=None, offset: int = 0, prefix: str = "", output: str = "print"):
    """Hexdump some data.

    Args:
        data: Bytes to hexdump.
        palette: Colorize the hexdump using this color pattern.
        offset: Byte offset of the hexdump.
        prefix: Optional prefix.
        output: Output format, can be 'print', 'generator' or 'string'.
    """
    generator = _hexdump(data, palette, offset, prefix)
    if output == "print":
        print("\n".join(generator))
    elif output == "generator":
        return generator
    elif output == "string":
        return "\n".join(list(generator))
    else:
        raise ValueError(f"Invalid output argument: {output!r} (should be 'print', 'generator' or 'string').")


def _dumpstruct(
    structure: Structure,
    instance: Instance,
    data: bytes,
    offset: int,
    color: bool,
    output: str,
):
    palette = []
    colors = [
        (COLOR_RED, COLOR_BG_RED),
        (COLOR_GREEN, COLOR_BG_GREEN),
        (COLOR_YELLOW, COLOR_BG_YELLOW),
        (COLOR_BLUE, COLOR_BG_BLUE),
        (COLOR_PURPLE, COLOR_BG_PURPLE),
        (COLOR_CYAN, COLOR_BG_CYAN),
        (COLOR_WHITE, COLOR_BG_WHITE),
    ]
    ci = 0
    out = [f"struct {structure.name}:"]
    foreground, background = None, None
    for field in instance._type.fields:
        if color:
            foreground, background = colors[ci % len(colors)]
            palette.append((instance._size(field.name), background))
        ci += 1

        value = getattr(instance, field.name)
        if isinstance(value, str):
            value = repr(value)
        elif isinstance(value, int):
            value = hex(value)
        elif isinstance(value, list):
            value = pprint.pformat(value)
            if "\n" in value:
                value = value.replace("\n", f"\n{' ' * (len(field.name) + 4)}")

        if color:
            out.append(f"- {foreground}{field.name}{COLOR_NORMAL}: {value}")
        else:
            out.append(f"- {field.name}: {value}")

    out = "\n".join(out)

    if output == "print":
        print()
        hexdump(data, palette, offset=offset)
        print()
        print(out)
    elif output == "string":
        return "\n".join(["", hexdump(data, palette, offset=offset, output="string"), "", out])


def dumpstruct(obj, data: bytes = None, offset: int = 0, color: bool = True, output: str = "print"):
    """Dump a structure or parsed structure instance.

    Prints a colorized hexdump and parsed structure output.

    Args:
        obj: Structure or Instance to dump.
        data: Bytes to parse the Structure on, if obj is not a parsed Instance.
        offset: Byte offset of the hexdump.
        output: Output format, can be 'print' or 'string'.
    """
    if output not in ("print", "string"):
        raise ValueError(f"Invalid output argument: {output!r} (should be 'print' or 'string').")

    if isinstance(obj, Instance):
        return _dumpstruct(obj._type, obj, obj.dumps(), offset, color, output)
    elif isinstance(obj, Structure) and data:
        return _dumpstruct(obj, obj(data), data, offset, color, output)
    else:
        raise ValueError("Invalid arguments")


def pack(value: int, size: int = None, endian: str = "little") -> bytes:
    """Pack an integer value to a given bit size, endianness.

    Arguments:
        value: Value to pack.
        size: Integer size in bits.
        endian: Endianness to use (little, big, network, <, > or !)
    """
    size = ((size or value.bit_length()) + 7) // 8
    return value.to_bytes(size, ENDIANNESS_MAP.get(endian, endian), signed=value < 0)


def unpack(value: bytes, size: int = None, endian: str = "little", sign: bool = False) -> int:
    """Unpack an integer value from a given bit size, endianness and sign.

    Arguments:
        value: Value to unpack.
        size: Integer size in bits.
        endian: Endianness to use (little, big, network, <, > or !)
        sign: Signedness of the integer.
    """
    if size and len(value) != size // 8:
        raise ValueError(f"Invalid byte value, expected {size // 8} bytes, got {len(value)} bytes")
    return int.from_bytes(value, ENDIANNESS_MAP.get(endian, endian), signed=sign)


def p8(value: int, endian: str = "little") -> bytes:
    """Pack an 8 bit integer.

    Arguments:
        value: Value to pack.
        endian: Endianness to use (little, big, network, <, > or !)
    """
    return pack(value, 8, endian)


def p16(value: int, endian: str = "little") -> bytes:
    """Pack a 16 bit integer.

    Arguments:
        value: Value to pack.
        endian: Endianness to use (little, big, network, <, > or !)
    """
    return pack(value, 16, endian)


def p32(value: int, endian: str = "little") -> bytes:
    """Pack a 32 bit integer.

    Arguments:
        value: Value to pack.
        endian: Endianness to use (little, big, network, <, > or !)
    """
    return pack(value, 32, endian)


def p64(value: int, endian: str = "little") -> bytes:
    """Pack a 64 bit integer.

    Arguments:
        value: Value to pack.
        endian: Endianness to use (little, big, network, <, > or !)
    """
    return pack(value, 64, endian)


def u8(value: bytes, endian: str = "little", sign: bool = False) -> int:
    """Unpack an 8 bit integer.

    Arguments:
        value: Value to unpack.
        endian: Endianness to use (little, big, network, <, > or !)
        sign: Signedness of the integer.
    """
    return unpack(value, 8, endian, sign)


def u16(value: bytes, endian: str = "little", sign: bool = False) -> int:
    """Unpack a 16 bit integer.

    Arguments:
        value: Value to unpack.
        endian: Endianness to use (little, big, network, <, > or !)
        sign: Signedness of the integer.
    """
    return unpack(value, 16, endian, sign)


def u32(value: bytes, endian: str = "little", sign: bool = False) -> int:
    """Unpack a 32 bit integer.

    Arguments:
        value: Value to unpack.
        endian: Endianness to use (little, big, network, <, > or !)
        sign: Signedness of the integer.
    """
    return unpack(value, 32, endian, sign)


def u64(value: bytes, endian: str = "little", sign: bool = False) -> int:
    """Unpack a 64 bit integer.

    Arguments:
        value: Value to unpack.
        endian: Endianness to use (little, big, network, <, > or !)
        sign: Signedness of the integer.
    """
    return unpack(value, 64, endian, sign)


def swap(value: int, size: int):
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
