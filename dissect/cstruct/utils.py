from __future__ import annotations

import json
import os
import pprint
import string
import sys
from enum import Enum
from typing import TYPE_CHECKING, Any

from dissect.cstruct.types.base import BaseArray
from dissect.cstruct.types.pointer import Pointer
from dissect.cstruct.types.structure import Structure, Union

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Literal

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
    data: bytes, palette: Palette | None = None, offset: int = 0, prefix: str = "", pretty: bool | None = False
) -> Iterator[str]:
    """Hexdump some data.

    Args:
        data: Bytes to hexdump.
        palette: Colorize the hexdump using this color pattern.
        offset: Byte offset of the hexdump.
        prefix: Optional prefix.
        pretty: Use pretty colors, mutual exclusive with palette.
    """
    if palette:
        palette = palette[::-1]

    # only happy little accidents
    if pretty and palette:
        raise ValueError("Cannot use argument 'pretty' in combination with 'palette', please pick one")

    remaining = 0
    active = None

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
                    chars.append(active + print_char + COLOR_CLEAR)
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
                        values += COLOR_CLEAR

                if j == 15 and palette is not None:
                    values += COLOR_CLEAR

            values += " "
            if j == 7:
                values += " "

        chars = "".join(chars)
        yield f"{prefix}{offset + i:08x}  {values:48s}  {chars}"


def hexdump(
    data: bytes,
    palette: Palette | None = None,
    offset: int = 0,
    prefix: str = "",
    output: str = "print",
    pretty: bool | None = None,
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
    """
    # Enable pretty colors by default if ...
    if (
        output == "print"  # the output type is set to 'print'
        and not palette  # no palette is given (structdump only)
        and pretty is not False  # pretty was not explicitly set to False
        and not os.environ.get("NO_COLOR")  # and the environment allows colors
    ):
        pretty = True

    generator = _hexdump(data, palette, offset, prefix, pretty)
    if output == "print":
        print("\n".join(generator))
        return None
    if output == "generator":
        return generator
    if output == "string":
        return "\n".join(list(generator))
    raise ValueError(f"Invalid output argument: {output!r} (should be 'print', 'generator' or 'string').")


def _format_value(value: Any) -> str:
    """Format a structure field value for human-readable display."""
    if isinstance(value, (str, Pointer, Enum)):
        return repr(value)
    if isinstance(value, int):
        return hex(value)
    if isinstance(value, list):
        return pprint.pformat(value)
    return str(value)


def _collect_struct_data(
    structure: Structure,
    types: dict[str, list[dict[str, Any]]],
    prefix: str = "",
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, str]]:
    """Walk structure fields to build type descriptors, sizes, and values in a single pass.

    Note: ``types`` is mutated in place, named sub-structure types encountered
    during traversal are registered directly into this dict.

    Returns ``(field_descriptors, sizes, values)``.
    """
    fields: list[dict[str, Any]] = []
    sizes: dict[str, int] = {}
    values: dict[str, str] = {}
    instance_sizes = structure.__sizes__
    bitfield_group: dict[str, Any] | None = None

    for field in structure.__class__.__fields__:
        value = getattr(structure, field._name)

        if field.bits:
            key = f"{prefix}.{field._name}" if prefix else field._name

            # Type descriptors: group consecutive bitfields into a single entry
            if field.offset is not None:
                if bitfield_group is not None:
                    fields.append(bitfield_group)
                bitfield_group = {
                    "type": field.type.__name__,
                    "bitfields": [],
                }
                # Sizes: emit once per bitfield group (keyed by first member)
                size = instance_sizes.get(field._name)
                if size is not None:
                    sizes[key] = size

            if bitfield_group is None:
                raise ValueError(
                    f"bitfield {field._name!r} without a preceding storage unit (offset is None but no group started)"
                )

            bitfield_group["bitfields"].append(
                {
                    "name": field._name,
                    "bits": field.bits,
                }
            )

            # Values: individual entry per bitfield
            values[key] = _format_value(value)
            continue

        # Flush any pending bitfield group
        if bitfield_group is not None:
            fields.append(bitfield_group)
            bitfield_group = None

        # Unwrap all array levels and resolve type information
        field_type = field.type
        counts: list[int | None] = []
        while issubclass(field_type, BaseArray):
            counts.append(field_type.num_entries)
            field_type = field_type.type

        if issubclass(field_type, Union):
            type_name = "union" if getattr(field_type, "__anonymous__", False) else field_type.__name__
        elif issubclass(field_type, Structure):
            type_name = "struct" if getattr(field_type, "__anonymous__", False) else field_type.__name__
        else:
            type_name = field_type.__name__

        suffix = "".join(f"[{c if c is not None else ''}]" for c in counts)
        display_name = f"{field._name}{suffix}" if suffix else field._name
        key = f"{prefix}.{display_name}" if prefix else display_name

        descriptor: dict[str, Any] = {"name": display_name, "type": type_name}

        if field.name is None and issubclass(field_type, Structure):
            # Anonymous struct/union: inline child descriptors, promote sizes/values
            child_fields, child_sizes, child_values = _collect_struct_data(value, types, prefix)
            descriptor["fields"] = child_fields
            descriptor["anonymous"] = True
            sizes.update(child_sizes)
            values.update(child_values)
        elif isinstance(value, Structure):
            # Named struct/union instance: collect container size, recurse for children
            size = instance_sizes.get(field._name)
            if size is not None:
                sizes[key] = size
            child_fields, child_sizes, child_values = _collect_struct_data(value, types, key)
            sizes.update(child_sizes)
            values.update(child_values)
            if getattr(field_type, "__anonymous__", False):
                # Anonymous type with named field (e.g. `union { ... } u`): inline descriptors
                descriptor["fields"] = child_fields
            elif field_type.__name__ not in types:
                # Named type: register in types dict
                types[field_type.__name__] = child_fields
        elif isinstance(value, list) and value and isinstance(value[0], Structure):
            # Array of structs: register the element type, keep value as repr
            size = instance_sizes.get(field._name)
            if size is not None:
                sizes[key] = size
            if field_type.__name__ not in types:
                child_fields, _, _ = _collect_struct_data(value[0], types)
                types[field_type.__name__] = child_fields
            values[key] = _format_value(value)
        else:
            # Leaf field (scalars, arrays, etc.)
            size = instance_sizes.get(field._name)
            if size is not None:
                sizes[key] = size
            values[key] = _format_value(value)

        fields.append(descriptor)

    # Flush trailing bitfield group
    if bitfield_group is not None:
        fields.append(bitfield_group)

    return fields, sizes, values


def _build_dumpstruct_dict(
    structure: Structure,
    data: bytes,
) -> dict[str, Any]:
    """Build a dictionary representation of a structure dump.

    The dictionary has the following shape:
        - bytes: hex string of raw data
        - root: name of the root structure type
        - types: mapping of type names to lists of field descriptors (purely structural)
        - sizes: mapping of dot-paths to byte sizes
        - values: mapping of dot-paths to human-readable values
    """
    root_name = structure.__class__.__name__
    types: dict[str, list[dict[str, Any]]] = {}
    root_fields, sizes, values = _collect_struct_data(structure, types)

    # Put root first, then referenced types
    ordered_types: dict[str, list[dict[str, Any]]] = {root_name: root_fields}
    ordered_types.update(types)

    return {
        "bytes": data.hex(),
        "root": root_name,
        "types": ordered_types,
        "sizes": sizes,
        "values": values,
    }


def dumpstruct(
    obj: Structure | type[Structure],
    data: bytes | None = None,
    offset: int = 0,
    color: bool = True,
    output: str = "print",
) -> str | dict[str, Any] | None:
    """Dump a structure or parsed structure instance.

    Prints a colorized hexdump and parsed structure output.

    Args:
        obj: :class:`~dissect.cstruct.types.structure.Structure` to dump.
        data: Bytes to parse the :class:`~dissect.cstruct.types.structure.Structure` on,
            if obj is not a parsed :class:`~dissect.cstruct.types.structure.Structure` already.
        offset: Byte offset of the hexdump.
        color: Colorize the output.
        output: Output format, can be ``print``, ``string``, ``dict`` or ``json``.

    Returns:
        Formatted string when ``output="string"``, a dict when ``output="dict"``,
        or ``None`` when ``output="print"``.
    """
    if output not in ("print", "string", "dict", "json"):
        raise ValueError(f"Invalid output argument: {output!r} (should be 'print', 'string', 'dict' or 'json').")

    if isinstance(obj, Structure):
        data = obj.dumps() if data is None else data
    elif isinstance(obj, type) and issubclass(obj, Structure) and data is not None:
        obj = obj(data)
    else:
        raise ValueError("Invalid arguments: expected a Structure instance, or a Structure class with data.")

    result = _build_dumpstruct_dict(obj, data)

    if output == "dict":
        return result

    if output == "json":
        return json.dumps(result, indent=4)

    # Build palette and field listing from the dict
    palette = [] if color else None
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
    out = [f"struct {result['root']}:"]

    def _render_fields(
        field_descs: list[dict[str, Any]],
        prefix: str = "",
        indent: int = 0,
        emit_palette: bool = True,
    ) -> None:
        nonlocal ci
        pad = "  " * indent

        for field_desc in field_descs:
            # Anonymous structs/unions: flatten children into parent
            if field_desc.get("anonymous"):
                _render_fields(field_desc["fields"], prefix, indent, emit_palette)
                continue

            # Bitfield groups: render each bitfield as a separate line
            if "bitfields" in field_desc:
                first = True
                for bf in field_desc["bitfields"]:
                    key = f"{prefix}.{bf['name']}" if prefix else bf["name"]
                    value = result["values"].get(key, "")

                    if color:
                        foreground, background = colors[ci % len(colors)]
                        if first and emit_palette:
                            size = result["sizes"].get(key, 0)
                            palette.append((size, background))
                            first = False
                        ci += 1
                        out.append(f"{pad}- {foreground}{bf['name']}{COLOR_CLEAR}: {value}")
                    else:
                        out.append(f"{pad}- {bf['name']}: {value}")
                continue

            name = field_desc["name"]
            key = f"{prefix}.{name}" if prefix else name

            # Named struct/union with inlined fields (anonymous type, named field)
            if "fields" in field_desc:
                is_union = field_desc["type"] == "union"
                if color:
                    foreground, background = colors[ci % len(colors)]
                    if emit_palette and is_union:
                        # Union: one palette entry for the whole container (children overlap)
                        size = result["sizes"].get(key, 0)
                        palette.append((size, background))
                    ci += 1
                    out.append(f"{pad}- {foreground}{name}{COLOR_CLEAR}:")
                else:
                    out.append(f"{pad}- {name}:")
                # Struct children emit palette (sequential), union children don't (overlapping)
                _render_fields(field_desc["fields"], key, indent + 1, emit_palette=not is_union)
                continue

            # Named struct type reference
            if field_desc["type"] in result["types"]:
                if color:
                    foreground, background = colors[ci % len(colors)]
                    # Struct: skip container palette, children handle their own bytes
                    ci += 1
                    out.append(f"{pad}- {foreground}{name}{COLOR_CLEAR}:")
                else:
                    out.append(f"{pad}- {name}:")
                _render_fields(result["types"][field_desc["type"]], key, indent + 1, emit_palette)
                continue

            # Leaf field
            value = result["values"].get(key, "")

            # Handle multi-line values with indentation
            if "\n" in str(value):
                value = str(value).replace("\n", f"\n{pad}{' ' * (len(name) + 4)}")

            if color:
                foreground, background = colors[ci % len(colors)]
                if emit_palette:
                    size = result["sizes"].get(key, 0)
                    palette.append((size, background))
                ci += 1
                out.append(f"{pad}- {foreground}{name}{COLOR_CLEAR}: {value}")
            else:
                out.append(f"{pad}- {name}: {value}")

    _render_fields(result["types"][result["root"]])

    out = "\n".join(out)

    if output == "print":
        print()
        hexdump(data, palette, offset=offset)
        print()
        print(out)
        return None

    return f"\n{hexdump(data, palette, offset=offset, output='string')}\n\n{out}"


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
