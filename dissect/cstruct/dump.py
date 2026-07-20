from __future__ import annotations

import json
import os
import pprint
import string
from enum import Enum
from typing import TYPE_CHECKING, Any

from dissect.cstruct.types.base import BaseArray
from dissect.cstruct.types.pointer import Pointer
from dissect.cstruct.types.structure import Structure, Union, UnionProxy

if TYPE_CHECKING:
    from collections.abc import Iterator


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


Palette = list[tuple[int, str]]


def _human_colors() -> dict[str, str]:
    """Generates a dictionary of characters with a human-readable ANSI color they should be in a hexdump.

    Coloring logic implementation derived from HexFriend and ImHex.
    """
    # Make all characters not in any rules below light green
    colors = {chr(char): COLOR_GREEN for char in range(256)}

    # Make all 7-bit ASCII characters yellow
    for char in colors:
        if ord(char) & 0x80 == 0:
            colors[char] = COLOR_YELLOW

    # Make null bytes grey
    colors["\00"] = COLOR_GREY

    # Make printable ASCII characters bold white (0x32-0x7E)
    for char in PRINTABLE:
        colors[char] = COLOR_WHITE_BOLD

    # Make ASCII whitespace characters green bold (0x9, 0xA, 0xB, 0xC, 0xD, 0x20)
    for char in ("\t", "\n", "\v", "\f", "\r", " "):
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
    types: dict[str, dict[str, Any]],
    sizes: dict[str, int],
    values: dict[str, str],
    lines: list[tuple[int, str, str | None, int]],
    prefix: str = "",
    indent: int = 0,
    emit_palette: bool = True,
) -> list[dict[str, Any]]:
    """Walk structure fields once, building type descriptors and render lines.

    ``types``, ``sizes``, ``values`` and ``lines`` are accumulators that are mutated in place.
    A line is an ``(indent, name, value, palette_size)`` tuple, where ``value`` is ``None`` for
    container headers and ``palette_size`` is the number of hexdump bytes to color.
    ``emit_palette`` is disabled for union members, since their bytes overlap with the container.

    Returns the field descriptors of ``structure``.
    """
    fields: list[dict[str, Any]] = []
    instance_sizes = structure.__sizes__
    bitfield_group: dict[str, Any] | None = None

    for field in structure.__class__.__fields__:
        value = getattr(structure, field._name)
        if isinstance(value, UnionProxy):
            # Nested Structure members inside a Union are proxied; unwrap to the real Structure
            value = value.__target__

        if field.bits:
            key = f"{prefix}.{field._name}" if prefix else field._name
            palette_size = 0

            # A set offset marks the start of a new bitfield storage unit
            if field.offset is not None or bitfield_group is None:
                if bitfield_group is not None:
                    fields.append(bitfield_group)
                bitfield_group = {"type": field.type.__name__, "bitfields": []}

                # Size and palette entry are emitted once per group, keyed by the first member
                if (size := instance_sizes.get(field._name)) is not None:
                    sizes[key] = size
                    if emit_palette:
                        palette_size = size

            bitfield_group["bitfields"].append({"name": field._name, "bits": field.bits})
            values[key] = _format_value(value)
            lines.append((indent, field._name, values[key], palette_size))
            continue

        # Flush any pending bitfield group
        if bitfield_group is not None:
            fields.append(bitfield_group)
            bitfield_group = None

        # Unwrap all array levels and resolve type information
        field_type = field.type
        counts: list[int | None] = []
        while hasattr(field_type, "type") and hasattr(field_type, "num_entries"):
            counts.append(field_type.num_entries)
            field_type = field_type.type
        while issubclass(field_type, BaseArray):
            counts.append(field_type.num_entries)
            field_type = field_type.type

        if getattr(field_type, "__anonymous__", False):
            type_name = "union" if issubclass(field_type, Union) else "struct"
        else:
            type_name = field_type.__name__

        suffix = "".join(f"[{c if c is not None else ''}]" for c in counts)
        display_name = f"{field._name}{suffix}"
        key = f"{prefix}.{display_name}" if prefix else display_name
        descriptor: dict[str, Any] = {"name": display_name, "type": type_name}

        anonymous = field.name is None and issubclass(field_type, Structure)
        size = instance_sizes.get(field._name)
        if not anonymous and size is not None:
            sizes[key] = size
        palette_size = (size or 0) if emit_palette else 0

        if anonymous:
            # Anonymous struct/union: inline child descriptors, promote sizes/values/lines
            descriptor["anonymous"] = True
            descriptor["fields"] = _collect_struct_data(value, types, sizes, values, lines, prefix, indent)
        elif isinstance(value, Structure):
            # Nested struct/union instance: render a container header and recurse.
            # A union container claims the palette entry for its full (overlapping) region,
            # a struct container leaves the palette to its (sequential) children.
            is_union = issubclass(field_type, Union)
            lines.append((indent, display_name, None, palette_size if is_union else 0))
            child_fields = _collect_struct_data(
                value, types, sizes, values, lines, key, indent + 1, emit_palette and not is_union
            )
            if getattr(field_type, "__anonymous__", False):
                # Anonymous type with named field (e.g. `union { ... } u`): inline descriptors
                descriptor["fields"] = child_fields
            elif field_type.__name__ not in types:
                types[field_type.__name__] = {"kind": "union" if is_union else "struct", "fields": child_fields}
        else:
            if (
                isinstance(value, list)
                and value
                and isinstance(value[0], Structure)
                and field_type.__name__ not in types
            ):
                # Array of structs: register the element type, render the value as repr
                types[field_type.__name__] = {
                    "kind": "union" if issubclass(field_type, Union) else "struct",
                    "fields": _collect_struct_data(value[0], types, {}, {}, []),
                }
            values[key] = _format_value(value)
            lines.append((indent, display_name, values[key], palette_size))

        fields.append(descriptor)

    # Flush trailing bitfield group
    if bitfield_group is not None:
        fields.append(bitfield_group)

    return fields


DUMP_COLORS = [
    (COLOR_RED_BOLD, COLOR_BG_RED),
    (COLOR_GREEN_BOLD, COLOR_BG_GREEN),
    (COLOR_YELLOW_BOLD, COLOR_BG_YELLOW),
    (COLOR_BLUE_BOLD, COLOR_BG_BLUE),
    (COLOR_PURPLE_BOLD, COLOR_BG_PURPLE),
    (COLOR_CYAN_BOLD, COLOR_BG_CYAN),
    (COLOR_WHITE_BOLD, COLOR_BG_WHITE),
]


def dumpstruct(
    obj: Structure | type[Structure],
    data: bytes | None = None,
    offset: int = 0,
    color: bool = True,
    autoskip: bool = False,
    output: str = "print",
) -> str | dict[str, Any] | None:
    """Dump a structure or parsed structure instance.

    Prints a colorized hexdump and parsed structure output.

    The ``dict`` and ``json`` output formats have the following shape:
        - bytes: hex string of raw data
        - root: name of the root structure type
        - types: mapping of type names to ``{"kind": "struct"|"union", "fields": [...]}`` descriptors
        - sizes: mapping of dot-paths to byte sizes
        - values: mapping of dot-paths to human-readable values

    Args:
        obj: :class:`~dissect.cstruct.types.structure.Structure` to dump.
        data: Bytes to parse the :class:`~dissect.cstruct.types.structure.Structure` on,
            if obj is not a parsed :class:`~dissect.cstruct.types.structure.Structure` already.
        offset: Byte offset of the hexdump.
        color: Colorize the hexdump and structure output.
        autoskip: A single '*' replaces NUL-lines in the output.
        output: Output format, can be ``print``, ``string``, ``dict`` or ``json``.

    Returns:
        Formatted string when ``output="string"``, a dict when ``output="dict"``,
        a JSON string when ``output="json"``, or ``None`` when ``output="print"``.
    """
    if output not in ("print", "string", "dict", "json"):
        raise ValueError(f"Invalid output argument: {output!r} (should be 'print', 'string', 'dict' or 'json').")

    if isinstance(obj, Structure):
        data = obj.dumps() if data is None else data
    elif isinstance(obj, type) and issubclass(obj, Structure) and data is not None:
        obj = obj(data)
    else:
        raise ValueError("Invalid arguments: expected a Structure instance, or a Structure class with data.")

    root_name = obj.__class__.__name__
    root_kind = "union" if isinstance(obj, Union) else "struct"
    types: dict[str, dict[str, Any]] = {}
    sizes: dict[str, int] = {}
    values: dict[str, str] = {}
    lines: list[tuple[int, str, str | None, int]] = []
    root_fields = _collect_struct_data(obj, types, sizes, values, lines)

    if output in ("dict", "json"):
        result = {
            "bytes": data.hex(),
            "root": root_name,
            "types": {root_name: {"kind": root_kind, "fields": root_fields}, **types},
            "sizes": sizes,
            "values": values,
        }
        return result if output == "dict" else json.dumps(result, indent=4)

    palette = [] if color else None
    out = [f"{root_kind} {root_name}:"]

    for ci, (indent, name, value, palette_size) in enumerate(lines):
        pad = "  " * indent
        value = "" if value is None else f" {value}"
        if "\n" in value:
            # Align continuation lines of multi-line values with the value start
            value = value.replace("\n", f"\n{pad}{' ' * (len(name) + 4)}")

        if color:
            foreground, background = DUMP_COLORS[ci % len(DUMP_COLORS)]
            if palette_size:
                palette.append((palette_size, background))
            out.append(f"{pad}- {foreground}{name}{COLOR_CLEAR}:{value}")
        else:
            out.append(f"{pad}- {name}:{value}")

    out = "\n".join(out)

    if output == "print":
        print()
        hexdump(data, palette=palette, offset=offset, autoskip=autoskip)
        print()
        print(out)
        return None

    return f"\n{hexdump(data, palette=palette, offset=offset, output='string', autoskip=autoskip)}\n\n{out}"
