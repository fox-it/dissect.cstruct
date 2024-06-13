from __future__ import annotations

import io
from contextlib import contextmanager
from functools import lru_cache
from operator import attrgetter
from textwrap import dedent
from types import FunctionType
from typing import Any, BinaryIO, Callable, ContextManager

from dissect.cstruct.bitbuffer import BitBuffer
from dissect.cstruct.types.base import BaseType, MetaType
from dissect.cstruct.types.enum import EnumMetaType
from dissect.cstruct.types.pointer import Pointer


class Field:
    """Structure field."""

    def __init__(self, name: str, type_: MetaType, bits: int = None, offset: int = None):
        self.name = name
        self.type = type_
        self.bits = bits
        self.offset = offset
        self.alignment = type_.alignment or 1

    def __repr__(self) -> str:
        bits_str = f" : {self.bits}" if self.bits else ""
        return f"<Field {self.name} {self.type.__name__}{bits_str}>"


class StructureMetaType(MetaType):
    """Base metaclass for cstruct structure type classes."""

    # TODO: resolve field types in _update_fields, remove resolves elsewhere?

    fields: dict[str, Field]
    """Mapping of field names to :class:`Field` objects, including "folded" fields from anonymous structures."""
    lookup: dict[str, Field]
    """Mapping of "raw" field names to :class:`Field` objects. E.g. holds the anonymous struct and not its fields."""
    __fields__: list[Field]
    """List of :class:`Field` objects for this structure. This is the structures' Single Source Of Truth."""

    # Internal
    __align__: bool
    __anonymous__: bool
    __updating__ = False
    __compiled__ = False

    def __new__(metacls, name: str, bases: tuple[type, ...], classdict: dict[str, Any]) -> MetaType:
        if (fields := classdict.pop("fields", None)) is not None:
            metacls._update_fields(metacls, fields, align=classdict.get("__align__", False), classdict=classdict)

        return super().__new__(metacls, name, bases, classdict)

    def __call__(cls, *args, **kwargs) -> Structure:
        if (
            cls.__fields__
            and len(args) == len(cls.__fields__) == 1
            and isinstance(args[0], bytes)
            and issubclass(cls.__fields__[0].type, bytes)
            and len(args[0]) == cls.__fields__[0].type.size
        ):
            # Shortcut for single char/bytes type
            return type.__call__(cls, *args, **kwargs)
        elif not args and not kwargs:
            obj = cls(**{field.name: field.type.default() for field in cls.__fields__})
            object.__setattr__(obj, "_values", {})
            object.__setattr__(obj, "_sizes", {})
            return obj

        return super().__call__(*args, **kwargs)

    def _update_fields(cls, fields: list[Field], align: bool = False, classdict: dict[str, Any] | None = None) -> None:
        classdict = classdict or {}

        lookup = {}
        raw_lookup = {}
        init_names = []
        field_names = []
        for field in fields:
            if field.name in lookup and field.name != "_":
                raise ValueError(f"Duplicate field name: {field.name}")

            if isinstance(field.type, StructureMetaType) and field.type.__anonymous__:
                for anon_field in field.type.fields.values():
                    attr = f"{field.name}.{anon_field.name}"
                    classdict[anon_field.name] = property(attrgetter(attr), attrsetter(attr))

                lookup.update(field.type.fields)
            else:
                lookup[field.name] = field

            raw_lookup[field.name] = field

        num_fields = len(lookup)
        field_names = lookup.keys()
        init_names = raw_lookup.keys()
        classdict["fields"] = lookup
        classdict["lookup"] = raw_lookup
        classdict["__fields__"] = fields
        classdict["__bool__"] = _patch_attributes(_make__bool__(num_fields), field_names, 1)

        if issubclass(cls, UnionMetaType) or isinstance(cls, UnionMetaType):
            classdict["__init__"] = _patch_setattr_args_and_attributes(
                _make_setattr__init__(len(init_names)), init_names
            )
            # Not a great way to do this but it works for now
            classdict["__eq__"] = Union.__eq__
        else:
            classdict["__init__"] = _patch_args_and_attributes(_make__init__(len(init_names)), init_names)
            classdict["__eq__"] = _patch_attributes(_make__eq__(num_fields), field_names, 1)

        classdict["__hash__"] = _patch_attributes(_make__hash__(num_fields), field_names, 1)

        # If we're calling this as a class method or a function on the metaclass
        if issubclass(cls, type):
            size, alignment = cls._calculate_size_and_offsets(cls, fields, align)
        else:
            size, alignment = cls._calculate_size_and_offsets(fields, align)

        if cls.__compiled__:
            # If the previous class was compiled try to compile this too
            from dissect.cstruct import compiler

            try:
                classdict["_read"] = compiler.Compiler(cls.cs).compile_read(fields, cls.__name__, align=cls.__align__)
                classdict["__compiled__"] = True
            except Exception:
                # Revert _read to the slower loop based method
                classdict["_read"] = classmethod(StructureMetaType._read)
                classdict["__compiled__"] = False

        # TODO: compile _write
        # TODO: generate cached_property for lazy reading

        classdict["size"] = size
        classdict["alignment"] = alignment
        classdict["dynamic"] = size is None

        return classdict

    def _calculate_size_and_offsets(cls, fields: list[Field], align: bool = False) -> tuple[int | None, int]:
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

        for field in fields:
            if field.offset is not None:
                # If a field already has an offset, it's leading
                offset = field.offset

            if align and offset is not None:
                # Round to next alignment
                offset += -offset & (field.alignment - 1)

            # The alignment of this struct is equal to its largest members' alignment
            alignment = max(alignment, field.alignment)

            if field.bits:
                field_type = field.type

                if isinstance(field_type, EnumMetaType):
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
                        continue

                    offset += field_len

        if align and offset is not None:
            # Add "tail padding" if we need to align
            # This bit magic rounds up to the next alignment boundary
            # E.g. offset = 3; alignment = 8; -offset & (alignment - 1) = 5
            offset += -offset & (alignment - 1)

        # The structure size is whatever the currently calculated offset is
        return offset, alignment

    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Structure:
        bit_buffer = BitBuffer(stream, cls.cs.endian)
        struct_start = stream.tell()

        result = {}
        sizes = {}
        for field in cls.__fields__:
            offset = stream.tell()
            field_type = cls.cs.resolve(field.type)

            if field.offset is not None and offset != struct_start + field.offset:
                # Field is at a specific offset, either alligned or added that way
                offset = struct_start + field.offset
                stream.seek(offset)

            if cls.__align__ and field.offset is None:
                # Previous field was dynamically sized and we need to align
                offset += -offset & (field.alignment - 1)
                stream.seek(offset)

            if field.bits:
                if isinstance(field_type, EnumMetaType):
                    value = field_type(bit_buffer.read(field_type.type, field.bits))
                else:
                    value = bit_buffer.read(field_type, field.bits)

                if field.name:
                    result[field.name] = value
                continue
            else:
                bit_buffer.reset()

            value = field_type._read(stream, result)

            if field.name:
                sizes[field.name] = stream.tell() - offset
                result[field.name] = value

        if cls.__align__:
            # Align the stream
            stream.seek(-stream.tell() & (cls.alignment - 1), io.SEEK_CUR)

        obj = cls(**result)
        obj._sizes = sizes
        obj._values = result
        return obj

    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] = None) -> list[Structure]:
        result = []

        while obj := cls._read(stream, context):
            result.append(obj)

        return result

    def _write(cls, stream: BinaryIO, data: Structure) -> int:
        bit_buffer = BitBuffer(stream, cls.cs.endian)
        struct_start = stream.tell()
        num = 0

        for field in cls.__fields__:
            field_type = cls.cs.resolve(field.type)

            bit_field_type = (
                (field_type.type if isinstance(field_type, EnumMetaType) else field_type) if field.bits else None
            )
            # Current field is not a bit field, but previous was
            # Or, moved to a bit field of another type, e.g. uint16 f1 : 8, uint32 f2 : 8;
            if (not field.bits and bit_buffer._type is not None) or (
                bit_buffer._type and bit_buffer._type != bit_field_type
            ):
                # Flush the current bit buffer so we can process alignment properly
                bit_buffer.flush()

            offset = stream.tell()

            if field.offset is not None and offset < struct_start + field.offset:
                # Field is at a specific offset, either alligned or added that way
                stream.write(b"\x00" * (struct_start + field.offset - offset))
                offset = struct_start + field.offset

            if cls.__align__ and field.offset is None:
                is_bitbuffer_boundary = bit_buffer._type and (
                    bit_buffer._remaining == 0 or bit_buffer._type != field_type
                )
                if not bit_buffer._type or is_bitbuffer_boundary:
                    # Previous field was dynamically sized and we need to align
                    align_pad = -offset & (field.alignment - 1)
                    stream.write(b"\x00" * align_pad)
                    offset += align_pad

            value = getattr(data, field.name, None)
            if value is None:
                value = field_type()

            if field.bits:
                if isinstance(field_type, EnumMetaType):
                    bit_buffer.write(field_type.type, value.value, field.bits)
                else:
                    bit_buffer.write(field_type, value, field.bits)
            else:
                field_type._write(stream, value)
                num += stream.tell() - offset

        if bit_buffer._type is not None:
            bit_buffer.flush()

        if cls.__align__:
            # Align the stream
            stream.write(b"\x00" * (-stream.tell() & (cls.alignment - 1)))

        return num

    def add_field(cls, name: str, type_: BaseType, bits: int | None = None, offset: int | None = None) -> None:
        field = Field(name, type_, bits=bits, offset=offset)
        cls.__fields__.append(field)

        if not cls.__updating__:
            cls.commit()

    @contextmanager
    def start_update(cls) -> ContextManager:
        try:
            cls.__updating__ = True
            yield
        finally:
            cls.commit()
            cls.__updating__ = False

    def commit(cls) -> None:
        classdict = cls._update_fields(cls.__fields__, cls.__align__)

        for key, value in classdict.items():
            setattr(cls, key, value)


class Structure(BaseType, metaclass=StructureMetaType):
    """Base class for cstruct structure type classes."""

    _values: dict[str, Any]
    _sizes: dict[str, int]

    def __len__(self) -> int:
        return len(self.dumps())

    def __bytes__(self) -> bytes:
        return self.dumps()

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __repr__(self) -> str:
        values = [
            f"{k}={hex(self[k]) if (issubclass(f.type, int) and not issubclass(f.type, Pointer)) else repr(self[k])}"
            for k, f in self.__class__.fields.items()
        ]
        return f"<{self.__class__.__name__} {' '.join(values)}>"


class UnionMetaType(StructureMetaType):
    """Base metaclass for cstruct union type classes."""

    def __call__(cls, *args, **kwargs) -> Union:
        obj = super().__call__(*args, **kwargs)
        if kwargs:
            # Calling with kwargs means we are initializing with values
            # Proxify all values
            obj._proxify()
        return obj

    def _calculate_size_and_offsets(cls, fields: list[Field], align: bool = False) -> tuple[int | None, int]:
        size = 0
        alignment = 0

        for field in fields:
            if size is not None:
                try:
                    size = max(len(field.type), size)
                except TypeError:
                    size = None

            alignment = max(field.alignment, alignment)

        if align and size is not None:
            # Add "tail padding" if we need to align
            # This bit magic rounds up to the next alignment boundary
            # E.g. offset = 3; alignment = 8; -offset & (alignment - 1) = 5
            size += -size & (alignment - 1)

        return size, alignment

    def _read_fields(cls, stream: BinaryIO, context: dict[str, Any] = None) -> tuple[dict[str, Any], dict[str, int]]:
        result = {}
        sizes = {}

        if cls.size is None:
            offset = stream.tell()
            buf = stream
        else:
            offset = 0
            buf = io.BytesIO(stream.read(cls.size))

        for field in cls.__fields__:
            field_type = cls.cs.resolve(field.type)

            start = 0
            if field.offset is not None:
                start = field.offset

            buf.seek(offset + start)
            value = field_type._read(buf, result)

            sizes[field.name] = buf.tell() - start
            result[field.name] = value

        return result, sizes

    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Union:
        if cls.size is None:
            start = stream.tell()
            result, sizes = cls._read_fields(stream, context)
            size = stream.tell() - start
            stream.seek(start)
            buf = stream.read(size)
        else:
            result = {}
            sizes = {}
            buf = stream.read(cls.size)

        obj: Union = cls(**result)
        object.__setattr__(obj, "_values", result)
        object.__setattr__(obj, "_sizes", sizes)
        object.__setattr__(obj, "_buf", buf)

        if cls.size is not None:
            obj._update()

        return obj

    def _write(cls, stream: BinaryIO, data: Union) -> int:
        offset = stream.tell()
        expected_offset = offset + len(cls)

        # Sort by largest field
        fields = sorted(cls.__fields__, key=lambda e: len(e.type), reverse=True)
        anonymous_struct = False

        # Try to write by largest field
        for field in fields:
            if isinstance(field.type, StructureMetaType) and field.type.__anonymous__:
                # Prefer to write regular fields initially
                anonymous_struct = field.type
                continue

            # Skip empty values
            if (value := getattr(data, field.name)) is None:
                continue

            # We have a value, write it
            field.type._write(stream, value)
            break

        # If we haven't written anything yet and we initially skipped an anonymous struct, write it now
        if stream.tell() == offset and anonymous_struct:
            anonymous_struct._write(stream, data)

        # If we haven't filled the union size yet, pad it
        if remaining := expected_offset - stream.tell():
            stream.write(b"\x00" * remaining)

        return stream.tell() - offset


class Union(Structure, metaclass=UnionMetaType):
    """Base class for cstruct union type classes."""

    _buf: bytes

    def __eq__(self, other: Any) -> bool:
        return self.__class__ is other.__class__ and bytes(self) == bytes(other)

    def __setattr__(self, attr: str, value: Any) -> None:
        if self.__class__.dynamic:
            raise NotImplementedError("Modifying a dynamic union is not yet supported")

        super().__setattr__(attr, value)
        self._rebuild(attr)

    def _rebuild(self, attr: str) -> None:
        if (cur_buf := getattr(self, "_buf", None)) is None:
            cur_buf = b"\x00" * self.__class__.size

        buf = io.BytesIO(cur_buf)
        field = self.__class__.fields[attr]
        if field.offset:
            buf.seek(field.offset)
        field.type._write(buf, getattr(self, attr))

        object.__setattr__(self, "_buf", buf.getvalue())
        self._update()

    def _update(self) -> None:
        result, sizes = self.__class__._read_fields(io.BytesIO(self._buf))
        self.__dict__.update(result)
        object.__setattr__(self, "_values", result)
        object.__setattr__(self, "_sizes", sizes)

    def _proxify(self) -> None:
        def _proxy_structure(value: Structure) -> None:
            for field in value.__class__.__fields__:
                if issubclass(field.type, Structure):
                    nested_value = getattr(value, field.name)
                    proxy = UnionProxy(self, field.name, nested_value)
                    object.__setattr__(value, field.name, proxy)
                    _proxy_structure(nested_value)

        _proxy_structure(self)


class UnionProxy:
    __union__: Union
    __attr__: str
    __target__: Structure

    def __init__(self, union: Union, attr: str, target: Structure):
        object.__setattr__(self, "__union__", union)
        object.__setattr__(self, "__attr__", attr)
        object.__setattr__(self, "__target__", target)

    def __len__(self) -> int:
        return len(self.__target__.dumps())

    def __bytes__(self) -> bytes:
        return self.__target__.dumps()

    def __getitem__(self, item: str) -> Any:
        return getattr(self.__target__, item)

    def __repr__(self) -> str:
        return repr(self.__target__)

    def __getattr__(self, attr: str) -> Any:
        return getattr(self.__target__, attr)

    def __setattr__(self, attr: str, value: Any) -> None:
        setattr(self.__target__, attr, value)
        self.__union__._rebuild(self.__attr__)


def attrsetter(path: str) -> Callable[[Any], Any]:
    path, _, attr = path.rpartition(".")
    path = path.split(".")

    def _func(obj: Any, value: Any) -> Any:
        for name in path:
            obj = getattr(obj, name)
        setattr(obj, attr, value)

    return _func


def _codegen(func: FunctionType) -> FunctionType:
    # Inspired by https://github.com/dabeaz/dataklasses
    @lru_cache
    def make_func_code(num_fields: int) -> FunctionType:
        names = [f"_{n}" for n in range(num_fields)]
        exec(func(names), {}, d := {})
        return d.popitem()[1]

    return make_func_code


def _patch_args_and_attributes(func: FunctionType, fields: list[str], start: int = 0) -> FunctionType:
    return type(func)(
        func.__code__.replace(
            co_names=(*func.__code__.co_names[:start], *fields),
            co_varnames=("self", *fields),
        ),
        func.__globals__,
        argdefs=func.__defaults__,
    )


def _patch_setattr_args_and_attributes(func: FunctionType, fields: list[str], start: int = 0) -> FunctionType:
    return type(func)(
        func.__code__.replace(
            co_consts=(None, *fields),
            co_varnames=("self", *fields),
        ),
        func.__globals__,
        argdefs=func.__defaults__,
    )


def _patch_attributes(func: FunctionType, fields: list[str], start: int = 0) -> FunctionType:
    return type(func)(
        func.__code__.replace(co_names=(*func.__code__.co_names[:start], *fields)),
        func.__globals__,
    )


@_codegen
def _make__init__(fields: list[str]) -> str:
    field_args = ", ".join(f"{field} = None" for field in fields)
    field_init = "\n".join(f" self.{name} = {name}" for name in fields)

    code = f"def __init__(self{', ' + field_args if field_args else ''}):\n"
    return code + (field_init or " pass")


@_codegen
def _make_setattr__init__(fields: list[str]) -> str:
    field_args = ", ".join(f"{field} = None" for field in fields)
    field_init = "\n".join(f" object.__setattr__(self, {name!r}, {name})" for name in fields)

    code = f"def __init__(self{', ' + field_args if field_args else ''}):\n"
    return code + (field_init or " pass")


@_codegen
def _make__eq__(fields: list[str]) -> str:
    self_vals = ",".join(f"self.{name}" for name in fields)
    other_vals = ",".join(f"other.{name}" for name in fields)

    if self_vals:
        self_vals += ","
    if other_vals:
        other_vals += ","

    # In the future this could be a looser check, e.g. an __eq__ on the classes, which compares the fields
    code = f"""
    def __eq__(self, other):
        if self.__class__ is other.__class__:
            return ({self_vals}) == ({other_vals})
        return False
    """

    return dedent(code)


@_codegen
def _make__bool__(fields: list[str]) -> str:
    vals = ", ".join(f"self.{name}" for name in fields)

    code = f"""
    def __bool__(self):
        return any([{vals}])
    """

    return dedent(code)


@_codegen
def _make__hash__(fields: list[str]) -> str:
    vals = ", ".join(f"self.{name}" for name in fields)

    code = f"""
    def __hash__(self):
        return hash(({vals}))
    """

    return dedent(code)
