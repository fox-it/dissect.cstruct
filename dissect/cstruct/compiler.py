# Made in Japan

from __future__ import annotations

import io
import logging
from enum import Enum
from itertools import groupby, repeat
from keyword import iskeyword
from operator import itemgetter
from textwrap import indent
from typing import TYPE_CHECKING, Any

from dissect.cstruct.exception import ExpressionParserError
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
from dissect.cstruct.types.structure import UnionMetaType, UnionProxy
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
    """Compile the ``_read`` method of a structure or union type, if the compiler supports it.

    The compilation happens on first use.
    """
    try:
        _check_supported(cls, cls.__fields__)
        cls._read = _LazyCompileRead(cls)
        cls.__compiled__ = True
    except Exception as e:
        # Revert to the interpreted reader
        log.debug("Failed to compile %s", cls, exc_info=e)
        cls._read = classmethod(type(cls)._read)
        cls.__compiled__ = False

    return cls


class _LazyCompileRead:
    """Descriptor that compiles the ``_read`` method of a structure on first access and replaces itself with it."""

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
                self.method = _ReadSourceGenerator(cls, self.fields, inline).generate()
            except Exception as e:
                # Revert to the slower loop based method
                log.debug("Failed to compile %s", cls, exc_info=e)
                self.method = classmethod(type(cls)._read)
                cls.__compiled__ = False

            if cls.__dict__.get("_read") is self:
                cls._read = self.method

        return self.method


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

# Globals that are available to all generated read functions
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
    **SOURCE_GLOBALS,
}


class _ReadSourceGenerator:
    """Generates the source code of an optimized ``_read`` method for a structure or union."""

    def __init__(self, cls: type[Structure], fields: list[Field], inline: bool = True):
        self.cls = cls
        self.fields = fields
        self.align = cls.__align__
        self.inline = inline and not self.align

        # Witnesses of inlined structure types (symbol of the type -> symbol of its __init__ at compile time)
        self._witnesses: dict[str, str] = {}
        self._fallback_symbol: str | None = None

        # The state of the bit buffer: the type of its current value and the remaining bits
        self._bits: tuple[type[BaseType], int] | None = None
        self._var_ids: dict[str, int] = {}

        # The values available to the generated code
        self.symbols: dict[str, Any] = {"cs": cls.__cs__}
        self._symbol_names: dict[int, str] = {}

        # (field name, local variable name) of all fields assigned so far
        self._assigned: list[tuple[str, str]] = []
        self._has_context = False
        self._uses_start = False
        self._uses_sizes = False

    def _type_symbol(self, type_: type[BaseType]) -> str:
        """Add a type as symbol, returns its name."""
        return self._add_symbol(type_, "type")

    def _add_symbol(self, value: Any, name: str) -> str:
        """Add a value that is available to the generated code, returns its name."""
        if (symbol := self._symbol_names.get(id(value))) is None:
            symbol = self._symbol_names[id(value)] = self._var(name)
            self.symbols[symbol] = value
        return symbol

    def _context(self, lines: list[str]) -> str:
        """Return the name of the context dictionary, creating it from the fields read so far if needed."""
        if not self._has_context:
            self._has_context = True
            items = ", ".join(f"{name!r}: {var}" for name, var in self._assigned)
            lines.append(f"values = {{{items}}}")

        return "values"

    def _var(self, name: str) -> str:
        """Return a unique variable name for the generated code."""
        index = self._var_ids.get(name, 0)
        self._var_ids[name] = index + 1
        return f"_{name}{index}"

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

    def _witness(self, type_: type[Structure]) -> str:
        """Add an inlined type as symbol, with a witness to detect modifications to it after compilation."""
        symbol = self._type_symbol(type_)
        self._witnesses[symbol] = self._add_symbol(type_.__init__, "init")
        return symbol

    def _modified_checks(self) -> list[str]:
        """Return the conditions that are true if any of the inlined types were modified after compilation."""
        return [f"{type_}.__init__ is not {init}" for type_, init in self._witnesses.items()]

    def generate(self) -> MethodType:
        source = self.generate_source()

        code = python_compile(source, f"<compiled {self.cls.__name__}._read>", "exec")
        exec(code, {**_GLOBALS, **self.symbols}, d := {})
        obj = d.popitem()[1]
        obj.__source__ = source

        return classmethod(obj)

    def generate_source(self) -> str:
        if issubclass(self.cls, Union):
            return self._generate_union_source()
        return self._generate_struct_source()

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

    def _starts_bit_value(self, field: Field) -> bool:
        """Return whether a bit field is read from a new value of the bit buffer."""
        return self._bits is None or self._bits[1] == 0 or self._bits[0] is not _get_bits_type(field)

    def _generate_bits_source(self, field: Field) -> Iterator[str]:
        """Generate the code for reading a bit field."""
        read_type = _get_bits_type(field)
        new_value = self._starts_bit_value(field)
        if new_value:
            self._bits = (read_type, read_type.__size__ * 8)
        remaining = self._bits[1]
        self._bits = (read_type, remaining - field.bits)

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
        size = self._pack_fields(fields, 0, unpack, reads, self._assign_local, self.align)

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
        align: bool = False,
    ) -> int:
        """Generate the code for reading the given fields from ``buf``, starting at the given offset.

        Unpackable values are added to the given ``unpack`` format, and accessed through its variable.
        Every field value is passed to ``target``, which returns the lines that store the value.

        Returns the offset after the last field.
        """
        inline = _inline_kind if self.inline else None
        for field, count, char in _generate_struct_info(fields, align, inline=inline):
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

    def _proxify(self, union: str, var: str, fields: list[Field], lines: list[str]) -> None:
        """Generate the code equivalent to ``Union._proxify``."""
        for field in fields:
            if issubclass(field.type, Structure):
                nested = self._var("nested")
                lines.append(f"{nested} = _getattr({var}, {field._name!r})")
                lines.append(
                    f"_object_setattr({var}, {field._name!r}, _UnionProxy({union}, {field._name!r}, {nested}))"
                )
                self._proxify(union, nested, field.type.__fields__, lines)

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

            if issubclass(field_type.__type__, Int):
                elem_size = field_type.__type__.__size__
                signed = bool(field_type.__type__.signed)
                lines.append(f"_array_buf = {getter}")
                raw = f"_int_from_bytes(_array_buf[i:i + {elem_size}], _byteorder[endian], signed={signed})"
                value = f"[_type_call({element}, {raw}) for i in range(0, {count}, {elem_size})]"
            elif issubclass(field_type.__type__, Pointer):
                context = self._context(lines)
                item = f"{element}.__new__({element}, value, stream, context={context}, endian=endian)"
                value = f"[{item} for value in {getter}]"
            elif issubclass(read_type, (Wchar, Int)):
                # Preserve the behaviour of the generic parsing path for these types
                value = f"[{element}(value) for value in {getter}]"
            else:
                value = f"list(map(_type_call, _repeat({element}), {getter}))"

            lines.extend(target(field, f"_type_call({array}, {value})"))

        elif issubclass(field_type, CharArray):
            lines.extend(target(field, f"_type_call({self._type_symbol(field.type)}, {getter})"))

        elif issubclass(field_type, WcharArray) or issubclass(read_type, Wchar):
            encoding = self._add_symbol(read_type.__encoding_map__, "encoding")
            # Using str() instead of .decode() also supports other bytes-like objects returned by the stream
            type_ = self._type_symbol(field.type)
            lines.extend(target(field, f"_type_call({type_}, str({getter}, {encoding}[endian]))"))

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
        fmt = _optimize_struct_fmt(self.items)
        return {endian: getattr(_struct(endian, fmt), name) for endian in _ENDIANNESS}


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
    align: bool = False,
    inline: Callable[[type[BaseType]], str | None] | None = None,
) -> Iterator[tuple[Field, int, str]]:
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

        size = count * read_type.__size__
        imaginary_offset += size
        if current_offset is not None:
            current_offset += size


def _optimize_struct_fmt(items: Iterable[tuple[int, str]]) -> str:
    """Create a struct format string from ``(count, char)`` items, merging consecutive items of the same char."""
    chars = []
    for char, group in groupby(items, key=itemgetter(1)):
        if count := sum(count for count, _ in group):
            chars.append(f"{count if count > 1 else ''}{char}")

    return "".join(chars)


def _get_bits_type(field: Field) -> type[BaseType]:
    """Return the type that ``BitBuffer`` reads a bit field as."""
    type_ = field.type.__type__ if issubclass(field.type, (Enum, Flag)) else field.type
    return type_.__cs__.uint8 if issubclass(type_, Char) else type_


def _get_read_type(type_: type[BaseType]) -> type[BaseType]:
    """Return the type that a value of the given type is read as."""
    if issubclass(type_, (Enum, Flag)):
        type_ = type_.__type__

    if issubclass(type_, Pointer):
        type_ = type_.__cs__.pointer

    return type_
