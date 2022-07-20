from __future__ import annotations

import io
from collections import OrderedDict
from typing import BinaryIO, List, TYPE_CHECKING

from dissect.cstruct.bitbuffer import BitBuffer
from dissect.cstruct.types import Array, BaseType, Enum, Instance, Pointer

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class Field:
    """Holds a structure field."""

    def __init__(self, name: str, type_: BaseType, bits: int = None, offset: int = None):
        self.name = name
        self.type = type_
        self.bits = bits
        self.offset = offset
        self.alignment = type_.alignment

    def __repr__(self):
        bits_str = " : {self.bits}" if self.bits else ""
        return f"<Field {self.name} {self.type}{bits_str}>"


class Structure(BaseType):
    """Type class for structures."""

    def __init__(
        self, cstruct: cstruct, name: str, fields: List[Field] = None, align: bool = False, anonymous: bool = False
    ):
        super().__init__(cstruct)
        self.name = name
        self.size = None
        self.alignment = None

        self.lookup = OrderedDict()
        self.fields = fields

        self.align = align
        self.anonymous = anonymous
        self.dynamic = False

        for field in self.fields:
            self.lookup[field.name] = field
            if isinstance(field.type, Structure) and field.type.anonymous:
                self.lookup.update(field.type.lookup)

        self._calc_size_and_offsets()

    def __len__(self) -> int:
        if self.dynamic:
            raise TypeError("Dynamic size")

        if self.size is None:
            self._calc_size_and_offsets()

        return self.size

    def __repr__(self) -> str:
        return f"<Structure {self.name}>"

    def _calc_size_and_offsets(self) -> None:
        """Iterate all fields in this structure to calculate the field offsets and total structure size.

        If a structure has a dynamic field, further field offsets will be set to None and self.dynamic
        will be set to True.
        """
        # The current offset, set to None if we become dynamic
        offset = 0
        # The current alignment for this structure
        alignment = 0

        # The current bit field type
        bits_type = None
        # The offset of the current bit field, set to None if we become dynamic
        bits_field_offset = 0
        # How many bits we have left in the current bit field
        bits_remaining = 0

        for field in self.fields:
            if field.offset is not None:
                # If a field already has an offset, it's leading
                offset = field.offset

            if self.align and offset is not None:
                # Round to next alignment
                offset += -offset & (field.alignment - 1)

            # The alignment of this struct is equal to its largest members' alignment
            alignment = max(alignment, field.type.alignment)

            if field.bits:
                field_type = field.type

                if isinstance(field_type, Enum):
                    field_type = field_type.type

                # Bit fields have special logic
                if (
                    # Exhausted a bit field
                    bits_remaining == 0
                    # Moved to a bit field of another type, e.g. uint16 f1 : 8, uint32 f2 : 8;
                    or field_type != bits_type
                    # Still processing a bit field, but it's at a different offset due to alignment or a manual offset
                    or (bits_type is not None and offset > bits_field_offset + bits_type.size)
                ):
                    # ... if any of this is true, we have to move to the next field
                    bits_type = field_type
                    bits_count = bits_type.size * 8
                    bits_remaining = bits_count
                    bits_field_offset = offset

                    if offset is not None:
                        # We're not dynamic, update the structure size and current offset
                        offset += bits_type.size

                    field.offset = bits_field_offset

                bits_remaining -= field.bits

                if bits_remaining < 0:
                    raise ValueError("Straddled bit fields are unsupported")
            else:
                # Reset bits stuff
                bits_type = None
                bits_field_offset = bits_remaining = 0

                field.offset = offset

                if offset is not None:
                    # We're not dynamic, update the structure size and current offset
                    try:
                        field_len = len(field.type)
                    except TypeError:
                        # This field is dynamic
                        offset = None
                        self.dynamic = True
                        continue

                    offset += field_len

        if self.align and offset is not None:
            # Add "tail padding" if we need to align
            # This bit magic rounds up to the next alignment boundary
            # E.g. offset = 3; alignment = 8; -offset & (alignment - 1) = 5
            offset += -offset & (alignment - 1)

        # The structure size is whatever the currently calculated offset is
        self.size = offset
        self.alignment = alignment

    def _read(self, stream: BinaryIO, *args, **kwargs) -> Instance:
        bit_buffer = BitBuffer(stream, self.cstruct.endian)
        struct_start = stream.tell()

        result = OrderedDict()
        sizes = {}
        for field in self.fields:
            offset = stream.tell()
            field_type = self.cstruct.resolve(field.type)

            if field.offset and offset != struct_start + field.offset:
                # Field is at a specific offset, either alligned or added that way
                offset = struct_start + field.offset
                stream.seek(offset)

            if self.align and field.offset is None:
                # Previous field was dynamically sized and we need to align
                offset += -offset & (field.alignment - 1)
                stream.seek(offset)

            if field.bits:
                if isinstance(field_type, Enum):
                    value = field_type(bit_buffer.read(field_type.type, field.bits))
                else:
                    value = bit_buffer.read(field_type, field.bits)

                if field.name:
                    result[field.name] = value
                continue
            else:
                bit_buffer.reset()

            if isinstance(field_type, (Array, Pointer)):
                value = field_type._read(stream, result)
            else:
                value = field_type._read(stream)

            if isinstance(field_type, Structure) and field_type.anonymous:
                sizes.update(value._sizes)
                result.update(value._values)
            else:
                if field.name:
                    sizes[field.name] = stream.tell() - offset
                    result[field.name] = value

        if self.align:
            # Align the stream
            stream.seek(-stream.tell() & (self.alignment - 1), io.SEEK_CUR)

        return Instance(self, result, sizes)

    def _write(self, stream: BinaryIO, data: Instance) -> int:
        bit_buffer = BitBuffer(stream, self.cstruct.endian)
        struct_start = stream.tell()
        num = 0

        for field in self.fields:
            bit_field_type = (field.type.type if isinstance(field.type, Enum) else field.type) if field.bits else None
            # Current field is not a bit field, but previous was
            # Or, moved to a bit field of another type, e.g. uint16 f1 : 8, uint32 f2 : 8;
            if (not field.bits and bit_buffer._type is not None) or (
                bit_buffer._type and bit_buffer._type != bit_field_type
            ):
                # Flush the current bit buffer so we can process alignment properly
                bit_buffer.flush()

            offset = stream.tell()

            if field.offset and offset < struct_start + field.offset:
                # Field is at a specific offset, either alligned or added that way
                stream.write(b"\x00" * (struct_start + field.offset - offset))
                offset = struct_start + field.offset

            if self.align and field.offset is None:
                is_bitbuffer_boundary = bit_buffer._type and (
                    bit_buffer._remaining == 0 or bit_buffer._type != field.type
                )
                if not bit_buffer._type or is_bitbuffer_boundary:
                    # Previous field was dynamically sized and we need to align
                    align_pad = -offset & (field.alignment - 1)
                    stream.write(b"\x00" * align_pad)
                    offset += align_pad

            value = getattr(data, field.name, None)
            if value is None:
                value = field.type.default()

            if field.bits:
                if isinstance(field.type, Enum):
                    bit_buffer.write(field.type.type, value.value, field.bits)
                else:
                    bit_buffer.write(field.type, value, field.bits)
            else:
                if isinstance(field.type, Structure) and field.type.anonymous:
                    field.type._write(stream, data)
                else:
                    field.type._write(stream, value)
                num += stream.tell() - offset

        if bit_buffer._type is not None:
            bit_buffer.flush()

        if self.align:
            # Align the stream
            stream.write(b"\x00" * (-stream.tell() & (self.alignment - 1)))

        return num

    def add_field(self, name: str, type_: BaseType, offset: int = None) -> None:
        """Add a field to this structure.

        Args:
            name: The field name.
            type_: The field type.
            offset: The field offset.
        """
        field = Field(name, type_, offset=offset)
        self.fields.append(field)
        self.lookup[name] = field
        if isinstance(field.type, Structure) and field.type.anonymous:
            self.lookup.update(field.type.lookup)
        self.size = None

    def default(self) -> Instance:
        """Create and return an empty Instance from this structure.

        Returns:
            An empty Instance from this structure.
        """
        result = OrderedDict()
        for field in self.fields:
            if isinstance(field.type, Structure) and field.type.anonymous:
                result.update(field.type.default()._values)
            else:
                result[field.name] = field.type.default()

        return Instance(self, result)

    def show(self, indent: int = 0) -> None:
        """Pretty print this structure."""
        if indent == 0:
            print(f"struct {self.name}")

        for field in self.fields:
            if field.offset is None:
                offset = "0x??"
            else:
                offset = f"0x{field.offset:02x}"

            print(f"{' ' * indent}+{offset} {field.name} {field.type}")

            if isinstance(field.type, Structure):
                field.type.show(indent + 1)


class Union(Structure):
    """Type class for unions"""

    def __repr__(self) -> str:
        return f"<Union {self.name}>"

    def _calc_size_and_offsets(self) -> None:
        self.size = max(len(field.type) for field in self.fields)
        self.alignment = max(field.type.alignment for field in self.fields)

    def _read(self, stream: BinaryIO) -> Instance:
        buf = io.BytesIO(memoryview(stream.read(len(self))))
        result = OrderedDict()
        sizes = {}

        for field in self.fields:
            start = 0
            buf.seek(0)
            field_type = self.cstruct.resolve(field.type)

            if field.offset:
                buf.seek(field.offset)
                start = field.offset

            if isinstance(field_type, (Array, Pointer)):
                v = field_type._read(buf, result)
            else:
                v = field_type._read(buf)

            if isinstance(field_type, Structure) and field_type.anonymous:
                sizes.update(v._sizes)
                result.update(v._values)
            else:
                sizes[field.name] = buf.tell() - start
                result[field.name] = v

        return Instance(self, result, sizes)

    def _write(self, stream: BinaryIO, data: Instance) -> Instance:
        offset = stream.tell()

        # Find the largest field
        field = max(self.fields, key=lambda e: len(e.type))

        # Write the value to the stream using the largest field type
        if isinstance(field.type, Structure) and field.type.anonymous:
            field.type._write(stream, data)
        else:
            field.type._write(stream, getattr(data, field.name))

        return stream.tell() - offset

    def show(self, indent: int = 0) -> None:
        raise NotImplementedError()
