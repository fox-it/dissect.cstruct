from __future__ import annotations

from typing import Any, BinaryIO

from dissect.cstruct import cstruct
from dissect.cstruct.types import BaseType


class ProtobufVarint(BaseType):
    """Implements a protobuf integer type for dissect.cstruct that can span a variable amount of bytes.

    Mainly follows the BaseType implementation with minor tweaks
    to support protobuf's msb varint implementation.

    Resources:
        - https://protobuf.dev/programming-guides/encoding/
        - https://github.com/protocolbuffers/protobuf/blob/main/python/google/protobuf/internal/decoder.py
    """

    @classmethod
    def _read(cls, stream: BinaryIO, context: dict[str, Any] | None = None) -> int:
        return decode_varint(stream)

    @classmethod
    def _write(cls, stream: BinaryIO, data: int) -> int:
        return stream.write(encode_varint(data))


def decode_varint(stream: BinaryIO) -> int:
    """Reads a varint from the provided buffer stream.

    If we have not reached the end of a varint, the msb will be 1.
    We read every byte from our current position until the msb is 0.
    """
    result = 0
    i = 0
    while True:
        byte = stream.read(1)
        result |= (byte[0] & 0x7F) << (i * 7)
        i += 1
        if byte[0] & 0x80 == 0:
            break

    return result


def encode_varint(number: int) -> bytes:
    """Encode a decoded protobuf varint to its original bytes."""
    buf = []
    while True:
        towrite = number & 0x7F
        number >>= 7
        if number:
            buf.append(towrite | 0x80)
        else:
            buf.append(towrite)
            break
    return bytes(buf)


if __name__ == "__main__":
    cdef = """
    struct foo {
        uint32 foo;
        varint size;
        char   bar[size];
    };
    """

    cs = cstruct(endian=">")
    cs.add_custom_type("varint", ProtobufVarint)
    cs.load(cdef, compiled=False)

    aaa = b"a" * 123456
    buf = b"\x00\x00\x00\x01\xc0\xc4\x07" + aaa
    foo = cs.foo(buf + b"\x01\x02\x03")
    assert foo.foo == 1
    assert foo.size == 123456
    assert foo.bar == aaa
    assert foo.dumps() == buf

    assert cs.varint[2](b"\x80\x01\x80\x02") == [128, 256]
    assert cs.varint[2].dumps([128, 256]) == b"\x80\x01\x80\x02"
