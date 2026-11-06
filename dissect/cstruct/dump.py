from __future__ import annotations

import json
import os
import pprint
import string
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

from dissect.cstruct.types.base import BaseArray
from dissect.cstruct.types.enum import EnumMetaType
from dissect.cstruct.types.pointer import Pointer
from dissect.cstruct.types.structure import Structure, Union, UnionProxy

if TYPE_CHECKING:
    from collections.abc import Iterator

    from dissect.cstruct.types.base import BaseType


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
        palette: Colorize the hexdump using this color pattern. An empty color leaves those bytes uncolored.
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
            if remaining <= 0 and palette:
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
    output: Literal["print", "generator", "string"] = "print",
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


def _format_value(value: Any) -> str | None:
    """Format a structure field value for human-readable display."""
    if value is None:
        return None
    if isinstance(value, (str, Pointer, Enum)):
        return repr(value)
    if isinstance(value, int):
        return hex(value)
    if isinstance(value, list):
        return pprint.pformat(value)
    return str(value)


def _describe_fields(structure: Structure, start: int | None) -> list[dict[str, Any]]:
    """Describe the fields of ``structure`` as nodes, with offsets into the dumped data.

    The offsets follow ``Structure._read``: explicit field offsets, alignment padding and bit fields sharing a
    storage unit. They are ``None`` after a field of unknown size, e.g. a dynamic field of a structure that
    wasn't parsed.
    """
    nodes: list[dict[str, Any]] = []
    sizes = structure.__sizes__
    is_union = isinstance(structure, Union)

    offset = start
    bits_type = None
    bits_offset = None
    bits_remaining = 0

    for field in structure.__class__.__fields__:
        if field.offset is not None and start is not None:
            offset = start + field.offset
        elif is_union:
            offset = start
        elif structure.__align__ and offset is not None:
            offset += -offset & (field.alignment - 1)

        # Of fields with a repeated name ("_"), a structure only keeps the value and size of the last one
        if structure.__class__.__lookup__[field._name] is field:
            value, size = getattr(structure, field._name), sizes.get(field._name)
        else:
            value, size = None, field.type.__size__

        if field.bits:
            field_type = field.type.__type__ if isinstance(field.type, EnumMetaType) else field.type
            # Like BitBuffer, start a new storage unit when the current one is full or the type changes
            if bits_remaining == 0 or field_type != bits_type:
                bits_type = field_type
                bits_offset = offset
                bits_remaining = field_type.__size__ * 8
                if offset is not None:
                    offset += field_type.__size__

            bits_remaining -= field.bits
            nodes.append(
                {
                    "name": field._name,
                    "type": field.type.__name__,
                    "offset": bits_offset,
                    "size": field_type.__size__,
                    "bits": field.bits,
                    "display": _format_value(value),
                }
            )
            continue

        bits_type = None

        # Anonymous struct/union members have no name, their fields are accessed on the parent
        name = None if field.name is None else f"{field.name}{_array_dimensions(field.type)[1]}"
        nodes.append(_describe_value(name, field.type, value, offset, size))

        if offset is not None:
            offset = None if size is None else offset + size

    return nodes


def _describe_value(
    name: str | None, type_: type[BaseType], value: Any, offset: int | None, size: int | None
) -> dict[str, Any]:
    """Describe a field or array element as a node.

    Structures and unions, and arrays of them, get their fields or elements as child nodes. Other values, including
    arrays of other types, are formatted as a human-readable ``display``.
    """
    if isinstance(value, UnionProxy):
        # Nested Structure members inside a Union are proxied; unwrap to the real Structure
        value = value.__target__

    base_type = _array_dimensions(type_)[0]
    is_structure = issubclass(base_type, Structure)
    node = {
        "name": name,
        "type": None if is_structure and base_type.__anonymous__ else base_type.__name__,
        "offset": offset,
        "size": size,
    }

    if isinstance(value, Structure):
        node["kind"] = "union" if isinstance(value, Union) else "struct"
        node["fields"] = _describe_fields(value, offset)
    elif is_structure and isinstance(value, list):
        node["kind"] = "array"
        node["fields"] = []
        element_type = type_.__type__
        for i, element in enumerate(value):
            element_node = _describe_value(f"[{i}]", element_type, element, offset, element_type.__size__)
            node["fields"].append(element_node)
            if offset is not None:
                offset = None if element_node["size"] is None else offset + element_node["size"]
    else:
        node["display"] = _format_value(value)

    if size is None and node["offset"] is not None and "fields" in node:
        # Parsing doesn't record the sizes of array elements, so a dynamic element ends where its last field ends
        ends = [
            child["offset"] + child["size"] for child in node["fields"] if None not in (child["offset"], child["size"])
        ]
        if len(ends) == len(node["fields"]):
            end = max(ends, default=node["offset"])
            if isinstance(value, Structure) and value.__align__:
                end += -end & (value.__alignment__ - 1)
            node["size"] = end - node["offset"]

    return node


def _array_dimensions(type_: type[BaseType]) -> tuple[type[BaseType], str]:
    """Return the element type of a (multi-dimensional) array type and its dimensions in C order, e.g. ``[2][3]``."""
    dimensions = ""
    while issubclass(type_, BaseArray):
        count = type_.__num_entries__
        dimensions += f"[{'' if count is None else count}]"
        type_ = type_.__type__
    return type_, dimensions


DUMP_COLORS = [
    (COLOR_RED_BOLD, COLOR_BG_RED),
    (COLOR_GREEN_BOLD, COLOR_BG_GREEN),
    (COLOR_YELLOW_BOLD, COLOR_BG_YELLOW),
    (COLOR_BLUE_BOLD, COLOR_BG_BLUE),
    (COLOR_PURPLE_BOLD, COLOR_BG_PURPLE),
    (COLOR_CYAN_BOLD, COLOR_BG_CYAN),
    (COLOR_WHITE_BOLD, COLOR_BG_WHITE),
]


def _render_fields(
    nodes: list[dict[str, Any]],
    indent: int,
    lines: list[tuple[int, str, str | None]],
    palette: Palette,
    colored_end: int,
) -> int:
    """Add an ``(indent, name, value)`` line per field to ``lines``, and the hexdump colors to ``palette``.

    Line ``i`` gets color ``i`` of ``DUMP_COLORS``. The bytes of a value or a union get the background color of
    their (first) line, unless they overlap bytes that are already colored, such as union members and bit fields
    after the first one in a storage unit. A struct leaves the coloring to its fields.

    Returns the end offset of the colored bytes.
    """
    for node in nodes:
        offset, size = node["offset"], node["size"]
        if ("display" in node or node["kind"] == "union") and offset is not None and size and offset >= colored_end:
            if offset > colored_end:
                # Leave padding uncolored
                palette.append((offset - colored_end, ""))
            palette.append((size, DUMP_COLORS[len(lines) % len(DUMP_COLORS)][1]))
            colored_end = offset + size

        if "fields" not in node:
            lines.append((indent, node["name"], node["display"]))
        elif node["name"] is None:
            colored_end = _render_fields(node["fields"], indent, lines, palette, colored_end)
        else:
            lines.append((indent, node["name"], None))
            colored_end = _render_fields(node["fields"], indent + 1, lines, palette, colored_end)

    return colored_end


def dumpstruct(
    obj: Structure | type[Structure],
    data: bytes | None = None,
    offset: int = 0,
    color: bool = True,
    autoskip: bool = False,
    output: Literal["print", "string", "dict", "json"] = "print",
) -> str | dict[str, Any] | None:
    """Dump a structure or parsed structure instance.

    Prints a colorized hexdump and parsed structure output.

    The ``dict`` and ``json`` output formats describe the structure as a tree:
        - bytes: hex string of the raw data
        - type: type name of the structure
        - kind: ``struct`` or ``union``
        - fields: list of field nodes

    A field node has a ``name``, ``type``, ``offset`` and ``size``, where ``offset`` is the position in ``bytes``.
    Values have a human-readable ``display``. Bit fields also have ``bits``, and share the ``offset`` and ``size`` of
    their storage unit. Nested structs and unions have a ``kind`` and ``fields`` instead of a ``display``, and so do
    arrays of them: ``kind`` is ``array`` and ``fields`` are the elements, named ``[0]``, ``[1]``, etc.
    Anonymous struct/union members (``struct { ... };``) have no ``name``, anonymous types have no ``type``.
    ``offset`` and ``size`` are ``None`` when they're unknown, and so is the ``display`` of a field the structure
    doesn't keep (all but the last of repeated ``_`` fields).

    For an array, ``name`` includes the dimensions as written in the definition and ``type`` is the element type,
    e.g. ``uint8 matrix[2][3];`` has ``name`` ``matrix[2][3]`` and ``type`` ``uint8``.

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

    result = {
        "bytes": data.hex(),
        "type": obj.__class__.__name__,
        "kind": "union" if isinstance(obj, Union) else "struct",
        "fields": _describe_fields(obj, 0),
    }

    if output in ("dict", "json"):
        return result if output == "dict" else json.dumps(result, indent=4)

    lines: list[tuple[int, str, str | None]] = []
    palette: Palette = []
    _render_fields(result["fields"], 0, lines, palette, 0)

    out = [f"{result['kind']} {result['type']}:"]
    for ci, (indent, name, value) in enumerate(lines):
        pad = "  " * indent
        value = "" if value is None else f" {value}"
        if "\n" in value:
            # Align continuation lines of multi-line values with the value start
            value = value.replace("\n", f"\n{pad}{' ' * (len(name) + 4)}")

        if color:
            foreground, _ = DUMP_COLORS[ci % len(DUMP_COLORS)]
            out.append(f"{pad}- {foreground}{name}{COLOR_CLEAR}:{value}")
        else:
            out.append(f"{pad}- {name}:{value}")

    out = "\n".join(out)
    palette = palette if color else None

    if output == "print":
        print()
        hexdump(data, palette=palette, offset=offset, autoskip=autoskip)
        print()
        print(out)
        return None

    return f"\n{hexdump(data, palette=palette, offset=offset, output='string', autoskip=autoskip)}\n\n{out}"
