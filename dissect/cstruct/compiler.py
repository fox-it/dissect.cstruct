# Made in Japan

from __future__ import annotations

import io
import logging
import struct
from enum import Enum
from itertools import groupby, repeat
from keyword import iskeyword
from operator import itemgetter
from textwrap import indent
from typing import TYPE_CHECKING, Any

from dissect.cstruct.exception import ArraySizeError, ExpressionParserError
from dissect.cstruct.expression import SOURCE_GLOBALS, Expression
from dissect.cstruct.types import (
    Array,
    BaseArray,
    Char,
    CharArray,
    Flag,
    Int,
    Packed,
    Pointer,
    Structure,
    Union,
    Void,
    VoidArray,
    Wchar,
    WcharArray,
)
from dissect.cstruct.types.enum import EnumMetaType
from dissect.cstruct.types.structure import StructureMetaType, UnionMetaType, UnionProxy
from dissect.cstruct.util import ENDIANNESS_TO_BYTEORDER_MAP, _struct

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from types import MethodType
    from typing import BinaryIO

    from dissect.cstruct.types import BaseType
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
    VoidArray,
)

log = logging.getLogger(__name__)

python_compile = compile


def compile_structure(cls: type[Structure]) -> type[Structure]:
    """Compile the ``_read`` and ``_write`` methods of a structure or union type, if the compiler supports it.

    The compilation happens on first use.
    """
    try:
        _check_supported(cls, cls.__fields__)
        cls._read = _LazyCompileRead(cls)
        cls._write = _LazyCompileWrite(cls)
        cls.__compiled__ = True
    except Exception as e:
        # Revert to the interpreted reader and writer
        log.debug("Failed to compile %s", cls, exc_info=e)
        _revert_to_interpreted(cls)

    return cls


def _revert_to_interpreted(cls: type[Structure]) -> None:
    cls._read = classmethod(type(cls)._read)
    cls._write = classmethod(type(cls)._write)
    cls.__compiled__ = False


class _LazyCompile:
    """Descriptor that compiles a method of a structure on first access and replaces itself with it."""

    name: str

    def __init__(self, cls: type[Structure]):
        self.cls = cls
        self.fields = list(cls.__fields__)
        self.method = None

        # Snapshot of the nested structure types, so that we only inline them if they're unchanged on first use
        self.snapshot = _snapshot_structures(self.fields, {})

    def __get__(self, obj: Any, owner: type | None = None) -> MethodType:
        return self.compile().__get__(obj, owner)

    def compile(self) -> classmethod:
        if self.method is None:
            cls = self.cls

            # Since we lazily compile, some of the nested structures may have changed
            # Only inline if they're the same as when we last built the structure
            inline = all(type_.__dict__.get("__init__") is init for type_, init in self.snapshot.items())

            try:
                self.method = self._generator(inline).generate()
            except Exception as e:
                # Revert to the slower interpreted method
                log.debug("Failed to compile %s", cls, exc_info=e)
                self.method = self._revert()

            if cls.__dict__.get(self.name) is self:
                setattr(cls, self.name, self.method)

        return self.method

    def _generator(self, inline: bool) -> _SourceGenerator:
        raise NotImplementedError

    def _revert(self) -> classmethod:
        """Return the interpreted version of the method."""
        return classmethod(getattr(type(self.cls), self.name))


class _LazyCompileRead(_LazyCompile):
    """Descriptor that compiles the ``_read`` method of a structure on first access and replaces itself with it."""

    name = "_read"

    def _generator(self, inline: bool) -> _SourceGenerator:
        return _ReadSourceGenerator(self.cls, self.fields, inline)

    def _revert(self) -> classmethod:
        # The structure no longer counts as compiled, so adding a field won't recompile _write either
        _revert_to_interpreted(self.cls)
        return super()._revert()


class _LazyCompileWrite(_LazyCompile):
    """Descriptor that compiles the ``_write`` method of a structure on first access and replaces itself with it."""

    name = "_write"

    def _generator(self, inline: bool) -> _SourceGenerator:
        return _WriteSourceGenerator(self.cls, self.fields, inline)


def _snapshot_structures(fields: list[Field], result: dict[type, Any]) -> dict[type, Any]:
    for field in fields:
        type_ = field.type
        if issubclass(type_, Structure) and type_ not in result:
            result[type_] = type_.__dict__.get("__init__")
            _snapshot_structures(type_.__fields__, result)
    return result


def _check_supported(cls: type[Structure], fields: list[Field]) -> None:
    """Check if the compiler supports the given fields."""
    if issubclass(cls, Union):
        _check_union(cls, fields)
        return

    for field in fields:
        field_type = field.type

        if isinstance(field_type, EnumMetaType):
            field_type = field_type.__type__

        if not issubclass(field_type, SUPPORTED_TYPES):
            raise TypeError(f"Unsupported type for compiler: {field_type}")

        if field.bits and field_type.__dynamic__:
            raise TypeError(f"Unsupported type for bit field: {field_type}")


class _Fallback:
    """Lazily compiled ``_read`` function without inlined structures.

    Used when one of the inlined structure types was modified after compilation.
    """

    def __init__(self, cls: type[Structure], fields: list[Field]):
        self.cls = cls
        self.fields = list(fields)
        self.func = None

    def __call__(self, cls: type[Structure], stream: BinaryIO, context: dict[str, Any] | None, endian: str) -> Any:
        if self.func is None:
            self.func = _ReadSourceGenerator(self.cls, self.fields, inline=False).generate().__func__
        return self.func(cls, stream, context=context, endian=endian)


_ENDIANNESS = ("<", ">", "!", "@", "=")

# Types of which the value can be used as an integer directly
_INTEGER_TYPES = (Int, Packed, Enum, Flag)

# Types of which the value can be packed, unless they have a custom way of writing
_PACKABLE_TYPES = (Array, Char, CharArray, Int, Packed, Pointer, Void, VoidArray, Wchar, WcharArray)


def _field_bytes(type_: type[BaseType], value: Any, endian: str) -> bytes:
    """Return the bytes of a char or wchar field that isn't of the right type yet or doesn't fit."""
    buf = type_.dumps(type_.__default__() if value is None else value, endian=endian)
    if len(buf) > type_.__size__:
        raise ArraySizeError(f"Expected {type_.__size__} bytes for {type_.__name__}, got {len(buf)} instead.")
    return buf


def _array_values(type_: type[Array], value: list[Any] | None) -> list[Any]:
    """Return the values of an array field that doesn't have the right size yet."""
    return type_.__default__() if value is None else type_._pad(value)


def _or_default(value: Any, type_: type[BaseType]) -> Any:
    """Return the value of a field, or the default of its type if it's ``None``."""
    return type_.__default__() if value is None else value


# Globals that are available to all generated functions
_GLOBALS = {
    "_type_call": type.__call__,
    "_object_new": object.__new__,
    "_setattr": setattr,
    "_repeat": repeat,
    "_int_from_bytes": int.from_bytes,
    "_byteorder": ENDIANNESS_TO_BYTEORDER_MAP,
    "_object_setattr": object.__setattr__,
    "_getattr": getattr,
    "_UnionProxy": UnionProxy,
    "_union_read": UnionMetaType._read,
    "_struct_write": StructureMetaType._write,
    "_union_write": UnionMetaType._write,
    "_struct_error": struct.error,
    "_field_bytes": _field_bytes,
    "_array_values": _array_values,
    "_or_default": _or_default,
    **SOURCE_GLOBALS,
}


class _SourceGenerator:
    """Base class for generating the source code of an optimized method of a structure or union."""

    name: str

    def __init__(self, cls: type[Structure], fields: list[Field], inline: bool = True):
        self.cls = cls
        self.fields = fields
        self.align = cls.__align__
        self.inline = inline and not self.align

        # The values available to the generated code
        self.symbols: dict[str, Any] = {"cs": cls.__cs__}
        self._symbol_names: dict[int, str] = {}

        # Witnesses of inlined structure types (symbol of the type -> symbol of its __init__ at compile time)
        self._witnesses: dict[str, str] = {}

        # The state of the bit buffer: the type of its current value and the remaining bits
        self._bits: tuple[type[BaseType], int] | None = None
        self._var_ids: dict[str, int] = {}

    def _type_symbol(self, type_: type[BaseType]) -> str:
        """Add a type as symbol, returns its name."""
        return self._add_symbol(type_, "type")

    def _add_symbol(self, value: Any, name: str) -> str:
        """Add a value that is available to the generated code, returns its name."""
        if (symbol := self._symbol_names.get(id(value))) is None:
            symbol = self._symbol_names[id(value)] = self._var(name)
            self.symbols[symbol] = value
        return symbol

    def _var(self, name: str) -> str:
        """Return a unique variable name for the generated code."""
        index = self._var_ids.get(name, 0)
        self._var_ids[name] = index + 1
        return f"_{name}{index}"

    def _witness(self, type_: type[Structure]) -> str:
        """Add an inlined type as symbol, with a witness to detect modifications to it after compilation."""
        symbol = self._type_symbol(type_)
        self._witnesses[symbol] = self._add_symbol(type_.__init__, "init")
        return symbol

    def _modified_checks(self) -> list[str]:
        """Return the conditions that are true if any of the inlined types were modified after compilation."""
        return [f"{type_}.__init__ is not {init}" for type_, init in self._witnesses.items()]

    def _starts_bit_value(self, field: Field) -> bool:
        """Return whether a bit field is the first of a new value of the bit buffer."""
        return self._bits is None or self._bits[1] == 0 or self._bits[0] is not _get_bit_buffer_type(field)

    def _advance_bits(self, field: Field) -> int:
        """Update the state of the bit buffer for a bit field, returns the bits that were remaining before it."""
        if self._starts_bit_value(field):
            self._bits = (_get_bit_buffer_type(field), _get_bits_type(field).__size__ * 8)
        remaining = self._bits[1]
        self._bits = (self._bits[0], remaining - field.bits)
        return remaining

    def generate(self) -> MethodType:
        source = self.generate_source()

        code = python_compile(source, f"<compiled {self.cls.__name__}.{self.name}>", "exec")
        exec(code, {**_GLOBALS, **self.symbols}, d := {})
        obj = d.popitem()[1]
        obj.__source__ = source

        return classmethod(obj)

    def generate_source(self) -> str:
        if issubclass(self.cls, Union):
            return self._generate_union_source()
        return self._generate_struct_source()

    def _generate_struct_source(self) -> str:
        raise NotImplementedError

    def _generate_union_source(self) -> str:
        raise NotImplementedError


class _ReadSourceGenerator(_SourceGenerator):
    """Generates the source code of an optimized ``_read`` method for a structure or union."""

    name = "_read"

    def __init__(self, cls: type[Structure], fields: list[Field], inline: bool = True):
        super().__init__(cls, fields, inline)

        self._fallback_symbol: str | None = None

        # (field name, local variable name) of all fields assigned so far
        self._assigned: list[tuple[str, str]] = []
        self._has_context = False
        self._uses_start = False
        self._uses_sizes = False

    def _context(self, lines: list[str]) -> str:
        """Return the name of the context dictionary, creating it from the fields read so far if needed."""
        if not self._has_context:
            self._has_context = True
            items = ", ".join(f"{name!r}: {var}" for name, var in self._assigned)
            lines.append(f"values = {{{items}}}")

        return "values"

    def _assign(self, field: Field, value: str) -> str:
        """Assign a value to a new local variable for the given field, and the context dictionary if it exists."""
        var = f"_value{len(self._assigned)}"
        self._assigned.append((field._name, var))
        if self._has_context:
            return f"{var} = values[{field._name!r}] = {value}"
        return f"{var} = {value}"

    def _assign_local(self, field: Field, value: str) -> list[str]:
        return [self._assign(field, value)]

    def _fallback(self) -> str:
        """Return the symbol of the non-inlined fallback read function."""
        if self._fallback_symbol is None:
            fallback = _Fallback(self.cls, self.fields)
            self._fallback_symbol = self._add_symbol(fallback, "fallback")
        return self._fallback_symbol

    def _generate_struct_source(self) -> str:
        """Generate the code for reading a structure."""
        read_code = "\n".join(self._generate_fields_source())

        preamble = []
        if checks := self._modified_checks():
            # Fall back to the non-inlined version if any of the inlined types was modified after compilation
            preamble.append(f"if {' or '.join(checks)}: return {self._fallback()}(cls, stream, context, endian)")
        if self._uses_sizes:
            preamble.append("sizes = {}")
        if self._uses_start:
            preamble.append("start = stream.tell()")

        sizes = "sizes" if self._uses_sizes else "{}"
        kwargs = ", ".join(f"{name!r}: {var}" for name, var in self._assigned)
        outro = []

        if self._can_construct_directly():
            # Construct the object directly if we're reading the exact structure class we compiled for
            # This bypasses the __init__ method
            outro.append(f"if cls is {self._add_symbol(self.cls, 'cls')}:")
            outro.append("    obj = _object_new(cls)")
            for name, var in self._assigned:
                outro.append(f"    {_set_attribute('obj', name, var)}")
            outro.append(f"    obj.__dynamic_sizes__ = {sizes}")
            outro.append("    return obj")

        # Using type.__call__ directly calls the __init__ method of the class
        outro.append(f"obj = _type_call(cls, **{{{kwargs}}})")
        outro.append(f"obj.__dynamic_sizes__ = {sizes}")
        outro.append("return obj")

        code = indent("\n".join([*preamble, read_code, *outro]), "    ")

        return f"def _read(cls, stream, *, context=None, endian):\n{code}"

    def _can_construct_directly(self) -> bool:
        if not _uses_generated_init(self.cls):
            return False

        # Void fields are not read and rely on the default value set by __init__
        return not any(issubclass(_get_read_type(field.type), (Void, VoidArray)) for field in self.fields)

    def _generate_union_source(self) -> str:
        """Generate the code for reading a union."""
        size = _check_union(self.cls, self.fields, self.inline)

        lines = ["obj = _object_new(cls)"]
        self._pack_union("obj", self.fields, 0, "buf", lines)

        # Fall back to the generic method if any of the inlined types was modified after compilation
        checks = [f"cls is not {self._add_symbol(self.cls, 'cls')}", *self._modified_checks()]

        preamble = [
            f"if {' or '.join(checks)}: return _union_read(cls, stream, context=context, endian=endian)",
            f"buf = stream.read({size})",
            _check_eof(size),
        ]
        code = indent("\n".join([*preamble, *lines, "return obj"]), "    ")

        return f"def _read(cls, stream, *, context=None, endian):\n{code}"

    def _generate_fields_source(self) -> Iterator[str]:
        """Generate the code for reading all fields."""
        _check_supported(self.cls, self.fields)

        # The offset of the current field in the structure, None if it's unknown due to a dynamic field
        current_offset = 0
        current_block: list[Field] = []

        def flush() -> Iterator[str]:
            if current_block:
                yield from self._generate_packed_source(current_block)
                current_block[:] = []

        def align_to_field(field: Field) -> Iterator[str]:
            nonlocal current_offset

            if field.offset is not None and field.offset != current_offset:
                # If a field has a set offset and it's not the same as the current tracked offset, seek to it
                self._uses_start = True
                yield f"stream.seek(start + {field.offset})"
                current_offset = field.offset

            if self.align and field.offset is None:
                yield f"stream.seek(-stream.tell() & ({field.alignment} - 1), {io.SEEK_CUR})"

        for field in self.fields:
            field_type = field.type

            if isinstance(field_type, EnumMetaType):
                field_type = field_type.__type__

            if not field.bits:
                self._bits = None

            size = field_type.__size__

            # Sub structure that we can inline into the current block
            inline = (
                self.inline
                and field.offset is not None
                and field.offset == current_offset
                and _inline_kind(field_type) is not None
            )

            # Sub structures, arrays of structures, multi-dimensional and dynamic arrays
            if (issubclass(field_type, Structure) and not inline) or (
                issubclass(field_type, (Array, CharArray, WcharArray))
                and (issubclass(field_type.__type__, (Structure, BaseArray)) or size is None)
            ):
                yield from flush()
                yield from align_to_field(field)
                yield from self._generate_field_source(field)

            # Bit fields
            elif field.bits:
                if not self._starts_bit_value(field):
                    # Only reading a new value into the bit buffer moves the stream
                    size = 0

                yield from flush()
                yield from align_to_field(field)
                yield from self._generate_bits_source(field)

            # Everything else - basic and composite types (and arrays of them), and inlined structures
            else:
                if field.offset is None:
                    # The alignment depends on the position in the stream, so this needs a new block
                    if self.align:
                        yield from flush()
                # A block is read in order, so a field before the current position needs a new block
                elif current_offset is None or field.offset < current_offset:
                    yield from flush()
                elif current_block:
                    current_offset = field.offset

                if not current_block:
                    yield from align_to_field(field)
                current_block.append(field)

            if current_offset is not None:
                current_offset = None if size is None else current_offset + size

        yield from flush()

        if self.align:
            yield f"stream.seek(-stream.tell() & (cls.__alignment__ - 1), {io.SEEK_CUR})"

    def _generate_field_source(self, field: Field) -> Iterator[str]:
        """Generate the code for reading and assigning a field."""
        lines = []
        read = self._generate_field_read_source(field, lines)

        if field.type.__dynamic__:
            self._uses_sizes = True
            lines.append("_offset = stream.tell()")
            lines.append(self._assign(field, read))
            lines.append(f"sizes[{field._name!r}] = stream.tell() - _offset")
        else:
            lines.append(self._assign(field, read))

        yield _block(lines)

    def _generate_field_read_source(self, field: Field, lines: list[str]) -> str:
        """Generate the code for reading a field."""
        context = self._context(lines)
        type_ = self._type_symbol(field.type)
        read = f"{type_}._read(stream, context={context}, endian=endian)"

        num_entries = getattr(field.type, "__num_entries__", None)
        if not isinstance(num_entries, Expression) or num_entries.expression == "EOF":
            return read

        # If the field is a dynamic array, generate the code for the length evaluation
        # Integer fields that were read before are used directly
        types = {field._name: field.type for field in self.fields}
        variables = {name: f"int({var})" for name, var in self._assigned if issubclass(types[name], _INTEGER_TYPES)}
        try:
            count = num_entries.source(variables, context)
        except ExpressionParserError:
            # Invalid expressions raise their error when reading the array
            return read

        lines.append(f"_count = max(0, {count})")
        element = self._type_symbol(field.type.__type__)
        return f"_type_call({type_}, {element}._read_array(stream, _count, context={context}, endian=endian))"

    def _generate_bits_source(self, field: Field) -> Iterator[str]:
        """Generate the code for reading a bit field."""
        read_type = _get_bits_type(field)
        new_value = self._starts_bit_value(field)
        remaining = self._advance_bits(field)

        lines = []
        if new_value:
            lines.append(f"_bit_buffer = {self._type_symbol(read_type)}._read(stream, endian=endian)")

        if field.bits > remaining:
            lines.append('raise ValueError("Reading straddled bits is unsupported")')
            yield _block(lines)
            return

        mask = (1 << field.bits) - 1
        # The bit buffer only reads the least significant bits first for explicit little endian
        lines.append(f'if endian == "<": _bit_value = _bit_buffer & {mask}; _bit_buffer >>= {field.bits}')
        lines.append(f"else: _bit_value = (_bit_buffer >> {remaining - field.bits}) & {mask}")

        # Character bit fields are returned as the integer type they're read as
        type_ = self._type_symbol(read_type if issubclass(field.type, Char) else field.type)

        if issubclass(field.type, (Enum, Flag)):
            lines.append(_member_lookup(type_, "_bit_value"))
            lines.append(self._assign(field, "_member"))
        else:
            lines.append(self._assign(field, f"_type_call({type_}, _bit_value)"))

        yield _block(lines)

    def _generate_packed_source(self, fields: list[Field]) -> Iterator[str]:
        """Generate the code for reading consecutive packed fields."""
        unpack = _Unpack("data")
        reads = []
        size = self._pack_fields(fields, 0, unpack, reads, self._assign_local)

        lines = [f"buf = stream.read({size})", _check_eof(size)]
        if unpack.has_values():
            lines.append(f"data = {self._add_symbol(unpack.functions('unpack'), 'unpack')}[endian](buf)")

        yield _block(lines + reads)

    def _pack_fields(
        self,
        fields: list[Field],
        offset: int,
        unpack: _Unpack,
        lines: list[str],
        target: Callable[[Field, str], list[str]],
    ) -> int:
        """Generate the code for reading the given fields from ``buf``, starting at the given offset.

        Unpackable values are added to the given ``unpack`` format, and accessed through its variable.
        Every field value is passed to ``target``, which returns the lines that store the value.

        Returns the offset after the last field.
        """
        inline = _inline_kind if self.inline else None
        for field, count, char in _generate_struct_info(fields, inline=inline):
            if field is None:
                # Padding
                unpack.add(count, "x")
                offset += count
                continue

            if char == "S":
                # Inlined structure
                type_ = field.type
                var = self._var("object")
                lines.append(f"{var} = _object_new({self._witness(type_)})")
                end = self._pack_fields(type_.__fields__, offset, unpack, lines, _attr_target(var))
                if padding := offset + type_.__size__ - end:
                    unpack.add(padding, "x")
                lines.append(f"{var}.__dynamic_sizes__ = {{}}")
                lines.extend(target(field, var))
                offset += type_.__size__
                continue

            if char == "U":
                # Inlined union
                type_ = field.type
                var = self._var("union")
                lines.append(f"{var} = _object_new({self._witness(type_)})")
                self._pack_union(var, type_.__fields__, offset, f"buf[{offset}:{offset + type_.__size__}]", lines)
                lines.extend(target(field, var))
                unpack.add(type_.__size__, "x")
                offset += type_.__size__
                continue

            field_type = field.type
            read_type = _get_read_type(field_type)
            is_array = issubclass(field_type, (Array, CharArray, WcharArray))
            if is_array:
                read_type = _get_read_type(field_type.__type__)

            if char == "x":
                # Byte based types are sliced directly out of the buffer, with the count in bytes
                getter = f"buf[{offset}:{offset + count}]"
            elif is_array:
                getter = f"{unpack.var}[{unpack.index}:{unpack.index + count}]"
            else:
                getter = f"{unpack.var}[{unpack.index}]"

            lines.extend(self._generate_packed_field_source(field, read_type, getter, count, target))
            unpack.add(count, char)
            offset += field_type.__size__

        return offset

    def _pack_union(self, var: str, fields: list[Field], offset: int, data: str, lines: list[str]) -> None:
        """Generate the code for reading a union from ``buf`` into ``var``.

        The union starts at the given offset in ``buf``, ``data`` is the code for its own bytes.
        """
        for member in fields:
            member_offset = offset + (member.offset or 0)
            unpack = _Unpack(self._var("data"))
            member_lines = []
            self._pack_fields([member], member_offset, unpack, member_lines, _union_target(var))

            if unpack.has_values():
                unpack_from = self._add_symbol(unpack.functions("unpack_from"), "unpack_from")
                lines.append(f"{unpack.var} = {unpack_from}[endian](buf, {member_offset})")
            lines.extend(member_lines)

        lines.append(f"_object_setattr({var}, '__dynamic_sizes__', {{}})")
        lines.append(f"_object_setattr({var}, '_buf', {data})")
        lines.append(f"_object_setattr({var}, '_endian', endian)")
        self._proxify(var, var, fields, lines)

    def _proxify(self, union: str, var: str, fields: list[Field], lines: list[str], attr: str | None = None) -> None:
        """Generate the code equivalent to ``Union._proxify``."""
        for field in fields:
            if issubclass(field.type, Structure):
                nested = self._var("nested")
                member = attr or field._name
                lines.append(f"{nested} = _getattr({var}, {field._name!r})")
                lines.append(f"_object_setattr({var}, {field._name!r}, _UnionProxy({union}, {member!r}, {nested}))")
                self._proxify(union, nested, field.type.__fields__, lines, member)

    def _generate_packed_field_source(
        self,
        field: Field,
        read_type: type[BaseType],
        getter: str,
        count: int,
        target: Callable[[Field, str], list[str]],
    ) -> list[str]:
        """Generate the code for reading a packed field."""
        field_type = field.type
        lines = []

        if issubclass(field_type, Array):
            array = self._type_symbol(field.type)
            element = self._type_symbol(field_type.__type__)

            if issubclass(read_type, Int):
                # Everything that's read as an integer type is sliced directly out of the buffer
                elem_size = read_type.__size__
                signed = bool(read_type.signed)
                lines.append(f"_array_buf = {getter}")
                raw = f"_int_from_bytes(_array_buf[i:i + {elem_size}], _byteorder[endian], signed={signed})"
                getter = f"[{raw} for i in range(0, {count}, {elem_size})]"

            if issubclass(field_type.__type__, Pointer):
                context = self._context(lines)
                item = f"{element}.__new__({element}, value, stream, context={context}, endian=endian)"
                value = f"[{item} for value in {getter}]"
            else:
                value = f"list(map(_type_call, _repeat({element}), {getter}))"

            lines.extend(target(field, f"_type_call({array}, {value})"))

        elif issubclass(field_type, CharArray):
            lines.extend(target(field, f"_type_call({self._type_symbol(field.type)}, {getter})"))

        elif issubclass(field_type, WcharArray) or issubclass(read_type, Wchar):
            encoding = self._add_symbol(read_type.__encoding_map__, "encoding")
            # Using str() instead of .decode() also supports other bytes-like objects returned by the stream
            type_ = self._type_symbol(field.type)
            lines.extend(target(field, f"_type_call({type_}, str({getter}, {encoding}[endian], 'surrogatepass'))"))

        elif issubclass(field_type, Pointer):
            context = self._context(lines)
            type_ = self._type_symbol(field.type)
            lines.extend(target(field, f"{type_}.__new__({type_}, {getter}, stream, context={context}, endian=endian)"))

        elif issubclass(field_type, (Enum, Flag)):
            # Fast path the member lookup, the slow path takes care of unknown values
            if issubclass(read_type, Int):
                raw = f"_int_from_bytes({getter}, _byteorder[endian], signed={bool(read_type.signed)})"
            else:
                raw = getter

            lines.append(f"_enum_value = {raw}")
            lines.append(_member_lookup(self._type_symbol(field.type), "_enum_value"))
            lines.extend(target(field, "_member"))

        elif issubclass(read_type, Int):
            signed = bool(read_type.signed)
            value = f"_int_from_bytes({getter}, _byteorder[endian], signed={signed})"
            lines.extend(target(field, f"_type_call({self._type_symbol(field.type)}, {value})"))

        else:
            lines.extend(target(field, f"_type_call({self._type_symbol(field.type)}, {getter})"))

        return lines


class _Unpack:
    """Tracks consecutive struct unpack formats."""

    def __init__(self, var: str):
        self.var = var
        self.index = 0
        self.items: list[tuple[int, str]] = []

    def add(self, count: int, char: str) -> None:
        self.items.append((count, char))
        if char != "x":
            self.index += count

    def has_values(self) -> bool:
        return self.index > 0

    def functions(self, name: str) -> dict[str, Callable]:
        """Return the given function of the struct for every endianness."""
        return _struct_functions(_optimize_struct_fmt(self.items), name)


class _WriteSourceGenerator(_SourceGenerator):
    """Generates the source code of an optimized ``_write`` method for a structure or union."""

    name = "_write"

    def __init__(self, cls: type[Structure], fields: list[Field], inline: bool = True):
        super().__init__(cls, fields, inline)

        self._uses_start = False

    def _generate_method_source(self, interpreted: str, lines: Iterable[str]) -> str:
        """Generate the code of the method, ``interpreted`` is the name of the method to fall back to."""
        write_code = "\n".join(lines)

        # Fall back to the generic method if any of the inlined types was modified after compilation
        checks = [f"cls is not {self._add_symbol(self.cls, 'cls')}", *self._modified_checks()]

        preamble = [f"if {' or '.join(checks)}: return {interpreted}(cls, stream, data, endian=endian)"]
        if self._uses_start:
            preamble.append("start = stream.tell()")

        code = indent("\n".join([*preamble, write_code]), "    ")

        return f"def _write(cls, stream, data, *, endian):\n{code}"

    def _generate_struct_source(self) -> str:
        """Generate the code for writing a structure."""
        return self._generate_method_source("_struct_write", list(self._generate_fields_source()))

    def _generate_union_source(self) -> str:
        """Generate the code for writing a union."""
        if not _can_pack(self.cls):
            raise TypeError(f"Unsupported union for compiler: {self.cls}")

        pack = _Pack()
        self._pack_union("data", self.cls, pack)

        lines = [self._generate_pack_source(pack), f"return {self.cls.__size__}"]
        return self._generate_method_source("_union_write", lines)

    def _generate_fields_source(self) -> Iterator[str]:
        """Generate the code for writing all fields."""
        # The offset of the current field in the structure, None if it's unknown due to a dynamic field
        current_offset = 0
        current_block: list[Field] = []
        current_bits: list[Field] = []

        def flush() -> Iterator[str]:
            if current_block:
                yield from self._generate_packed_source(current_block)
                current_block[:] = []
            if current_bits:
                yield from self._generate_bits_source(current_bits)
                current_bits[:] = []

        def align_to_field(field: Field) -> Iterator[str]:
            nonlocal current_offset

            if field.offset is not None and field.offset != current_offset:
                if current_offset is None:
                    # This only writes padding if the stream is before the offset, otherwise the amount is negative
                    yield f'stream.write(b"\\x00" * (start + {field.offset} - stream.tell()))'
                else:
                    yield f"stream.write({bytes(field.offset - current_offset)!r})"
                    current_offset = field.offset

            if self.align and field.offset is None:
                yield f'stream.write(b"\\x00" * (-stream.tell() & ({field.alignment} - 1)))'

        for field in self.fields:
            if not field.bits:
                self._bits = None
                if current_bits:
                    yield from flush()

            # Unlike reading, we can't move back in the stream
            if None not in (field.offset, current_offset) and field.offset < current_offset:
                raise TypeError(f"Unsupported offset for compiler: {field}")

            size = field.type.__size__

            # Bit fields
            if field.bits:
                if self._starts_bit_value(field):
                    if not _can_pack_bits(field):
                        raise TypeError(f"Unsupported type for bit field: {field.type}")

                    yield from flush()
                    yield from align_to_field(field)
                elif field.offset is not None:
                    raise TypeError(f"Unsupported offset for bit field: {field}")
                else:
                    # Only the first bit field of a value moves the stream
                    size = 0

                self._advance_bits(field)
                current_bits.append(field)

            # Basic and composite types (and arrays of them), and inlined structures
            elif _can_pack(field.type):
                if field.offset is None:
                    # The alignment depends on the position in the stream, so this needs a new block
                    if self.align:
                        yield from flush()
                elif current_offset is None:
                    yield from flush()
                elif current_block:
                    current_offset = field.offset

                if not current_block:
                    yield from align_to_field(field)
                current_block.append(field)

            # Everything else - sub structures, arrays of structures, multi-dimensional and dynamic arrays
            else:
                yield from flush()
                yield from align_to_field(field)
                yield from self._generate_field_source(field)

                # An aligned structure writes more than its size if the stream isn't aligned
                if self.align:
                    size = None

            if current_offset is not None:
                current_offset = None if size is None else current_offset + size

        yield from flush()

        if self.align:
            self._uses_start = True
            yield 'stream.write(b"\\x00" * (-stream.tell() & (cls.__alignment__ - 1)))'

        yield "return stream.tell() - start" if self._uses_start else f"return {current_offset}"

    def _generate_field_source(self, field: Field) -> Iterator[str]:
        """Generate the code for writing a field using its type."""
        self._uses_start = True
        type_ = self._type_symbol(field.type)
        lines = [
            f"_value = {_get_attribute('data', field._name)}",
            f"if _value is None: _value = {type_}.__default__()",
            f"{type_}._write(stream, _value, endian=endian)",
        ]

        yield _block(lines)

    def _generate_bits_source(self, fields: list[Field]) -> Iterator[str]:
        """Generate the code for writing the bit fields that share a value of the bit buffer."""
        type_ = _get_bits_type(fields[0])

        pack = _Pack()
        little = []
        other = []
        remaining = type_.__size__ * 8
        for field in fields:
            value = self._load_value(field, _get_attribute("data", field._name), pack)
            if issubclass(field.type, (Enum, Flag)):
                value += "._value_"

            remaining -= field.bits
            little.append(f"{value} << {type_.__size__ * 8 - remaining - field.bits}")
            other.append(f"{value} << {remaining}")

        # The bit buffer only writes the least significant bits first for explicit little endian
        self._pack_number(type_, f"({' | '.join(little)} if endian == '<' else {' | '.join(other)})", pack)

        yield self._generate_pack_source(pack)

    def _generate_packed_source(self, fields: list[Field]) -> Iterator[str]:
        """Generate the code for writing consecutive packed fields."""
        pack = _Pack()
        self._pack_fields(fields, "data", pack)

        if pack.items:
            yield self._generate_pack_source(pack)

    def _generate_pack_source(self, pack: _Pack) -> str:
        """Generate the code for checking, packing and writing values."""
        function = f"{self._add_symbol(pack.functions('pack'), 'pack')}[endian]"
        if pack.values == pack.retry:
            return _block([*pack.lines, f"stream.write({function}({', '.join(pack.values)}))"])

        # Numbers aren't checked for None up front, since struct.pack raises an error for those
        return _block(
            [
                *pack.lines,
                "try:",
                f"    buf = {function}({', '.join(pack.values)})",
                "except _struct_error:",
                f"    buf = {function}({', '.join(pack.retry)})",
                "stream.write(buf)",
            ]
        )

    def _load_value(self, field: Field, value: str, pack: _Pack) -> str:
        """Generate the code for loading a value, using the default of its type if it's ``None``."""
        var = self._var("value")
        pack.lines.append(f"if ({var} := {value}) is None: {var} = {self._type_symbol(field.type)}.__default__()")
        return var

    def _pack_fields(self, fields: list[Field], var: str, pack: _Pack, proxied: bool = False) -> None:
        """Generate the code for packing the given fields of the object in ``var``.

        The fields of objects in a union are proxied, in which case we use the object behind the proxy.
        """
        for field, count, char in _generate_struct_info(fields, inline=_inline_kind):
            if field is None:
                # Padding
                pack.add(count, "x")
                continue

            value = _get_attribute(var, field._name)

            if char in ("S", "U"):
                # Inlined structure or union
                self._witness(field.type)
                nested = self._load_value(field, value, pack)
                if proxied:
                    pack.lines.append(f"if type({nested}) is _UnionProxy: {nested} = {nested}.__target__")

                if char == "S":
                    self._pack_fields(field.type.__fields__, nested, pack, proxied)
                else:
                    self._pack_union(nested, field.type, pack)
                continue

            self._pack_field(field, value, count, char, pack)

    def _pack_union(self, var: str, type_: type[Union], pack: _Pack) -> None:
        """Generate the code for packing the union in ``var``, by the field the interpreted writer uses."""
        # Changing a nested structure can change which field is the largest
        for field in type_.__fields__:
            if issubclass(field.type, Structure):
                self._witness(field.type)

        self._pack_fields([type_._write_field()], var, pack, proxied=True)

    def _pack_field(self, field: Field, value: str, count: int, char: str, pack: _Pack) -> None:
        """Generate the code for checking and packing a field."""
        field_type = field.type
        read_type = _get_read_type(field_type)
        type_ = self._type_symbol(field_type)

        if issubclass(field_type, Array):
            read_type = _get_read_type(field_type.__type__)
            var = self._var("value")
            num = field_type.__num_entries__
            pack.lines.append(
                f"if ({var} := {value}) is None or len({var}) != {num}: {var} = _array_values({type_}, {var})"
            )

            # Entries can be enum members or plain integers, both can be packed as they are
            if issubclass(read_type, Int):
                pack.add(count, "s", f"b''.join([{_int_to_bytes(read_type, 'item')} for item in {var}])")
            else:
                pack.add(count, char, f"*{var}")

        elif issubclass(field_type, (Char, CharArray, Wchar, WcharArray)):
            var = self._var("value")

            # The format pads values that are too short with zeroes
            if issubclass(field_type, (Wchar, WcharArray)):
                encoding = self._add_symbol(Wchar.__encoding_map__, "encoding")
                pack.lines.append(
                    f"if ({var} := {value}) is None or "
                    f"len({var} := {var}.encode({encoding}[endian], 'surrogatepass')) > {count}: "
                    f"{var} = _field_bytes({type_}, {value}, endian)"
                )
            else:
                pack.lines.append(
                    f"if not isinstance({var} := {value}, bytes) or len({var}) > {count}: "
                    f"{var} = _field_bytes({type_}, {var}, endian)"
                )

            pack.add(count, "s", var)

        elif issubclass(field_type, (Enum, Flag)):
            self._pack_number(read_type, f"{self._load_value(field, value, pack)}._value_", pack)

        elif issubclass(read_type, Packed):
            pack.add(1, read_type.__fmt__, value, f"_or_default({value}, {type_})")

        else:
            self._pack_number(read_type, self._load_value(field, value, pack), pack)

    def _pack_number(self, type_: type[BaseType], value: str, pack: _Pack) -> None:
        """Generate the code for packing a value of an integer or packed type."""
        if issubclass(type_, Int):
            pack.add(type_.__size__, "s", _int_to_bytes(type_, value))
        else:
            pack.add(1, type_.__fmt__, value)


class _Pack:
    """Tracks consecutive struct pack formats, and the code for the values to pack."""

    def __init__(self):
        self.items: list[tuple[int, str]] = []
        self.lines: list[str] = []
        self.values: list[str] = []
        self.retry: list[str] = []

    def add(self, count: int, char: str, value: str | None = None, retry: str | None = None) -> None:
        self.items.append((count, char))
        if value is not None:
            self.values.append(value)
            self.retry.append(retry or value)

    def functions(self, name: str) -> dict[str, Callable]:
        """Return the given function of the struct for every endianness."""
        return _struct_functions(_optimize_struct_fmt(self.items), name)


def _check_union(cls: type[Union], fields: list[Field], inline: bool = True) -> int:
    """Check if the compiler supports the union. Returns its size."""
    size = cls.__size__
    if (
        not inline
        or cls.__align__
        or size is None
        or not _uses_generated_init(cls)
        or not _can_inline_fields(fields, size, is_union=True)
    ):
        raise TypeError(f"Unsupported union for compiler: {cls}")
    return size


def _inline_kind(type_: type[BaseType], in_union: bool = False) -> str | None:
    """Determine if a structure type can be inlined, returning ``S`` for structures and ``U`` for unions."""
    if not issubclass(type_, Structure):
        return None

    # Only static structures that we can construct directly, the same way their (compiled) _read would
    if type_.__size__ is None or type_.__align__ or not _uses_generated_init(type_):
        return None

    is_union = issubclass(type_, Union)
    if (is_union and in_union) or (not is_union and not type_.__compiled__):
        # Unions nested in unions aren't supported when proxying
        return None

    if not _can_inline_fields(type_.__fields__, type_.__size__, is_union, in_union):
        return None

    return "U" if is_union else "S"


def _can_inline_fields(fields: list[Field], size: int, is_union: bool, in_union: bool = False) -> bool:
    """Determine if the fields of a structure or union type of the given size can be inlined."""
    end = 0
    for field in fields:
        # Union members without an offset are read from the start of the union
        if field.bits or (field.offset is None and not is_union) or (not is_union and field.offset < end):
            return False

        field_type = field.type
        if isinstance(field_type, EnumMetaType):
            field_type = field_type.__type__

        if not issubclass(field_type, SUPPORTED_TYPES) or issubclass(field_type, (Pointer, Void, VoidArray)):
            return False

        if issubclass(field_type, Structure):
            if _inline_kind(field_type, in_union or is_union) is None:
                return False
        elif issubclass(field_type, (Array, CharArray, WcharArray)) and (
            field_type.__dynamic__ or issubclass(field_type.__type__, (Structure, BaseArray, Pointer, Void))
        ):
            return False

        # Union members can be placed beyond the end of the union, which reads past its bytes
        if (end := (field.offset or 0) + field_type.__size__) > size:
            return False

    return True


def _uses_generated_init(type_: type[Structure]) -> bool:
    """Return whether a structure type uses a generated ``__init__``, so we can bypass it by setting attributes."""
    return "__init__" in type_.__dict__ and type_.__new__ is object.__new__


def _can_pack(type_: type[BaseType]) -> bool:
    """Determine if a value of a type can be written by packing it, instead of by using the ``_write`` method."""
    if type_.__size__ is None:
        return False

    if issubclass(type_, (Enum, Flag)):
        return _can_pack(type_.__type__)

    if issubclass(type_, Structure):
        kind = _inline_kind(type_)
        if kind == "U":
            field = type_._write_field()
            return field is not None and bool(field.type.__size__) and _can_pack(field.type)
        return kind == "S" and all(_can_pack(field.type) for field in type_.__fields__)

    if issubclass(type_, Array) and (
        issubclass(type_.__type__, (Structure, BaseArray)) or not _can_pack(type_.__type__)
    ):
        return False

    return any(issubclass(type_, base) and _has_default_write(type_, base) for base in _PACKABLE_TYPES)


def _can_pack_bits(field: Field) -> bool:
    """Determine if the value of the bit buffer for a bit field can be written by packing it."""
    type_ = _get_bits_type(field)
    return issubclass(type_, (Int, Packed)) and _can_pack(type_)


def _has_default_write(type_: type[BaseType], base: type[BaseType]) -> bool:
    """Return whether a type uses the write methods of its base type, and doesn't have custom ones."""
    return all(getattr(type_, name).__func__ is getattr(base, name).__func__ for name in ("_write", "_write_array"))


def _int_to_bytes(type_: type[Int], value: str) -> str:
    """Return the code to convert a value of an integer type to bytes."""
    return f"{value}.to_bytes({type_.__size__}, _byteorder[endian], signed={bool(type_.signed)})"


def _get_attribute(var: str, name: str) -> str:
    """Return the code to get an attribute."""
    if name.isidentifier() and not iskeyword(name):
        return f"{var}.{name}"
    return f"_getattr({var}, {name!r})"


def _set_attribute(var: str, name: str, value: str) -> str:
    """Return the code to set an attribute."""
    if name.isidentifier() and not iskeyword(name):
        return f"{var}.{name} = {value}"
    return f"_setattr({var}, {name!r}, {value})"


def _attr_target(var: str) -> Callable[[Field, str], list[str]]:
    """Return a target that sets field values as attributes on the given object variable."""

    def target(field: Field, value: str) -> list[str]:
        return [_set_attribute(var, field._name, value)]

    return target


def _union_target(var: str) -> Callable[[Field, str], list[str]]:
    """Return a target that sets field values on the given union object variable."""

    def target(field: Field, value: str) -> list[str]:
        # This bypasses `__setattr__`
        return [f"_object_setattr({var}, {field._name!r}, {value})"]

    return target


def _member_lookup(type_: str, value: str) -> str:
    """Return the code to get the enum or flag member for a value into ``_member``."""
    return f"if (_member := {type_}._value2member_map_.get({value})) is None: _member = _type_call({type_}, {value})"


def _check_eof(size: int) -> str:
    """Return the code to raise an ``EOFError`` if fewer than ``size`` bytes were read into ``buf``."""
    return f'if len(buf) != {size}: raise EOFError(f"Read {{len(buf)}} bytes, but expected {size}")'


def _block(lines: list[str]) -> str:
    return "\n" + "\n".join(lines) + "\n"


def _generate_struct_info(
    fields: list[Field],
    inline: Callable[[type[BaseType]], str | None] | None = None,
) -> Iterator[tuple[Field, int, str]]:
    if not fields:
        return

    current_offset = fields[0].offset
    for field in fields:
        # We moved -- probably due to alignment
        if field.offset is not None and (drift := field.offset - current_offset) > 0:
            yield None, drift, "x"
            current_offset += drift

        count = 1
        read_type = _get_read_type(field.type)

        # Drop voids
        if issubclass(read_type, (Void, VoidArray)):
            continue

        # Structures that are inlined, yield as (S)tructure or (U)nion
        if inline is not None and (kind := inline(read_type)) is not None:
            yield field, 1, kind

        # Array of more complex types are handled elsewhere
        if issubclass(read_type, (Array, CharArray, WcharArray)):
            count = read_type.__num_entries__
            read_type = _get_read_type(read_type.__type__)

        # Take the pack char for Packed
        if issubclass(read_type, Packed):
            yield field, count, read_type.__fmt__

        # Other types are byte based
        # We don't actually unpack anything here but slice directly out of the buffer
        elif issubclass(read_type, (Char, Wchar, Int)):
            yield field, count * read_type.__size__, "x"

        if current_offset is not None:
            current_offset += count * read_type.__size__


def _optimize_struct_fmt(items: Iterable[tuple[int, str]]) -> str:
    """Create a struct format string from ``(count, char)`` items, merging consecutive items of the same char.

    Byte strings aren't merged, since those are a single value regardless of their count.
    """
    chars = []
    for char, group in groupby(items, key=itemgetter(1)):
        if char == "s":
            chars.extend(f"{count}{char}" for count, _ in group)
        elif count := sum(count for count, _ in group):
            chars.append(f"{count if count > 1 else ''}{char}")

    return "".join(chars)


def _struct_functions(fmt: str, name: str) -> dict[str, Callable]:
    """Return the given function of a struct with the given format for every endianness.

    The ``@`` endianness uses the ``=`` format, since ``@`` would add padding between items to align them.
    """
    return {endian: getattr(_struct("=" if endian == "@" else endian, fmt), name) for endian in _ENDIANNESS}


def _get_bit_buffer_type(field: Field) -> type[BaseType]:
    """Return the type that ``BitBuffer`` uses for a bit field, only bit fields of the same type share a value."""
    return field.type.__type__ if issubclass(field.type, (Enum, Flag)) else field.type


def _get_bits_type(field: Field) -> type[BaseType]:
    """Return the type that ``BitBuffer`` reads a bit field as."""
    type_ = _get_bit_buffer_type(field)
    return type_.__cs__.uint8 if issubclass(type_, Char) else type_


def _get_read_type(type_: type[BaseType]) -> type[BaseType]:
    """Return the type that a value of the given type is read as."""
    if issubclass(type_, (Enum, Flag)):
        type_ = type_.__type__

    if issubclass(type_, Pointer):
        type_ = type_.__cs__.pointer

    return type_
