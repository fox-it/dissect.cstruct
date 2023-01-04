from __future__ import annotations

import struct
from collections import OrderedDict
from textwrap import dedent
from typing import List, TYPE_CHECKING

from dissect.cstruct.bitbuffer import BitBuffer
from dissect.cstruct.expression import Expression
from dissect.cstruct.types import (
    Array,
    BytesInteger,
    CharType,
    Enum,
    EnumInstance,
    Field,
    Flag,
    FlagInstance,
    Instance,
    PackedType,
    Pointer,
    PointerInstance,
    Structure,
    Union,
    WcharType,
)

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class Compiler:
    """Compiler for cstruct structures. Creates somewhat optimized parsing code."""

    TYPES = (
        Structure,
        Pointer,
        Enum,
        Flag,
        Array,
        PackedType,
        CharType,
        WcharType,
        BytesInteger,
    )

    COMPILE_TEMPLATE = """
class {name}(Structure):
    def __init__(self, cstruct, structure, source=None):
        self.structure = structure
        self.source = source
        super().__init__(cstruct, structure.name, structure.fields, anonymous=structure.anonymous)

    def _read(self, stream, context=None):
        r = OrderedDict()
        sizes = {{}}
        bitreader = BitBuffer(stream, self.cstruct.endian)

{read_code}

        return Instance(self, r, sizes)

    def add_field(self, name, type_, offset=None):
        raise NotImplementedError("Can't add fields to a compiled structure")

    def __repr__(self):
        return '<Structure {name} +compiled>'
"""

    def __init__(self, cstruct: cstruct):
        self.cstruct = cstruct

    def compile(self, structure: Structure) -> Structure:
        if isinstance(structure, Union) or structure.align:
            return structure

        structure_name = structure.name

        try:
            # Generate struct class based on provided structure type
            source = self.gen_struct_class(structure_name, structure)
        except TypeError:
            return structure

        # Create code object that can be executed later on
        code_object = compile(
            source,
            f"<compiled {structure_name}>",
            "exec",
        )

        env = {
            "OrderedDict": OrderedDict,
            "Structure": Structure,
            "Instance": Instance,
            "Expression": Expression,
            "EnumInstance": EnumInstance,
            "FlagInstance": FlagInstance,
            "PointerInstance": PointerInstance,
            "BytesInteger": BytesInteger,
            "BitBuffer": BitBuffer,
            "struct": struct,
            "range": range,
        }

        exec(code_object, env)
        return env[structure_name](self.cstruct, structure, source)

    def gen_struct_class(self, name: str, structure: Structure) -> str:
        blocks = []
        classes = []
        cur_block = []
        read_size = 0
        prev_was_bits = False

        for field in structure.fields:
            field_type = self.cstruct.resolve(field.type)

            if not isinstance(field_type, self.TYPES):
                raise TypeError(f"Unsupported type for compiler: {field_type}")

            if isinstance(field_type, Structure) or (
                isinstance(field_type, Array) and isinstance(field_type.type, Structure)
            ):

                blocks.append(self.gen_read_block(read_size, cur_block))

                struct_read = "s = stream.tell()\n"
                if isinstance(field_type, Array):
                    num = field_type.count

                    if isinstance(num, Expression):
                        num = f"max(0, Expression(self.cstruct, '{num.expression}').evaluate(r))"

                    struct_read += dedent(
                        f"""
                        r['{field.name}'] = []
                        for _ in range({num}):
                            r['{field.name}'].append(self.lookup['{field.name}'].type.type._read(stream))
                        sizes['{field.name}'] = stream.tell() - s
                        """
                    )
                elif isinstance(field_type, Structure) and field_type.anonymous:
                    struct_read += dedent(
                        f"""
                        v = self.lookup["{field.name}"].type._read(stream)
                        r.update(v._values)
                        sizes.update(v._sizes)
                        """
                    )
                else:
                    struct_read += dedent(
                        f"""
                        r['{field.name}'] = self.lookup['{field.name}'].type._read(stream)
                        sizes['{field.name}'] = stream.tell() - s
                        """
                    )

                blocks.append(struct_read)
                read_size = 0
                cur_block = []
                continue

            if field.bits:
                blocks.append(self.gen_read_block(read_size, cur_block))
                if isinstance(field_type, Enum):
                    bitfield_read = dedent(
                        f"""
                        r['{field.name}'] = self.cstruct.{field.type.name}(
                            bitreader.read(self.cstruct.{field.type.type.name}, {field.bits})
                        )
                        """
                    )
                else:
                    bitfield_read = f"r['{field.name}'] = bitreader.read(self.cstruct.{field.type.name}, {field.bits})"
                blocks.append(bitfield_read)

                read_size = 0
                cur_block = []
                prev_was_bits = True
                continue

            if prev_was_bits:
                blocks.append("bitreader.reset()")
                prev_was_bits = False

            try:
                count = len(field_type)
                read_size += count
                cur_block.append(field)
            except TypeError:
                if cur_block:
                    blocks.append(self.gen_read_block(read_size, cur_block))

                blocks.append(self.gen_dynamic_block(field))
                read_size = 0
                cur_block = []

        if len(cur_block):
            blocks.append(self.gen_read_block(read_size, cur_block))

        read_code = "\n\n".join(blocks)
        read_code = "\n".join(["    " * 2 + line for line in read_code.split("\n")])

        classes.append(self.COMPILE_TEMPLATE.format(name=name, read_code=read_code))
        return "\n\n".join(classes)

    def gen_read_block(self, size: int, block: List[str]) -> str:
        template = dedent(
            f"""
            buf = stream.read({size})
            if len(buf) != {size}: raise EOFError()
            data = struct.unpack(self.cstruct.endian + '{{}}', buf)
            {{}}
            """
        )

        read_code = []
        fmt = []

        cur_type = None
        cur_count = 0

        buf_offset = 0
        data_offset = 0

        for field in block:
            field_type = self.cstruct.resolve(field.type)
            read_type = field_type

            count = 1
            data_count = 1

            if isinstance(read_type, (Enum, Flag)):
                read_type = read_type.type
            elif isinstance(read_type, Pointer):
                read_type = self.cstruct.pointer

            if isinstance(field_type, Array):
                count = read_type.count
                data_count = count
                read_type = read_type.type

                if isinstance(read_type, (Enum, Flag)):
                    read_type = read_type.type
                elif isinstance(read_type, Pointer):
                    read_type = self.cstruct.pointer

                if isinstance(read_type, (CharType, WcharType, BytesInteger)):
                    read_slice = f"{buf_offset}:{buf_offset + + (count * read_type.size)}"
                else:
                    read_slice = f"{data_offset}:{data_offset + count}"
            elif isinstance(read_type, CharType):
                read_slice = f"{buf_offset}:{buf_offset + 1}"
            elif isinstance(read_type, (WcharType, BytesInteger)):
                read_slice = f"{buf_offset}:{buf_offset + read_type.size}"
            else:
                read_slice = str(data_offset)

            if not cur_type:
                if isinstance(read_type, PackedType):
                    cur_type = read_type.packchar
                else:
                    cur_type = "x"

            if isinstance(read_type, (PackedType, CharType, WcharType, BytesInteger, Enum, Flag)):
                char_count = count

                if isinstance(read_type, (CharType, WcharType, BytesInteger)):
                    data_count = 0
                    pack_char = "x"
                    char_count *= read_type.size
                else:
                    pack_char = read_type.packchar

                if cur_type != pack_char:
                    fmt.append(f"{cur_count}{cur_type}")
                    cur_count = 0

                cur_count += char_count
                cur_type = pack_char

            if isinstance(read_type, BytesInteger):
                getter = "BytesInteger.parse(buf[{slice}], {size}, {count}, {signed}, self.cstruct.endian){data_slice}"

                getter = getter.format(
                    slice=read_slice,
                    size=read_type.size,
                    count=count,
                    signed=read_type.signed,
                    data_slice="[0]" if count == 1 else "",
                )
            elif isinstance(read_type, (CharType, WcharType)):
                getter = f"buf[{read_slice}]"

                if isinstance(read_type, WcharType):
                    getter += ".decode('utf-16-le' if self.cstruct.endian == '<' else 'utf-16-be')"
            else:
                getter = f"data[{read_slice}]"

            if isinstance(field_type, (Enum, Flag)):
                enum_type = field_type.__class__.__name__
                getter = f"{enum_type}Instance(self.cstruct.{field_type.name}, {getter})"
            elif isinstance(field_type, Array) and isinstance(field_type.type, (Enum, Flag)):
                enum_type = field_type.type.__class__.__name__
                getter = f"[{enum_type}Instance(self.cstruct.{field_type.type.name}, d) for d in {getter}]"
            elif isinstance(field_type, Pointer):
                getter = f"PointerInstance(self.cstruct.{field_type.type.name}, stream, {getter}, r)"
            elif isinstance(field_type, Array) and isinstance(field_type.type, Pointer):
                getter = f"[PointerInstance(self.cstruct.{field_type.type.type.name}, stream, d, r) for d in {getter}]"
            elif isinstance(field_type, Array) and isinstance(read_type, PackedType):
                getter = f"list({getter})"

            read_code.append(f"r['{field.name}'] = {getter}")
            read_code.append(f"sizes['{field.name}'] = {count * read_type.size}")

            data_offset += data_count
            buf_offset += count * read_type.size

        if cur_count:
            fmt.append(f"{cur_count}{cur_type}")

        return template.format("".join(fmt), "\n".join(read_code))

    def gen_dynamic_block(self, field: Field) -> str:
        if not isinstance(field.type, Array):
            raise TypeError(f"Only Array can be dynamic, got {field.type!r}")

        field_type = self.cstruct.resolve(field.type.type)
        reader = None

        if isinstance(field_type, (Enum, Flag)):
            field_type = field_type.type

        if not field.type.count:  # Null terminated
            if isinstance(field_type, PackedType):
                reader = dedent(
                    f"""
                    t = []
                    while True:
                        d = stream.read({field_type.size})
                        if len(d) != {field_type.size}: raise EOFError()
                        v = struct.unpack(self.cstruct.endian + '{field_type.packchar}', d)[0]
                        if v == 0: break
                        t.append(v)
                    """
                )

            elif isinstance(field_type, (CharType, WcharType)):
                null = "\\x00" * field_type.size
                reader = dedent(
                    f"""
                    t = []
                    while True:
                        c = stream.read({field_type.size})
                        if len(c) != {field_type.size}: raise EOFError()
                        if c == b'{null}': break
                        t.append(c)
                    t = b''.join(t)"""  # It's important there's no newline here because of the optional decode
                )

                if isinstance(field_type, WcharType):
                    reader += ".decode('utf-16-le' if self.cstruct.endian == '<' else 'utf-16-be')"
            elif isinstance(field_type, BytesInteger):
                reader = dedent(
                    f"""
                    t = []
                    while True:
                        d = stream.read({field_type.size})
                        if len(d) != {field_type.size}: raise EOFError()
                        v = BytesInteger.parse(d, {field_type.size}, 1, {field_type.signed}, self.cstruct.endian)
                        if v == 0: break
                        t.append(v)
                    """
                )

            if isinstance(field_type, (Enum, Flag)):
                enum_type = field_type.__class__.__name__
                reader += f"\nt = [{enum_type}Instance(self.cstruct.{field_type.name}, d) for d in t]"

            if not reader:
                raise TypeError(f"Couldn't compile a reader for array {field!r}, {field_type!r}.")

            return f"s = stream.tell()\n{reader}\nr['{field.name}'] = t\nsizes['{field.name}'] = stream.tell() - s"

        expr_read = dedent(
            f"""
            dynsize = max(0, Expression(self.cstruct, "{field.type.count.expression}").evaluate(r))
            buf = stream.read(dynsize * {field_type.size})
            if len(buf) != dynsize * {field_type.size}: raise EOFError()
            r['{field.name}'] = {{reader}}
            sizes['{field.name}'] = dynsize * {field_type.size}
            """
        )

        if isinstance(field_type, PackedType):
            reader = f"list(struct.unpack(self.cstruct.endian + f'{{dynsize}}{field_type.packchar}', buf))"
        elif isinstance(field_type, (CharType, WcharType)):
            reader = "buf"
            if isinstance(field_type, WcharType):
                reader += ".decode('utf-16-le' if self.cstruct.endian == '<' else 'utf-16-be')"
        elif isinstance(field_type, BytesInteger):
            reader = f"BytesInteger.parse(buf, {field_type.size}, dynsize, {field_type.signed}, self.cstruct.endian)"

        if isinstance(field_type, (Enum, Flag)):
            enum_type = field_type.__class__.__name__
            reader += f"[{enum_type}Instance(self.cstruct.{field_type.name}, d) for d in {reader}]"

        return expr_read.format(reader=reader, size=None)
