from __future__ import annotations

import sys
from enum import EnumMeta, IntEnum, IntFlag
from typing import TYPE_CHECKING, Any, BinaryIO, Optional, Union

from dissect.cstruct.types.base import Array, BaseType, MetaType

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


class EnumMetaType(EnumMeta, MetaType):
    type: MetaType

    def __call__(
        cls,
        value: Union[cstruct, int, BinaryIO, bytes],
        name: Optional[str] = None,
        type_: Optional[MetaType] = None,
        *args,
        **kwargs,
    ):
        if name is None:
            if not isinstance(value, int):
                # value is a parsable value
                value = cls.type(value)

            return super().__call__(value)

        cs = value
        if not issubclass(type_, int):
            raise TypeError("Enum can only be created from int type")

        enum_cls = super().__call__(name, *args, **kwargs)
        enum_cls.cs = cs
        enum_cls.type = type_
        enum_cls.size = type_.size
        enum_cls.alignment = type_.alignment

        _fix_alias_members(enum_cls)

        return enum_cls

    def __getitem__(cls, name: Union[str, int]) -> Union[Enum, Array]:
        if isinstance(name, str):
            return super().__getitem__(name)
        return MetaType.__getitem__(cls, name)

    __len__ = MetaType.__len__

    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Enum:
        return cls(cls.type._read(stream, context))

    def _read_array(cls, stream: BinaryIO, count: int, context: dict[str, Any] = None) -> list[Enum]:
        return list(map(cls, cls.type._read_array(stream, count, context)))

    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] = None) -> list[Enum]:
        return list(map(cls, cls.type._read_0(stream, context)))

    def _write(cls, stream: BinaryIO, data: Enum) -> int:
        return cls.type._write(stream, data.value)

    def _write_array(cls, stream: BinaryIO, array: list[Enum]) -> int:
        data = [entry.value if isinstance(entry, Enum) else entry for entry in array]
        return cls.type._write_array(stream, data)

    def _write_0(cls, stream: BinaryIO, array: list[BaseType]) -> int:
        data = [entry.value if isinstance(entry, Enum) else entry for entry in array]
        return cls._write_array(stream, data + [cls.type()])


def _fix_alias_members(cls: type[Enum]):
    # Emulate aenum NoAlias behaviour
    # https://github.com/ethanfurman/aenum/blob/master/aenum/doc/aenum.rst
    if len(cls._member_names_) == len(cls._member_map_):
        return

    for name, member in cls._member_map_.items():
        if name != member.name:
            new_member = int.__new__(cls, member.value)
            new_member._name_ = name
            new_member._value_ = member.value

            type.__setattr__(cls, name, new_member)
            cls._member_names_.append(name)
            cls._member_map_[name] = new_member
            cls._value2member_map_[member.value] = new_member


class Enum(BaseType, IntEnum, metaclass=EnumMetaType):
    """Enum type supercharged with cstruct functionality.

    Enums are (mostly) compatible with the Python 3 standard library ``IntEnum`` with some notable differences:
        - Duplicate members are their own unique member instead of being an alias
        - Non-existing values are allowed and handled similarly to ``IntFlag``: ``<Enum: 0>``
        - Enum members are only considered equal if the enum class is the same

    Enums can be made using any integer type.

    Example:
        When using the default C-style parser, the following syntax is supported:

            enum <name> [: <type>] {
                <values>
            };

        For example, an enum that has A=1, B=5 and C=6 could be written like so:

            enum Test : uint16 {
                A, B=5, C
            };
    """

    if sys.version_info >= (3, 11):

        def __repr__(self) -> str:
            result = IntFlag.__repr__(self)
            if not self.__class__.__name__:
                result = f"<{result[2:]}"
            return result

        def __str__(self) -> str:
            result = IntFlag.__str__(self)
            if not self.__class__.__name__:
                result = f"<{result[1:]}"
            return result

    else:

        def __repr__(self) -> str:
            name = self.__class__.__name__
            if self._name_ is not None:
                if name:
                    name += "."
                name += self._name_
            return f"<{name}: {self._value_!r}>"

        def __str__(self) -> str:
            name = self.__class__.__name__
            if name:
                name += "."

            if self._name_ is not None:
                name += f"{self._name_}"
            else:
                name += repr(self._value_)
            return name

    def __eq__(self, other: Union[int, Enum]) -> bool:
        if isinstance(other, Enum) and other.__class__ is not self.__class__:
            return False

        # Python <= 3.10 compatibility
        if isinstance(other, Enum):
            other = other.value

        return self.value == other

    def __ne__(self, value: Union[int, Enum]) -> bool:
        return not self.__eq__(value)

    def __hash__(self) -> int:
        return hash((self.__class__, self.name, self.value))

    @classmethod
    def _missing_(cls, value: int) -> Enum:
        # Emulate FlagBoundary.KEEP for enum (allow values other than the defined members)
        pseudo_member = cls._value2member_map_.get(value, None)
        if pseudo_member is None:
            new_member = int.__new__(cls, value)
            new_member._name_ = None
            new_member._value_ = value
            pseudo_member = cls._value2member_map_.setdefault(value, new_member)
        return pseudo_member
