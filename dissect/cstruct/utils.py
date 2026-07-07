from __future__ import annotations

import os
import pprint
import string
import sys
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Literal

    from dissect.cstruct.types.base import BaseType
    from dissect.cstruct.types.structure import Structure

# Regular ANSI colors
COLOR_RED = "\033[0;31m"
COLOR_GREEN = "\033[0;32m"
COLOR_YELLOW = "\033[0;93m"
COLOR_BLUE = "\033[0;34m"
COLOR_PURPLE = "\033[0;35m"
COLOR_CYAN = "\033[0;36m"
COLOR_WHITE = "\033[0;37m"
COLOR_BLACK = "\033[0;30m"
COLOR_GREY = "\033[0;90m"

# Bold ANSI colors
COLOR_RED_BOLD = "\033[1;31m"
COLOR_GREEN_BOLD = "\033[1;32m"
COLOR_YELLOW_BOLD = "\033[1;33m"
COLOR_BLUE_BOLD = "\033[1;34m"
COLOR_PURPLE_BOLD = "\033[1;35m"
COLOR_CYAN_BOLD = "\033[1;36m"
COLOR_WHITE_BOLD = "\033[1;37m"
COLOR_BLACK_BOLD = "\033[1;30m"
COLOR_GREY_BOLD = "\033[1;90m"

# Background ANSI colors
COLOR_BG_RED = "\033[1;41m\033[1;37m"
COLOR_BG_GREEN = "\033[1;42m\033[1;37m"
COLOR_BG_YELLOW = "\033[1;43m\033[1;37m"
COLOR_BG_BLUE = "\033[1;44m\033[1;37m"
COLOR_BG_PURPLE = "\033[1;45m\033[1;37m"
COLOR_BG_CYAN = "\033[1;46m\033[1;37m"
COLOR_BG_WHITE = "\033[1;47m\033[1;30m"

# Reset ANSI codes
COLOR_CLEAR = "\033[0m"
COLOR_CLEAR_BOLD = "\033[1;0m"

PRINTABLE = string.digits + string.ascii_letters + string.punctuation + " "

ENDIANNESS_MAP: dict[str, Literal["big", "little"]] = {
    "@": sys.byteorder,
    "=": sys.byteorder,
    "<": "little",
    ">": "big",
    "!": "big",
    "network": "big",
}

Palette = list[tuple[int, str]]


def _human_colors() -> dict[str, str]:
    """Generates a dictionary of characters with a human-readable ANSI color they should be in a hexdump.

    Coloring logic implementation derived from HexFriend and ImHex.
    """
    # Make all characters not in any rules below light green
    colors = {chr(char): COLOR_GREEN for char in range(256)}

    # Make all ASCII extended characters yellow
    for char in colors:
        if ord(char) & 0x80 == 0:
            colors[char] = COLOR_YELLOW

    # Make null bytes grey
    colors["\00"] = COLOR_GREY

    # Make printable ASCII characters bold white (0x32-0x7E)
    for char in PRINTABLE:
        colors[char] = COLOR_WHITE_BOLD

    # Make ASCII whitespace characters green bold (0x9, 0xA, 0xB, 0xC, 0xD, 0x20)
    for char in ("\t", "\n", "\11", "\12", "\r", "\20"):
        colors[char] = COLOR_GREEN_BOLD

    return colors


HUMAN_COLORS = _human_colors()


def _hexdump(
    data: bytes,
    *,
    palette: Palette | None = None,
    offset: int = 0,
    prefix: str = "",
    pretty: bool | None = False,
    autoskip: bool = False,
) -> Iterator[str]:
    """Hexdump some data.

    Args:
        data: Bytes to hexdump.
        palette: Colorize the hexdump using this color pattern.
        offset: Byte offset of the hexdump.
        prefix: Optional prefix.
        pretty: Use pretty colors, mutual exclusive with palette.
        autoskip: A single '*' replaces NUL-lines in the output.
    """
    if palette:
        palette = palette[::-1]

    # only happy little accidents
    if pretty and palette:
        raise ValueError("Cannot use argument 'pretty' in combination with 'palette', please pick one")

    remaining = 0
    active = None
    in_null_run = False
    in_collapsed_null_run = False
    last_offset = len(data) - 16

    for i in range(0, len(data), 16):
        values = ""
        chars = []

        for j in range(16):
            if not active and palette:
                remaining, active = palette.pop()
                while remaining == 0:
                    if len(palette) == 0:
                        # Last palette tuple is empty: print remaining whitespaces
                        active = ""
                        break
                    else:
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
                    chars.append(active + print_char + COLOR_CLEAR_BOLD)
                else:
                    if pretty and (color := HUMAN_COLORS.get(char, "")):
                        values += f"{color}{ord(char):02x}{COLOR_CLEAR}"
                        chars.append(color + print_char + COLOR_CLEAR)
                    else:
                        values += f"{ord(char):02x}"
                        chars.append(print_char)

                remaining -= 1
                if remaining == 0:
                    active = None

                    if palette is not None:
                        values += COLOR_CLEAR_BOLD

                if j == 15 and palette is not None:
                    values += COLOR_CLEAR_BOLD

            values += " "
            if j == 7:
                values += " "

        if autoskip and 0 < i < last_offset and data[i : i + 16] == b"\x00" * 16:
            if in_null_run:
                if not in_collapsed_null_run:
                    yield "*"
                    in_collapsed_null_run = True
                continue

            # Keep the first interior NUL line visible, collapse from the second onwards.
            in_null_run = True
        else:
            in_null_run = False
            in_collapsed_null_run = False

        chars = "".join(chars)
        yield f"{prefix}{offset + i:08x}  {values:48s}  {chars}"


def hexdump(
    data: bytes,
    *,
    palette: Palette | None = None,
    offset: int = 0,
    prefix: str = "",
    output: str = "print",
    pretty: bool | None = None,
    autoskip: bool = False,
) -> Iterator[str] | str | None:
    """Hexdump some data.

    Uses colored ANSI output with output type "print" by default. Disable with ``pretty=False``
    or set the environment variable ``NO_COLOR``.

    Args:
        data: Bytes to hexdump.
        palette: Colorize the hexdump using this color pattern.
        offset: Byte offset of the hexdump.
        prefix: Optional prefix.
        output: Output format, can be 'print', 'generator' or 'string'.
        pretty: Use pretty colors for improved human readability.
        autoskip: A single '*' replaces NUL-lines in the output.
    """
    # Enable pretty colors by default if ...
    if (
        output == "print"  # the output type is set to 'print'
        and not palette  # no palette is given (structdump only)
        and pretty is not False  # pretty was not explicitly set to False
        and not os.environ.get("NO_COLOR")  # and the environment allows colors
    ):
        pretty = True

    generator = _hexdump(data, palette=palette, offset=offset, prefix=prefix, pretty=pretty, autoskip=autoskip)
    if output == "print":
        print("\n".join(generator))
        return None
    if output == "generator":
        return generator
    if output == "string":
        return "\n".join(list(generator))
    raise ValueError(f"Invalid output argument: {output!r} (should be 'print', 'generator' or 'string').")


def _dumpstruct(
    structure: Structure,
    data: bytes,
    offset: int,
    color: bool,
    output: str,
    autoskip: bool,
) -> str | None:
    palette = []
    colors = [
        (COLOR_RED_BOLD, COLOR_BG_RED),
        (COLOR_GREEN_BOLD, COLOR_BG_GREEN),
        (COLOR_YELLOW_BOLD, COLOR_BG_YELLOW),
        (COLOR_BLUE_BOLD, COLOR_BG_BLUE),
        (COLOR_PURPLE_BOLD, COLOR_BG_PURPLE),
        (COLOR_CYAN_BOLD, COLOR_BG_CYAN),
        (COLOR_WHITE_BOLD, COLOR_BG_WHITE),
    ]
    ci = 0
    out = [f"struct {structure.__class__.__name__}:"]
    foreground, background = None, None
    for field in structure.__class__.__fields__:
        if getattr(field.type, "anonymous", False):
            continue

        value = getattr(structure, field._name)

        if isinstance(value, int) and not isinstance(value, Enum):
            value = hex(value)
        elif isinstance(value, list):
            value = pprint.pformat(value)
            if "\n" in value:
                value = value.replace("\n", f"\n{' ' * (len(field._name) + 4)}")
        else:
            value = repr(value)

        if color:
            foreground, background = colors[ci % len(colors)]
            size = structure.__sizes__[field._name]
            palette.append((size, background))
            ci += 1
            out.append(f"- {foreground}{field._name}{COLOR_CLEAR_BOLD}: {value}")
        else:
            out.append(f"- {field._name}: {value}")

    out = "\n".join(out)

    if output == "print":
        print()
        hexdump(data, palette=palette, offset=offset, autoskip=autoskip)
        print()
        print(out)
    elif output == "string":
        return f"\n{hexdump(data, palette=palette, offset=offset, output='string', autoskip=autoskip)}\n\n{out}"
    return None


def dumpstruct(
    obj: Structure | type[Structure],
    data: bytes | None = None,
    offset: int = 0,
    color: bool = True,
    autoskip: bool = False,
    output: str = "print",
) -> str | None:
    """Dump a structure or parsed structure instance.

    Prints a colorized hexdump and parsed structure output.

    Args:
        obj: Structure to dump.
        data: Bytes to parse the Structure on, if obj is not a parsed Structure already.
        offset: Byte offset of the hexdump.
        color: Colorize the hexdump and structure output.
        autoskip: A single '*' replaces NUL-lines in the output.
        output: Output format, can be 'print' or 'string'.
    """
    if output not in ("print", "string"):
        raise ValueError(f"Invalid output argument: {output!r} (should be 'print' or 'string').")

    if isinstance(obj, type) and data is not None:
        return _dumpstruct(obj(data), data, offset, color, output, autoskip)

    return _dumpstruct(obj, obj.dumps(), offset, color, output, autoskip)


def pack(value: int, size: int | None = None, endian: str = "little") -> bytes:
    """Pack an integer value to a given bit size, endianness.

    Arguments:
        value: Value to pack.
        size: Integer size in bits.
        endian: Endianness to use (little, big, network, <, > or !)
    """
    size = ((size or value.bit_length()) + 7) // 8
    return value.to_bytes(size, ENDIANNESS_MAP.get(endian, endian), signed=value < 0)


def unpack(value: bytes, size: int | None = None, endian: str = "little", sign: bool = False) -> int:
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
