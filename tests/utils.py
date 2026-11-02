from __future__ import annotations

import io
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from dissect.cstruct.types.structure import UnionProxy

if TYPE_CHECKING:
    from dissect.cstruct import Structure


def verify_compiled(struct: type[Structure], compiled: bool) -> bool:
    return struct.__compiled__ == compiled


def absolute_path(path: str | Path) -> Path:
    return Path(__file__).parent.joinpath(path)


class NonSeekableStream:
    """A stream that only supports reading."""

    def __init__(self, data: bytes):
        self._fh = io.BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        return self._fh.read(size)

    def seekable(self) -> bool:
        return False


def source_lines(type_: type) -> list[str]:
    """Return the lines of the compiled ``_read`` method of a type, without indentation."""
    return [line.strip() for line in type_._read.__source__.splitlines()]


def parsed_state(obj: object) -> object:
    """Return a comparable representation of a parsed value, including the types of all nested values."""
    if isinstance(obj, UnionProxy):
        return ("proxy", obj.__attr__, parsed_state(obj.__target__))
    if hasattr(obj, "__dict__") and hasattr(obj.__class__, "__fields__"):
        items = [(k, parsed_state(v)) for k, v in obj.__dict__.items()]
        return (type(obj).__name__, items)
    if isinstance(obj, list):
        return (type(obj).__name__, [parsed_state(v) for v in obj])
    if isinstance(obj, Enum):
        # Members of different cstruct instances never compare equal
        return (type(obj).__name__, obj.name, obj.value)
    return (type(obj).__name__, obj)
