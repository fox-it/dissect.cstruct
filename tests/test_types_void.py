from __future__ import annotations

import io
from typing import TYPE_CHECKING

from .utils import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_void_read(cs: cstruct) -> None:
    # The type itself is truthy, but an instance is not
    assert cs.void
    assert not cs.void()

    stream = io.BytesIO(b"AAAA")
    assert not cs.void(stream)

    assert stream.tell() == 0


def test_void_write(cs: cstruct) -> None:
    assert cs.void().dumps() == b""


def test_void_array_read(cs: cstruct) -> None:
    assert not cs.void[4]()

    stream = io.BytesIO(b"AAAA")
    assert not cs.void[4](stream)
    assert not cs.void[None](stream)
    assert stream.tell() == 0


def test_void_array_write(cs: cstruct) -> None:
    assert cs.void[4](b"AAAA").dumps() == b""
    assert cs.void[None](b"AAAA").dumps() == b""


def test_void_default(cs: cstruct) -> None:
    assert cs.void() == cs.void.__default__()
    assert not cs.void()
    assert not cs.void.__default__()

    assert cs.void[1].__default__() == []
    assert cs.void[None].__default__() == []


def test_void_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        void    a;
        void    b[4];
        void    c[];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    stream = io.BytesIO(b"AAAA")

    obj = cs.test(stream)
    assert not obj.a
    assert not obj.b
    assert not obj.c

    assert stream.tell() == 0

    assert obj.dumps() == b""
