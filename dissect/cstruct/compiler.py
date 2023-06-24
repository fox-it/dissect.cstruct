# Made in Japan

from __future__ import annotations

import io
import logging
from enum import Enum
from textwrap import dedent, indent
from typing import TYPE_CHECKING, Iterator, Optional
from typing import Union as UnionHint

from dissect.cstruct.bitbuffer import BitBuffer
from dissect.cstruct.types import (
    Array,
    ArrayMetaType,
    Char,
    CharArray,
    Flag,
    Int,
    MetaType,
    Packed,
    Pointer,
    Structure,
    Union,
    Void,
    Wchar,
    WcharArray,
)
from dissect.cstruct.types.packed import _struct

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct
    from dissect.cstruct.types.structure import Field

SUPPORTED_TYPES = (
    Array,
    Char,
    CharArray,
    Enum,
    Flag,
    Int,
    Packed,
    Pointer,
    Structure,
    Void,
    Wchar,
    WcharArray,
)

log = logging.getLogger(__name__)

python_compile = compile


def compile(structure: type[Structure]) -> type[Structure]:
    if issubclass(structure, Union):
        return structure

    try:
        structure._read = classmethod(
            generate_read(structure.cs, structure.fields, structure.__name__, structure.align)
        )
        structure.__compiled__ = True
    except Exception as e:
        # Silently ignore, we didn't compile unfortunately
        log.debug("Failed to compile %s", structure, exc_info=e)

    return structure


def generate_read(cs: cstruct, fields: list[Field], name: Optional[str] = None, align: bool = False) -> Iterator[str]:
    source = generate_read_source(cs, fields, align)

    code = python_compile(source, f"<compiled {name or 'anonymous'}>", "exec")
    exec(code, {"BitBuffer": BitBuffer, "_struct": _struct}, d := {})
    obj = d.popitem()[1]
    obj.__source__ = source

    return obj


def generate_read_source(cs: cstruct, fields: list[Field], align: bool = False) -> str:
    preamble = """
    r = {}
    s = {}
    lookup = cls.__lookup__
    """

    if any(field.bits for field in fields):
        preamble += "bit_reader = BitBuffer(stream, cls.cs.endian)\n"

    read_code = "\n".join(generate_fields_read(cs, fields, align))

    outro = """
    obj = cls(**r)
    obj._sizes = s
    obj._values = r

    return obj
    """

    code = indent(dedent(preamble).lstrip() + read_code + dedent(outro), "    ")

    template = f"def _read(cls, stream, context=None):\n{code}"
    return template


def generate_fields_read(cs: cstruct, fields: list[Field], align: bool = False):
    current_offset = 0
    current_block = []
    prev_was_bits = False
    prev_bits_type = None
    bits_remaining = 0
    bits_rollover = False

    def flush() -> Iterator[str]:
        if current_block:
            if align and current_block[0].offset is None:
                yield f"stream.seek(-stream.tell() & ({current_block[0].alignment} - 1), {io.SEEK_CUR})"

            yield from generate_packed_read(cs, current_block, align)
            current_block[:] = []

    def align_to_field(field: Field) -> Iterator[str]:
        nonlocal current_offset

        if field.offset is not None and field.offset != current_offset:
            # If a field has a set offset and it's not the same as the current tracked offset, seek to it
            yield f"stream.seek({field.offset})"
            current_offset = field.offset

        if align and field.offset is None:
            yield f"stream.seek(-stream.tell() & ({field.alignment} - 1), {io.SEEK_CUR})"

    for field in fields:
        field_type = cs.resolve(field.type)

        if not issubclass(field_type, SUPPORTED_TYPES):
            raise TypeError(f"Unsupported type for compiler: {field_type}")

        if prev_was_bits and not field.bits:
            # Reset the bit reader
            yield "bit_reader.reset()"
            prev_was_bits = False
            bits_remaining = 0

        try:
            size = len(field_type)
            is_dynamic = False
        except TypeError:
            size = None
            is_dynamic = True

        # Sub structure
        if issubclass(field_type, Structure):
            # Flush the current block
            yield from flush()

            # Align if needed
            yield from align_to_field(field)

            # Yield a structure block
            yield from generate_structure_read(field)

        # Array of structures and multi-dimensional arrays
        elif issubclass(field_type, (Array, CharArray, WcharArray)) and (
            issubclass(field_type.type, Structure) or isinstance(field_type.type, ArrayMetaType) or is_dynamic
        ):
            # Flush the current block
            yield from flush()

            # Align if needed
            yield from align_to_field(field)

            # Yield a complex array block
            yield from generate_array_read(field)

        # Bit fields
        elif field.bits:
            if not prev_was_bits:
                prev_bits_type = field.type
                prev_was_bits = True

            if bits_remaining == 0 or prev_bits_type != field.type:
                bits_remaining = (size * 8) - field.bits
                bits_rollover = True

            # Flush the current block
            yield from flush()

            # Align if needed
            yield from align_to_field(field)

            # Yield a bit read block
            yield from generate_bits_read(field)

        # Everything else - basic and composite types (and arrays of them)
        else:
            # Add to the current block
            current_block.append(field)

        if current_offset is not None and size is not None:
            if not field.bits or (field.bits and bits_rollover):
                current_offset += size
                bits_rollover = False

    yield from flush()

    if align:
        # Align the stream
        yield f"stream.seek(-stream.tell() & (cls.alignment - 1), {io.SEEK_CUR})"


def generate_structure_read(field: Field) -> Iterator[str]:
    if field.type.anonymous:
        template = f"""
        _s = stream.tell()
        _v = lookup["{field.name}"].type._read(stream, context=r)
        r.update(_v._values)
        s.update(_v._sizes)
        """
    else:
        template = f"""
        _s = stream.tell()
        r["{field.name}"] = lookup["{field.name}"].type._read(stream, context=r)
        s["{field.name}"] = stream.tell() - _s
        """

    yield dedent(template)


def generate_array_read(field: Field) -> Iterator[str]:
    template = f"""
    _s = stream.tell()
    r["{field.name}"] = lookup["{field.name}"].type._read(stream, context=r)
    s["{field.name}"] = stream.tell() - _s
    """

    yield dedent(template)


def generate_bits_read(field: Field) -> Iterator[str]:
    lookup = f'lookup["{field.name}"].type'
    read_type = "_t"
    field_type = field.type
    if issubclass(field_type, (Enum, Flag)):
        read_type += ".type"
        field_type = field_type.type

    if issubclass(field_type, Char):
        field_type = field_type.cs.uint8
        lookup = "cls.cs.uint8"

    template = f"""
    _t = {lookup}
    r["{field.name}"] = type.__call__(_t, bit_reader.read({read_type}, {field.bits}))
    """

    yield dedent(template)


def generate_packed_read(cs: cstruct, fields: list[Field], align: bool = False) -> Iterator[str]:
    info = list(_generate_struct_info(cs, fields, align))
    reads = []

    size = 0
    slice_index = 0
    for field, count, _ in info:
        if field is None:
            # Padding
            size += count
            continue

        field_type = cs.resolve(field.type)
        read_type = _get_read_type(cs, field_type)

        if issubclass(field_type, (Array, CharArray, WcharArray)):
            count = field_type.num_entries
            read_type = _get_read_type(cs, field_type.type)

            if issubclass(read_type, (Char, Wchar, Int)):
                count *= read_type.size
                getter = f"buf[{size}:{size + count}]"
            else:
                getter = f"data[{slice_index}:{slice_index + count}]"
                slice_index += count
        elif issubclass(read_type, (Char, Wchar, Int)):
            getter = f"buf[{size}:{size + read_type.size}]"
        else:
            getter = f"data[{slice_index}]"
            slice_index += 1

        if issubclass(read_type, (Wchar, Int)):
            # Types that parse bytes further down to their own type
            parser_template = "{type}({getter})"
        else:
            # All other types can be simply intialized
            parser_template = "type.__call__({type}, {getter})"

        # Create the final reading code
        if issubclass(field_type, Array):
            reads.append(f'_t = lookup["{field.name}"].type')
            reads.append("_et = _t.type")

            if issubclass(field_type.type, Int):
                reads.append(f"_b = {getter}")
                item_parser = parser_template.format(type="_et", getter=f"_b[i:i + {field_type.type.size}]")
                list_comp = f"[{item_parser} for i in range(0, {count}, {field_type.type.size})]"
            elif issubclass(field_type.type, Pointer):
                item_parser = "_et.__new__(_et, e, stream, r)"
                list_comp = f"[{item_parser} for e in {getter}]"
            else:
                item_parser = parser_template.format(type="_et", getter="e")
                list_comp = f"[{item_parser} for e in {getter}]"

            parser = f"type.__call__(_t, {list_comp})"
        elif issubclass(field_type, CharArray):
            parser = f'type.__call__(lookup["{field.name}"].type, {getter})'
        elif issubclass(field_type, Pointer):
            reads.append(f"_pt = lookup['{field.name}'].type")
            parser = f"_pt.__new__(_pt, {getter}, stream, r)"
        else:
            parser = parser_template.format(
                type=f'lookup["{field.name}"].type',
                getter=getter,
            )

        reads.append(f'r["{field.name}"] = {parser}')
        reads.append(f's["{field.name}"] = {field_type.size}')
        reads.append("")  # Generates a newline in the resulting code

        size += field_type.size

    fmt = _optimize_struct_fmt(info)
    if fmt == "x" or (len(fmt) == 2 and fmt[1] == "x"):
        unpack = ""
    else:
        unpack = f'data = _struct(cls.cs.endian, "{fmt}").unpack(buf)\n'

    template = f"""
    buf = stream.read({size})
    if len(buf) != {size}: raise EOFError()
    {unpack}
    """

    yield dedent(template) + "\n".join(reads)


def _generate_struct_info(cs: cstruct, fields: list[Field], align: bool = False) -> Iterator[tuple[Field, int, str]]:
    if not fields:
        return

    current_offset = fields[0].offset
    imaginary_offset = 0
    for field in fields:
        # We moved -- probably due to alignment
        if field.offset is not None and (drift := field.offset - current_offset) > 0:
            yield None, drift, "x"
            current_offset += drift

        if align and field.offset is None and (drift := -imaginary_offset & (field.alignment - 1)) > 0:
            # Assume we started at a correctly aligned boundary
            yield None, drift, "x"
            imaginary_offset += drift

        count = 1
        read_type = _get_read_type(cs, field.type)

        # Drop voids
        if issubclass(read_type, Void):
            continue

        # Array of more complex types are handled elsewhere
        if issubclass(read_type, (Array, CharArray, WcharArray)):
            count = read_type.num_entries
            read_type = _get_read_type(cs, read_type.type)

        # Take the pack char for Packed
        if issubclass(read_type, Packed):
            yield field, count, read_type.packchar

        # Other types are byte based
        # We don't actually unpack anything here but slice directly out of the buffer
        elif issubclass(read_type, (Char, Wchar, Int)):
            yield field, count * read_type.size, "x"

        size = count * read_type.size
        imaginary_offset += size
        if current_offset is not None:
            current_offset += size


def _optimize_struct_fmt(info: Iterator[tuple[Field, int, str]]):
    chars = []

    current_count = 0
    current_char = None

    for _, count, char in info:
        if current_char is None:
            current_count = count
            current_char = char
            continue

        if char != current_char:
            if current_count:
                chars.append((current_count, current_char))
            current_count = count
            current_char = char
        else:
            current_count += count

    if current_char is not None and current_count:
        chars.append((current_count, current_char))

    return "".join(f"{count if count > 1 else ''}{char}" for count, char in chars)


def _get_read_type(cs: cstruct, type_: UnionHint[MetaType, str]) -> MetaType:
    type_ = cs.resolve(type_)

    if issubclass(type_, (Enum, Flag)):
        type_ = type_.type

    if issubclass(type_, Pointer):
        type_ = cs.pointer

    return cs.resolve(type_)
