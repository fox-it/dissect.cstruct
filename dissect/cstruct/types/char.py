from __future__ import annotations

from typing import Any, BinaryIO, Union

from dissect.cstruct.types.base import EOF, ArrayMetaType, BaseType


class Char(bytes, BaseType):
    """Character type for reading and writing bytes."""

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Char:
        return cls._read_array(stream, 1, context)

    @classmethod
    def _read_array(cls, stream: BinaryIO, count: int, context: dict[str, Any] = None) -> Char:
        if count == 0:
            return type.__call__(cls, b"")

        data = stream.read(-1 if count == EOF else count)
        if count != EOF and len(data) != count:
            raise EOFError(f"Read {len(data)} bytes, but expected {count}")

        return type.__call__(cls, data)

    @classmethod
    def _read_0(cls, stream: BinaryIO, context: dict[str, Any] = None) -> Char:
        buf = []
        while True:
            byte = stream.read(1)
            if byte == b"":
                raise EOFError("Read 0 bytes, but expected 1")

            if byte == b"\x00":
                break

            buf.append(byte)

        return type.__call__(cls, b"".join(buf))

    @classmethod
    def _write(cls, stream: BinaryIO, data: Union[bytes, int, str]) -> int:
        if isinstance(data, int):
            data = chr(data)

        if isinstance(data, str):
            data = data.encode("latin-1")

        return stream.write(data)

    @classmethod
    def default(cls) -> Char:
        return type.__call__(cls, b"\x00")


class CharArray(bytes, BaseType, metaclass=ArrayMetaType):
    """Character array type for reading and writing byte strings."""

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] = None) -> CharArray:
        return type.__call__(cls, ArrayMetaType._read(cls, stream, context))

    @classmethod
    def _write(cls, stream: BinaryIO, data: bytes) -> int:
        if isinstance(data, list) and data and isinstance(data[0], int):
            data = bytes(data)

        if isinstance(data, str):
            data = data.encode("latin-1")

        if cls.null_terminated:
            return stream.write(data + b"\x00")
        return stream.write(data)

    @classmethod
    def default(cls) -> CharArray:
        return type.__call__(cls, b"\x00" * (0 if cls.dynamic or cls.null_terminated else cls.num_entries))
