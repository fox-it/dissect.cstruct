from __future__ import annotations

from typing import Any, BinaryIO, Dict, List, Union, TYPE_CHECKING

from dissect.cstruct.types import BaseType, RawType

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class Enum(RawType):
    """Implements an Enum type.

    Enums can be made using any type. The API for accessing enums and their
    values is very similar to Python 3 native enums.

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

    def __init__(self, cstruct: cstruct, name: str, type_: BaseType, values: Dict[str, int]):
        self.type = type_
        self.values = values
        self.reverse = {}

        for k, v in values.items():
            self.reverse[v] = k

        super().__init__(cstruct, name, len(self.type), self.type.alignment)

    def __call__(self, value: Union[int, BinaryIO]) -> EnumInstance:
        if isinstance(value, int):
            return EnumInstance(self, value)
        return super().__call__(value)

    def __getitem__(self, attr: str) -> EnumInstance:
        return self(self.values[attr])

    def __getattr__(self, attr: str) -> EnumInstance:
        try:
            return self(self.values[attr])
        except KeyError:
            raise AttributeError(attr)

    def __contains__(self, attr: str) -> bool:
        return attr in self.values

    def _read(self, stream: BinaryIO, context: dict[str, Any] = None) -> EnumInstance:
        v = self.type._read(stream, context)
        return self(v)

    def _read_array(self, stream: BinaryIO, count: int, context: dict[str, Any] = None) -> List[EnumInstance]:
        return list(map(self, self.type._read_array(stream, count, context)))

    def _read_0(self, stream: BinaryIO, context: dict[str, Any] = None) -> List[EnumInstance]:
        return list(map(self, self.type._read_0(stream, context)))

    def _write(self, stream: BinaryIO, data: Union[int, EnumInstance]) -> int:
        data = data.value if isinstance(data, EnumInstance) else data
        return self.type._write(stream, data)

    def _write_array(self, stream: BinaryIO, data: List[Union[int, EnumInstance]]) -> int:
        data = [d.value if isinstance(d, EnumInstance) else d for d in data]
        return self.type._write_array(stream, data)

    def _write_0(self, stream: BinaryIO, data: List[Union[int, EnumInstance]]) -> int:
        data = [d.value if isinstance(d, EnumInstance) else d for d in data]
        return self.type._write_0(stream, data)

    def default(self) -> EnumInstance:
        return self(0)

    def default_array(self, count: int) -> List[EnumInstance]:
        return [self.default() for _ in range(count)]


class EnumInstance:
    """Implements a value instance of an Enum"""

    def __init__(self, enum: Enum, value: int):
        self.enum = enum
        self.value = value

    def __eq__(self, value: Union[int, EnumInstance]) -> bool:
        if isinstance(value, EnumInstance) and value.enum is not self.enum:
            return False

        if hasattr(value, "value"):
            value = value.value

        return self.value == value

    def __ne__(self, value: Union[int, EnumInstance]) -> bool:
        return self.__eq__(value) is False

    def __hash__(self) -> int:
        return hash((self.enum, self.value))

    def __str__(self) -> str:
        return f"{self.enum.name}.{self.name}"

    def __repr__(self) -> str:
        return f"<{self.enum.name}.{self.name}: {self.value}>"

    @property
    def name(self) -> str:
        if self.value not in self.enum.reverse:
            return f"{self.enum.name}_{self.value}"

        return self.enum.reverse[self.value]
