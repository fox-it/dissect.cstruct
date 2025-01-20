from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_char_read(cs: cstruct) -> None:
    assert cs.char(b"A") == b"A"
    assert cs.char(b"AAAA\x00") == b"A"
    assert cs.char(io.BytesIO(b"AAAA\x00")) == b"A"


def test_char_write(cs: cstruct) -> None:
    assert cs.char(b"A").dumps() == b"A"


def test_char_array(cs: cstruct) -> None:
    buf = b"AAAA\x00"

    assert cs.char[4](buf) == b"AAAA"
    assert cs.char[4](io.BytesIO(buf)) == b"AAAA"

    assert cs.char[None](buf) == b"AAAA"
    assert cs.char[None](io.BytesIO(buf)) == b"AAAA"


def test_char_array_write(cs: cstruct) -> None:
    buf = b"AAAA\x00"

    assert cs.char[4](buf).dumps() == b"AAAA"
    assert cs.char[None](buf).dumps() == b"AAAA\x00"


def test_char_eof(cs: cstruct) -> None:
    with pytest.raises(EOFError):
        cs.char(b"")

    with pytest.raises(EOFError):
        cs.char[4](b"")

    with pytest.raises(EOFError):
        cs.char[None](b"AAAA")

    assert cs.char[0](b"") == b""


def test_char_default(cs: cstruct) -> None:
    assert cs.char.__default__() == b"\x00"
    assert cs.char[4].__default__() == b"\x00\x00\x00\x00"
    assert cs.char[None].__default__() == b""
